"""Analytic ground truth for the 3D line: a UV sphere written straight to GLB.

The reconstruction has no reference to be scored against, which is why the
silhouette metric could report 0.92 agreement on an asset that visibly contains
a lattice of junk and a floor puddle. This gives a shape whose volume, area,
shell count and silhouette are known in closed form.
"""

import json
import math
import struct
import sys
from pathlib import Path


def uv_sphere(radius=0.5, stacks=48, sectors=64):
    verts = [(0.0, radius, 0.0)]
    for i in range(1, stacks):
        phi = math.pi * i / stacks
        y = radius * math.cos(phi)
        rr = radius * math.sin(phi)
        for j in range(sectors):
            t = 2 * math.pi * j / sectors
            verts.append((rr * math.cos(t), y, rr * math.sin(t)))
    south = len(verts)
    verts.append((0.0, -radius, 0.0))

    def ring(i, j):
        return 1 + (i - 1) * sectors + (j % sectors)

    tris = []
    for j in range(sectors):
        tris.append((0, ring(1, j), ring(1, j + 1)))
    for i in range(1, stacks - 1):
        for j in range(sectors):
            a, b = ring(i, j), ring(i, j + 1)
            c, d = ring(i + 1, j), ring(i + 1, j + 1)
            tris.append((a, c, d))
            tris.append((a, d, b))
    for j in range(sectors):
        tris.append((south, ring(stacks - 1, j + 1), ring(stacks - 1, j)))
    return verts, tris


def mesh_measures(verts, tris):
    vol = sum((verts[a][0] * (verts[b][1] * verts[c][2] - verts[b][2] * verts[c][1])
               - verts[a][1] * (verts[b][0] * verts[c][2] - verts[b][2] * verts[c][0])
               + verts[a][2] * (verts[b][0] * verts[c][1] - verts[b][1] * verts[c][0]))
              / 6.0 for a, b, c in tris)
    area = 0.0
    for a, b, c in tris:
        va, vb, vc = verts[a], verts[b], verts[c]
        ux, uy, uz = vb[0] - va[0], vb[1] - va[1], vb[2] - va[2]
        wx, wy, wz = vc[0] - va[0], vc[1] - va[1], vc[2] - va[2]
        cx, cy, cz = uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx
        area += 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)
    return abs(vol), area


def write_glb(path, verts, tris, normals=None, uvs=None):
    """POSITION + indices, plus NORMAL / TEXCOORD_0 when the caller has them.

    Left-to-right attribute order keeps the no-extras output byte-identical to the
    original writer, so the analytic truth sphere this feeds stays comparable.
    """
    mn = [min(v[i] for v in verts) for i in range(3)]
    mx = [max(v[i] for v in verts) for i in range(3)]
    attrs = [("POSITION", verts, {"min": mn, "max": mx})]
    if normals is not None:
        attrs.append(("NORMAL", normals, {}))
    if uvs is not None:
        attrs.append(("TEXCOORD_0", uvs, {}))

    blobs, views, accessors, primitive = [], [], [], {}
    for name, rows, extra in attrs:
        width = 3 if name != "TEXCOORD_0" else 2
        buf = b"".join(struct.pack(f"<{width}f", *r[:width]) for r in rows)
        while len(buf) % 4:
            buf += b"\0"
        accessors.append({"bufferView": len(views), "componentType": 5126, "count": len(rows),
                          "type": "VEC2" if width == 2 else "VEC3", **extra})
        views.append({"buffer": 0, "byteOffset": sum(len(b) for b in blobs), "byteLength": len(buf)})
        blobs.append(buf)
        primitive[name] = len(accessors) - 1

    idx = b"".join(struct.pack("<3I", *t) for t in tris)
    while len(idx) % 4:
        idx += b"\0"
    views.append({"buffer": 0, "byteOffset": sum(len(b) for b in blobs), "byteLength": len(idx)})
    accessors.append({"bufferView": len(views) - 1, "componentType": 5125,
                      "count": len(tris) * 3, "type": "SCALAR"})
    blobs.append(idx)

    gltf = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": primitive, "indices": len(accessors) - 1, "mode": 4}]}],
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": sum(len(b) for b in blobs)}],
    }
    js = json.dumps(gltf, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    bin_chunk = b"".join(blobs)
    total = 12 + 8 + len(js) + 8 + len(bin_chunk)
    Path(path).write_bytes(
        struct.pack("<III", 0x46546C67, 2, total)
        + struct.pack("<II", len(js), 0x4E4F534A) + js
        + struct.pack("<II", len(bin_chunk), 0x004E4942) + bin_chunk
    )


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "run/solid")
    out.mkdir(parents=True, exist_ok=True)
    r = 0.5
    verts, tris = uv_sphere(radius=r)
    vol, area = mesh_measures(verts, tris)
    write_glb(out / "truth_sphere.glb", verts, tris)
    truth = {
        "radius": r,
        "analytic_volume": 4 / 3 * math.pi * r ** 3,
        "analytic_area": 4 * math.pi * r ** 2,
        "mesh_volume": vol,
        "mesh_area": area,
        "volume_rel_err": abs(vol - 4 / 3 * math.pi * r ** 3) / (4 / 3 * math.pi * r ** 3),
        "area_rel_err": abs(area - 4 * math.pi * r ** 2) / (4 * math.pi * r ** 2),
        "thinness_sphere_exact": 4 * math.pi / ((4 / 3 * math.pi) ** (2 / 3)),
        "verts": len(verts),
        "tris": len(tris),
        "bbox": [min(v[i] for v in verts) * 2 for i in range(3)],
    }
    (out / "truth_sphere.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    for k, v in truth.items():
        print(f"  {k:22} {v}")


if __name__ == "__main__":
    main()
