"""Normalise a generated GLB: unit bounding box, and normals that actually land on disk.

Two defects the octree sweep left behind. Hunyuan3D's output arrives with a bbox of
roughly 1.96 per axis -- nothing in the node graph scales a mesh, only RotateMesh --
and MeshSmoothNormals computes normals that SaveGLB then drops. Both are post-processing
properties, so they are fixed here rather than waited on from ComfyUI.
"""

import argparse
import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_solid
import mesh_metrics


def read_primitive(path):
    """The mesh's single primitive. More than one is refused, not silently merged."""
    gltf, binb = mesh_metrics.read_glb(path)
    prims = [p for m in gltf.get("meshes", []) for p in m["primitives"]]
    if len(prims) != 1:
        raise ValueError(f"expected 1 primitive, found {len(prims)} -- refusing to merge")
    pr = prims[0]
    attrs = {k: mesh_metrics.accessor_array(gltf, binb, i) for k, i in pr["attributes"].items()}
    if "POSITION" not in attrs:
        raise ValueError("no POSITION attribute")
    n = len(attrs["POSITION"])
    for k, v in attrs.items():
        if len(v) != n:
            raise ValueError(f"{k} has {len(v)} rows but POSITION has {n}; cannot carry it")
    if "indices" in pr:
        idx = [r[0] for r in mesh_metrics.accessor_array(gltf, binb, pr["indices"])]
        tris = [tuple(idx[i:i + 3]) for i in range(0, len(idx), 3)]
    else:
        tris = [(i, i + 1, i + 2) for i in range(0, n - 2)]
    return attrs, tris


def vertex_normals(verts, tris):
    """Area-weighted accumulate then normalise: the unnormalised cross product already
    has magnitude 2*area, so summing raw crosses weights each face by its area."""
    acc = [[0.0, 0.0, 0.0] for _ in verts]
    for a, b, c in tris:
        va, vb, vc = verts[a], verts[b], verts[c]
        u = [vb[i] - va[i] for i in range(3)]
        w = [vc[i] - va[i] for i in range(3)]
        cr = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]
        for i, vi in enumerate((a, b, c)):
            for k in range(3):
                acc[vi][k] += cr[k]
    out = []
    for x, y, z in acc:
        m = math.sqrt(x * x + y * y + z * z)
        out.append((x / m, y / m, z / m) if m > 1e-12 else (0.0, 0.0, 1.0))
    return out


def normalise(verts, target):
    lo = [min(v[i] for v in verts) for i in range(3)]
    hi = [max(v[i] for v in verts) for i in range(3)]
    extent = max(hi[i] - lo[i] for i in range(3))
    if extent <= 0:
        raise ValueError("degenerate mesh: zero extent")
    s = target / extent
    mid = [(lo[i] + hi[i]) / 2 for i in range(3)]
    return [tuple((v[i] - mid[i]) * s for i in range(3)) for v in verts], extent, s


def run(src, dst, target=1.0, force_normals=False):
    attrs, tris = read_primitive(src)
    before = mesh_metrics.analyse(src)
    verts = [tuple(map(float, v[:3])) for v in attrs["POSITION"]]

    verts, extent, scale = normalise(verts, target)

    have = "NORMAL" in attrs and not force_normals
    normals = [tuple(map(float, v[:3])) for v in attrs["NORMAL"]] if have else vertex_normals(verts, tris)
    uvs = None
    if "TEXCOORD_0" in attrs:
        uvs = [tuple(map(float, v[:2])) for v in attrs["TEXCOORD_0"]]

    make_solid.write_glb(dst, verts, tris, normals=normals, uvs=uvs)

    after = mesh_metrics.analyse(dst)
    return {
        "src": Path(src).name, "dst": Path(dst).name,
        "normal_source": "carried through" if have else ("computed" if normals else "none"),
        "bbox_before": before["bbox"], "bbox_after": after["bbox"],
        "max_extent_before": round(extent, 4), "scale": round(scale, 4),
        "tris_before": before["tris"], "tris_after": after["tris"],
        "shells_before": before["shells"], "shells_after": after["shells"],
        "watertight_after": after["watertight"],
        "attrs_after": sorted(k for k, v in {
            "POSITION": verts, "NORMAL": normals, "TEXCOORD_0": uvs}.items() if v),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--target", type=float, default=1.0, help="longest bbox edge in world units")
    ap.add_argument("--force-normals", action="store_true", help="recompute even if a NORMAL exists")
    a = ap.parse_args()
    print(json.dumps(run(a.src, a.dst, a.target, a.force_normals), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
