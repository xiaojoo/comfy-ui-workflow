"""The template registry: real workflow graphs, and how UI fields map onto them.

Only workflows that exist and have been run are listed. The mock this was built
from showed six categories including photographic portrait and e-commerce shots;
there is no measured graph for those, so they are absent rather than faked.
"""

import json
from pathlib import Path

from .config import WORKFLOWS

# UI field -> (node id, input key). Per template, because each graph puts the same
# idea in a different node -- a shared map would silently write into the wrong graph.
GEN_MAP = {
    "prompt": ("67", "text"),
    "negative": ("71", "text"),
    "width": ("68", "width"),
    "height": ("68", "height"),
    "batch": ("68", "batch_size"),
    "steps": ("70", "steps"),
    "cfg": ("70", "cfg"),
    "seed": ("70", "seed"),
    "unet": ("66", "unet_name"),
    "clip": ("62", "clip_name"),
    "prefix": ("9", "filename_prefix"),
    "shift": ("69", "shift"),
    "sampler": ("70", "sampler_name"),
    "scheduler": ("70", "scheduler"),
    "denoise": ("70", "denoise"),
}

VID_MAP = {
    "prompt": ("5", "text"),
    "negative": ("6", "text"),
    "width": ("7", "width"),
    "height": ("7", "height"),
    "length": ("7", "length"),
    "steps": ("8", "steps"),
    "cfg": ("8", "cfg"),
    "seed": ("8", "seed"),
    "unet": ("1", "unet_name"),
    "clip": ("2", "clip_name"),
    "prefix": ("11", "filename_prefix"),
    "shift": ("4", "shift"),
    "sampler": ("8", "sampler_name"),
    "scheduler": ("8", "scheduler"),
    "denoise": ("8", "denoise"),
    "fps": ("10", "fps"),
}

D3_MAP = {
    "image": ("2", "image"),
    "seed": ("24", "seed"),
    "octree": ("25", "octree_resolution"),
    "chunks": ("25", "num_chunks"),
    "threshold": ("26", "threshold"),
    "prefix": ("27", "filename_prefix"),
}

ICON_STYLE = ("flat vector app icon, one single centered object, solid pure white background, "
              "two or three flat colors, thick clean geometry, sharp corners, no text, "
              "no gradient, no shadow, no outline noise, high contrast, product icon style")
TECH_STYLE = ("flat geometric app icon, one single centered object, solid pure white background, "
              "cobalt blue and white only, sharp corners, blueprint-like precision, no text, "
              "no gradient, no shadow, no ornament, high contrast, enterprise software style")
NEG = ("photograph, scenery, background objects, gradient, drop shadow, text, watermark, "
       "intricate detail, low contrast, multiple subjects")

# The measured pairing, as defaults rather than a dropdown the user has to know to
# set. Without these two keys the model select binds to undefined and renders empty.
BASE = {"unet": "z_image_turbo_int8_convrot.safetensors", "clip": "qwen_3_4b_fp8_mixed.safetensors",
        "shift": 3.0, "sampler": "res_multistep", "scheduler": "simple", "denoise": 1.0}

TEMPLATES = [
    {
        "id": "icon_flat", "graph": "gen_icon.json", "category": "enterprise_icon",
        "name": "企业图标生成", "name_en": "Enterprise icon",
        "desc": "单主体扁平应用图标，白底、2-3 色、硬边。已跑 8/8 过矢量化与门禁。",
        "desc_en": "Flat single-object app icon on white, 2-3 colours. 8/8 measured through vectorise + gate.",
        "fields": ["prompt", "negative", "width", "height", "steps", "cfg", "seed", "unet", "clip"],
        "defaults": {"prompt": "a settings gear wheel with six teeth and a hollow centre",
                     "style": ICON_STYLE, "negative": NEG,
                     "width": 1024, "height": 1024, "steps": 8, "cfg": 1.0, "seed": 42, "batch": 1},
        "verified": True, "model": "Z-Image Turbo int8", "model_en": "Z-Image Turbo int8",
        "spec": "1024×1024 · 8步",
    },
    {
        "id": "icon_brand_tech", "graph": "gen_icon.json", "category": "enterprise_icon",
        "name": "品牌图标-科技风", "name_en": "Brand icon, tech",
        "desc": "钴蓝+白两色、蓝图式硬边，用于企业软件品牌族。同一生成图，换风格后缀。",
        "desc_en": "Cobalt and white, blueprint hard edges. Same graph, different style suffix.",
        "fields": ["prompt", "negative", "width", "height", "steps", "cfg", "seed", "unet", "clip"],
        "defaults": {"prompt": "a hexagonal badge with a star cut out of its centre",
                     "style": TECH_STYLE, "negative": NEG,
                     "width": 1024, "height": 1024, "steps": 8, "cfg": 1.0, "seed": 42, "batch": 1},
        "verified": True, "model": "Z-Image Turbo int8", "model_en": "Z-Image Turbo int8",
        "spec": "1024×1024 · 8步",
    },
    {
        "id": "icon_batch", "graph": "gen_icon.json", "category": "enterprise_icon",
        "name": "批量图标生成", "name_en": "Batch icons",
        "desc": "同一次采样出多张，用于挑形；一次显存驻留出满一批。",
        "desc_en": "Several images per run to pick shapes from; weights load once.",
        "fields": ["prompt", "negative", "width", "height", "steps", "cfg", "seed", "batch", "unet", "clip"],
        "defaults": {"prompt": "a notification bell with a small clapper underneath",
                     "style": ICON_STYLE, "negative": NEG,
                     "width": 1024, "height": 1024, "steps": 8, "cfg": 1.0, "seed": 42, "batch": 4},
        "verified": True, "model": "Z-Image Turbo int8", "model_en": "Z-Image Turbo int8",
        "spec": "1024×1024 · 4张",
    },
    {
        "id": "wan_t2v", "graph": "wan_t2v.json", "category": "enterprise_icon",
        "name": "图标动画-文生视频", "name_en": "Icon motion, text to video",
        "desc": "Wan 2.1 1.3B 出短动效。5 秒实测 136.5s、峰值 13.03 GiB，不需要提 WSL 内存。",
        "desc_en": "Wan 2.1 1.3B short motion. Measured 5s clip: 136.5s wall, 13.03 GiB peak, no WSL bump needed.",
        "map": VID_MAP,
        "fields": ["prompt", "negative", "width", "height", "length", "steps", "cfg", "seed", "unet", "clip", "fps"],
        "defaults": {"prompt": "a flat vector gear icon rotating slowly on a white background, clean geometry, steady camera",
                     "negative": "worst quality, blurry, jittery, distorted, watermarks, text",
                     "width": 832, "height": 480, "length": 33, "steps": 20, "cfg": 6.0,
                     "seed": 42, "fps": 16.0, "unet": "wan2.1_t2v_1.3B_fp16.safetensors",
                     "clip": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "shift": 8.0,
                     "sampler": "euler", "scheduler": "simple", "denoise": 1.0},
        "verified": True, "model": "Wan 2.1 T2V 1.3B", "model_en": "Wan 2.1 T2V 1.3B",
        "spec": "832×480 · 33帧", "media": "video",
    },
    {
        "id": "hunyuan3d", "graph": "3d_d0_chain.json", "category": "enterprise_icon",
        "name": "图标转 3D 网格", "name_en": "Icon to 3D mesh",
        "desc": "单张图 → Hunyuan3D 2.1 → 降面/焊接/补洞 → GLB + 渲染图。输入须是 ComfyUI input 目录里的文件。",
        "desc_en": "Image to Hunyuan3D 2.1 to decimate/weld/fill to GLB plus renders. Input is a filename in ComfyUI's input dir.",
        "map": D3_MAP,
        "fields": ["image", "seed", "octree", "threshold"],
        "defaults": {"image": "test.jpg", "seed": 42, "octree": 128, "threshold": 0.6, "chunks": 8000},
        "verified": True, "model": "Hunyuan3D 2.1", "model_en": "Hunyuan3D 2.1",
        "spec": "octree 128 · 工作点", "media": "model",
    },
]

for t in TEMPLATES:
    t.setdefault("map", GEN_MAP)
    t.setdefault("media", "image")
    # BASE is the image-graph's shared knob set. The video and 3D graphs have their
    # own weights and samplers, so merging it in would store parameters they ignore.
    if t["map"] is GEN_MAP:
        t["defaults"] = {**BASE, **t["defaults"]}

BY_ID = {t["id"]: t for t in TEMPLATES}


def graph_for(template, params):
    """The workflow with UI values written into the nodes that own them.

    The style suffix is appended server-side because it is part of the measured
    prompt, not something a caller should have to remember to add.
    """
    g = json.loads((WORKFLOWS / template["graph"]).read_text(encoding="utf-8"))
    merged = {**template["defaults"], **params}
    style = merged.pop("style", "")
    for field, (node, key) in template["map"].items():
        if field not in merged or node not in g:
            continue
        value = merged[field]
        if field == "prompt" and style:
            value = f"{value}, {style}"
        g[node]["inputs"][key] = value
    return g


def public():
    """What the browser may show -- no node ids, no graph internals."""
    return [{"id": t["id"], "name": t["name"], "name_en": t["name_en"], "category": t["category"],
             "desc": t["desc"], "desc_en": t["desc_en"], "fields": t["fields"],
             "defaults": {k: v for k, v in t["defaults"].items() if k != "style"},
             "verified": t["verified"], "model": t["model"], "model_en": t["model_en"],
             "media": t["media"], "spec": t["spec"]} for t in TEMPLATES]
