"""Read structure out of a GLB without a 3D library.

A GLB is a header plus a JSON chunk and a BIN chunk, so vertex/triangle counts,
UV sets, materials and textures are all answerable from the JSON chunk alone --
which is what the D4 budget (face count, UV island presence, texture presence)
needs before anyone opens it in a viewer.
"""

import json
import struct
import sys
from pathlib import Path

CHUNK_JSON = 0x4E4F534A


def parse(path):
    data = Path(path).read_bytes()
    magic, version, length = struct.unpack("<III", data[:12])
    if magic != 0x46546C67:
        raise ValueError(f"not a GLB (magic {magic:#x})")
    off = 12
    gltf = None
    bin_len = 0
    while off + 8 <= len(data):
        clen, ctype = struct.unpack("<II", data[off:off + 8])
        if ctype == CHUNK_JSON:
            gltf = json.loads(data[off + 8: off + 8 + clen])
        elif ctype == 0x004E4942:
            bin_len = clen
        off += 8 + clen
    return magic, version, length, gltf, bin_len


def main():
    for p in sys.argv[1:]:
        _, ver, length, g, bin_len = parse(p)
        acc = g.get("accessors", [])
        print(f"{p}")
        print(f"  glb v{ver} total {length/1e6:.2f} MB, bin chunk {bin_len/1e6:.2f} MB")
        print(f"  meshes {len(g.get('meshes', []))}  materials {len(g.get('materials', []))}  "
              f"textures {len(g.get('textures', []))}  images {len(g.get('images', []))}  "
              f"animations {len(g.get('animations', []))}")
        for mi, m in enumerate(g.get("meshes", [])):
            for pi, pr in enumerate(m.get("primitives", [])):
                idx = pr.get("indices")
                ntri = (acc[idx]["count"] // 3) if idx is not None else None
                pos = pr["attributes"]["POSITION"]
                attrs = sorted(pr["attributes"])
                ext = (acc[pos].get("min"), acc[pos].get("max"))
                print(f"  mesh{mi} prim{pi}: verts {acc[pos]['count']} tris {ntri} "
                      f"attrs {sorted(attrs)} mode {pr.get('mode', 4)}")
                if ext[0]:
                    w = [round(b - a, 4) for a, b in zip(ext[0], ext[1])]
                    print(f"     bbox extent {w}  (units: {'~1 cube' if max(w) < 1.6 else 'NOT normalised'})")
        ext = g.get("extensionsUsed", [])
        print(f"  extensionsUsed {ext}")


if __name__ == "__main__":
    main()
