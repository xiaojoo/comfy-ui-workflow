"""Shell-level structure metrics for a GLB -- the metric that the silhouette IoU could not be.

Silhouette agreement between three octree densities stayed at 0.90-0.92 while the
renders visibly contained a lattice of junk and a floor puddle, because those live
*inside* the outline. What distinguishes them is topology: extra closed shells,
non-manifold edges, and above all shells with large area but near-zero volume.
"""

import json
import math
import struct
import sys
from collections import defaultdict
from pathlib import Path

CHUNK_JSON = 0x4E4F534A
COMP_TYPE = {5126: ("<f", 4), 5123: ("<H", 2), 5125: ("<I", 4), 5121: ("<B", 1), 5122: ("<h", 2), 5120: ("<b", 1)}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def read_glb(path):
    data = Path(path).read_bytes()
    off = 12
    gltf = None
    binb = b""
    while off + 8 <= len(data):
        clen, ctype = struct.unpack("<II", data[off:off + 8])
        if ctype == CHUNK_JSON:
            gltf = json.loads(data[off + 8:off + 8 + clen])
        elif ctype == 0x004E4942:
            binb = data[off + 8:off + 8 + clen]
        off += 8 + clen
    return gltf, binb


def accessor_array(gltf, binb, i):
    a = gltf["accessors"][i]
    bv = gltf["bufferViews"][a["bufferView"]]
    fmt, sz = COMP_TYPE[a["componentType"]]
    n = NCOMP[a["type"]]
    base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", sz * n)
    out = []
    for k in range(a["count"]):
        o = base + k * stride
        out.append(struct.unpack_from(f"<{n}{fmt[1]}", binb, o))
    return out


def analyse(path, weld_decimals=5):
    gltf, binb = read_glb(path)
    verts, tris = [], []
    for mesh in gltf.get("meshes", []):
        for pr in mesh["primitives"]:
            v = accessor_array(gltf, binb, pr["attributes"]["POSITION"])
            base = len(verts)
            verts.extend(v)
            if "indices" in pr:
                idx = [x[0] for x in accessor_array(gltf, binb, pr["indices"])]
            else:
                idx = list(range(len(v)))
            for i in range(0, len(idx), 3):
                tris.append(tuple(base + j for j in idx[i:i + 3]))

    key = {}
    remap = []
    for x, y, z in verts:
        k = (round(x, weld_decimals), round(y, weld_decimals), round(z, weld_decimals))
        if k not in key:
            key[k] = len(key)
        remap.append(key[k])
    wtris = [(remap[a], remap[b], remap[c]) for a, b, c in tris]
    wtris = [t for t in wtris if len(set(t)) == 3]

    parent = list(range(len(key)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    edges = defaultdict(int)
    for a, b, c in wtris:
        union(a, b)
        union(b, c)
        union(c, a)
        for e in ((min(a, b), max(a, b)), (min(b, c), max(b, c)), (min(c, a), max(c, a))):
            edges[e] += 1

    comp = defaultdict(lambda: {"tris": 0, "area": 0.0, "vol": 0.0, "verts": set()})
    for a, b, c in wtris:
        r = find(a)
        va, vb, vc = verts[a], verts[b], verts[c]
        ux, uy, uz = vb[0] - va[0], vb[1] - va[1], vb[2] - va[2]
        wx, wy, wz = vc[0] - va[0], vc[1] - va[1], vc[2] - va[2]
        cx, cy, cz = uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx
        d = comp[r]
        d["tris"] += 1
        d["area"] += 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)
        d["vol"] += (va[0] * (vb[1] * vc[2] - vb[2] * vc[1])
                     - va[1] * (vb[0] * vc[2] - vb[2] * vc[0])
                     + va[2] * (vb[0] * vc[1] - vb[1] * vc[0])) / 6.0
        d["verts"].update((a, b, c))

    open_edges = sum(1 for n in edges.values() if n == 1)
    bad_edges = sum(1 for n in edges.values() if n > 2)
    spheres = []
    for r, d in comp.items():
        vol = abs(d["vol"])
        thin = d["area"] / (vol ** (2 / 3)) if vol > 1e-12 else float("inf")
        spheres.append({"tris": d["tris"], "area": round(d["area"], 6), "volume": round(vol, 8),
                        "thinness": round(thin, 1) if math.isfinite(thin) else "inf"})
    spheres.sort(key=lambda s: -s["area"])

    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    return {
        "file": Path(path).name,
        "verts_welded": len(key),
        "tris": len(wtris),
        "shells": len(spheres),
        "open_edges": open_edges,
        "nonmanifold_edges": bad_edges,
        "watertight": open_edges == 0 and bad_edges == 0,
        "bbox": [round(max(xs) - min(xs), 4), round(max(ys) - min(ys), 4), round(max(zs) - min(zs), 4)],
        "total_area": round(sum(s["area"] for s in spheres), 5),
        "total_volume": round(sum(abs(s["volume"]) for s in spheres), 6),
        "top_shells": spheres[:6],
    }


def main():
    for p in sys.argv[1:]:
        r = analyse(p)
        print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
