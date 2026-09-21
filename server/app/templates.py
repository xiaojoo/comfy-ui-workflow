"""The template registry: real workflow graphs, and how UI fields map onto them.

Only workflows that exist and have been run are listed. The mock this was built
from showed six categories including photographic portrait and e-commerce shots;
there is no measured graph for those, so they are absent rather than faked.
"""

import json
from pathlib import Path

from .config import WORKFLOWS

# UI field -> (node id, input key) in gen_icon.json. Declared once so the server,
# not the browser, decides which knob moves which node.
GEN_FIELDS = {
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
]

for t in TEMPLATES:
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
    for field, (node, key) in GEN_FIELDS.items():
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
             "spec": t["spec"]} for t in TEMPLATES]
