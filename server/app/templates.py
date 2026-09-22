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

# Krea-2 Turbo, the only pairing on this box that came through the hands-at-face pose
# without an extra digit (4/4 clean; Z-Image Turbo was 4/4 defective on the same pose).
PORTRAIT_MAP = {
    "prompt": ("4", "text"),
    "width": ("6", "width"),
    "height": ("6", "height"),
    "batch": ("6", "batch_size"),
    "seed": ("7", "seed"),
    "steps": ("7", "steps"),
    "cfg": ("7", "cfg"),
    "sampler": ("7", "sampler_name"),
    "scheduler": ("7", "scheduler"),
    "denoise": ("7", "denoise"),
    "unet": ("1", "unet_name"),
    "clip": ("2", "clip_name"),
    "vae": ("3", "vae_name"),
    "prefix": ("9", "filename_prefix"),
}

# MiniMax H3 first-frame route. The negative prompt is deliberately absent: this graph is
# conditioned by one positive stream (the official t2v/i2v graphs carry no second one), so
# a negative box would be a control that does nothing.
H3_MAP = {
    "prompt": ("6", "prompt"),
    "width": ("6", "width"),
    "height": ("6", "height"),
    "length": ("6", "length"),
    "image": ("5", "image"),
    "unet": ("1", "unet_name"),
    "clip": ("2", "clip_name"),
    "vae": ("3", "vae_name"),
    "lora": ("7", "lora_name"),
    "lora_strength": ("7", "strength_model"),
    "sampler": ("9", "sampler_name"),
    "scheduler": ("10", "scheduler"),
    "steps": ("10", "steps"),
    "denoise": ("10", "denoise"),
    "seed": ("11", "noise_seed"),
    "fps": ("15", "fps"),
    "prefix": ("16", "filename_prefix"),
}

# ref2va: the reference route. Identity rides on up to nine reference images quoted by tag
# (<Picture 1>), not on a first frame, so the shot can start anywhere and still be her.
H3_REF_MAP = {
    "prompt": ("6", "prompt"),
    "width": ("6", "width"),
    "height": ("6", "height"),
    "length": ("6", "length"),
    "image": ("5", "image"),
    "ref_size": ("6", "ref_image_size"),
    "unet": ("1", "unet_name"),
    "clip": ("2", "clip_name"),
    "vae": ("3", "vae_name"),
    "lora": ("7", "lora_name"),
    "lora_strength": ("7", "strength_model"),
    "sampler": ("9", "sampler_name"),
    "scheduler": ("10", "scheduler"),
    "steps": ("10", "steps"),
    "denoise": ("10", "denoise"),
    "seed": ("11", "noise_seed"),
    "fps": ("15", "fps"),
    "prefix": ("16", "filename_prefix"),
}

# Video to HD: the whole clip lands in RAM as one IMAGE batch (this engine has no
# loop node), so the frame count is the ceiling, not the model. fps and audio ride
# through GetVideoComponents -> CreateVideo, so the speed and sound do not change.
UP_VID_MAP = {
    "video": ("1", "file"),
    "model": ("3", "model_name"),
    "prefix": ("6", "filename_prefix"),
}

# Image to HD: LoadImage -> a 4x model -> SaveImage. The model name is the engine's
# own combo (see comfy.SOURCES); both weights on this box are listed there.
UP_IMG_MAP = {
    "image": ("1", "image"),
    "model": ("2", "model_name"),
    "prefix": ("4", "filename_prefix"),
}

# MiniMax H3. The negative prompt is deliberately absent: this graph is conditioned by
# one positive stream (the official t2v/i2v graphs carry no second one), so a negative
# box would be a control that does nothing.
H3_MAP = {
    "prompt": ("6", "prompt"),
    "width": ("6", "width"),
    "height": ("6", "height"),
    "length": ("6", "length"),
    "image": ("5", "image"),
    "unet": ("1", "unet_name"),
    "clip": ("2", "clip_name"),
    "vae": ("3", "vae_name"),
    "lora": ("7", "lora_name"),
    "lora_strength": ("7", "strength_model"),
    "sampler": ("9", "sampler_name"),
    "scheduler": ("10", "scheduler"),
    "steps": ("10", "steps"),
    "denoise": ("10", "denoise"),
    "seed": ("11", "noise_seed"),
    "fps": ("15", "fps"),
    "prefix": ("16", "filename_prefix"),
}

# ref2va: the reference route. Identity rides on up to nine reference images quoted by
# tag (<Picture 1>), not on a first frame, so the shot can start anywhere and still be her.
H3_REF_MAP = {
    "prompt": ("6", "prompt"),
    "width": ("6", "width"),
    "height": ("6", "height"),
    "length": ("6", "length"),
    "image": ("5", "image"),
    "ref_size": ("6", "ref_image_size"),
    "unet": ("1", "unet_name"),
    "clip": ("2", "clip_name"),
    "vae": ("3", "vae_name"),
    "lora": ("7", "lora_name"),
    "lora_strength": ("7", "strength_model"),
    "sampler": ("9", "sampler_name"),
    "scheduler": ("10", "scheduler"),
    "steps": ("10", "steps"),
    "denoise": ("10", "denoise"),
    "seed": ("11", "noise_seed"),
    "fps": ("15", "fps"),
    "prefix": ("16", "filename_prefix"),
}

# Qwen-Image-2.1: one graph covering text-to-image and reference edit. The generator
# takes its reference images through flat dotted keys (`images.image_1`), which the
# engine itself re-nests into the `images` dict -- so a slot that is not wanted is a key
# that is not written, and _qwen_mode drops the LoadImage behind it.
QWEN_REFS = {"ref1": "21", "ref2": "22", "ref3": "23", "ref4": "24"}

QWEN_MAP = {
    "prompt": ("5", "prompt"),
    "negative": ("5", "negative_prompt"),
    "width": ("6", "width"),
    "height": ("6", "height"),
    "batch": ("8", "amount"),
    "steps": ("10", "steps"),
    "cfg": ("10", "cfg"),
    "seed": ("10", "seed"),
    "unet": ("1", "unet_name"),
    "clip": ("2", "clip_name"),
    "vae": ("3", "vae_name"),
    "prefix": ("9", "filename_prefix"),
}

# Edit mode deliberately has no width/height: the canvas is image_1's own resized latent,
# and the official template's note on a second, different size is "the edit can shift".
QWEN_EDIT_MAP = {
    "prompt": ("5", "prompt"),
    "negative": ("5", "negative_prompt"),
    "resolution": ("5", "resolution"),
    "batch": ("8", "amount"),
    "steps": ("10", "steps"),
    "cfg": ("10", "cfg"),
    "seed": ("10", "seed"),
    "unet": ("1", "unet_name"),
    "clip": ("2", "clip_name"),
    "vae": ("3", "vae_name"),
    "prefix": ("9", "filename_prefix"),
    **{field: (node, "image") for field, node in QWEN_REFS.items()},
}

ICON_STYLE = ("flat vector app icon, one single centered object, solid pure white background, "
              "two or three flat colors, thick clean geometry, sharp corners, no text, "
              "no gradient, no shadow, no outline noise, high contrast, product icon style")
TECH_STYLE = ("flat geometric app icon, one single centered object, solid pure white background, "
              "cobalt blue and white only, sharp corners, blueprint-like precision, no text, "
              "no gradient, no shadow, no ornament, high contrast, enterprise software style")
NEG = ("photograph, scenery, background objects, gradient, drop shadow, text, watermark, "
       "intricate detail, low contrast, multiple subjects")

# Appended to the character prompt server-side, same as the icon styles: the anatomy
# wording is part of the measured prompt, not something the caller has to remember.
PERSON_STYLE = ("photorealistic portrait, natural skin texture, correct anatomy, "
                "five separate fingers on each hand, plain mid-grey studio background, "
                "soft key light, 50mm, sharp focus")

# Xianxia / xuanhuan presets on the same measured Z-Image graph. The hand wording in
# XIANXIA_STYLE is the same insurance PERSON_STYLE carries; the scene preset keeps
# characters out of focus so a face defect cannot ruin an environment shot.
# The strand-by-strand wording is the A/B winner: the head-band Laplacian variance went
# 479 -> 731-820 (xianxia) and 139-308 -> 566-636 (xuanhuan) at 16 steps / 1024-side canvas.
XIANXIA_STYLE = ("xianxia anime illustration, one immortal cultivator, flowing hanfu with cloud motifs, "
                 "long black hair rendered strand by strand, individual loose strands catching the rim "
                 "light, jade hairpin and flowing crown with thin gold chains, layered silk sleeves with "
                 "embroidered cloud-and-crane gold patterns, woven belt with dangling jade pendants, "
                 "crisp fabric folds, delicate eyelash and lip detail, soft rim light, painted misty "
                 "mountain backdrop, clean cel linework, high detail illustration, correct anatomy, "
                 "five separate fingers on each hand")
XUANHUAN_STYLE = ("xuanhuan fantasy world concept art, vast floating mountains above an endless sea of "
                  "clouds, waterfall threads catching light against crag faces with crisp rock grain, "
                  "ancient giant trees with individual leaves and exposed root claws, glowing rune rivers "
                  "etched in gold, distant celestial palace with layered bracket-set roofs and hanging "
                  "lantern chains, volumetric god rays, atmospheric haze layering, painted matte style, "
                  "high detail matte painting, no single character in focus")
ART_NEG = ("photograph, 3d render, extra fingers, extra limbs, deformed hands, watermark, text, logo, "
           "lowres, oversaturated, muddy detail")

# The measured pairing, as defaults rather than a dropdown the user has to know to
# set. Without these two keys the model select binds to undefined and renders empty.
BASE = {"unet": "z_image_turbo_int8_convrot.safetensors", "clip": "qwen_3_4b_fp8_mixed.safetensors",
        "shift": 3.0, "sampler": "res_multistep", "scheduler": "simple", "denoise": 1.0}

# The Qwen-Image-2.1 trio. The text encoder is the w4a8 build rather than the int8 one the
# shipped template names, because int8 DiT + int8 encoder + VAE is 16.10 GiB and this WSL
# distro is capped at 15.5 GiB; w4a8 is 13.27 GiB, which runs without touching .wslconfig.
QWEN_UNET = "qwen_image_2.1_int8_convrot.safetensors"
QWEN_CLIP = "qwen3vl_8b_w4a8.safetensors"
QWEN_VAE = "qwen_image_2.1_vae_bf16.safetensors"

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
        # Long clips outrun the 900 s default and get recorded as TIMEOUT while the
        # engine is still sampling. Sized for the measured long end of the ladder.
        "timeout": 2700,
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
    {
        "id": "char_portrait", "graph": "char_portrait.json", "category": "character",
        "name": "人物图片-真人身材", "name_en": "Character photo",
        "desc": "Krea-2 Turbo 出真人像，一次 4 张挑形。手部实测：双手合十这个最难的姿势 4/4 无多余指，"
                "同姿势 Z-Image Turbo 4/4 多指；每张 9.2s。构图会切脚，全身照要多出几张挑。",
        "desc_en": "Krea-2 Turbo, 4 per run. On the hardest pose (hands at the face) it measured 4/4 with no "
                   "extra digit, where Z-Image Turbo measured 4/4 defective. 9.2s per image warm.",
        "map": PORTRAIT_MAP,
        "fields": ["prompt", "width", "height", "batch", "steps", "cfg", "seed", "unet", "clip", "vae"],
        "defaults": {"prompt": "a young woman standing relaxed and facing the camera, full body from head to "
                               "feet, arms hanging at her sides, both hands open with fingers clearly separated "
                               "and visible, white t-shirt and dark trousers",
                     "style": PERSON_STYLE,
                     "width": 832, "height": 1216, "batch": 4, "steps": 8, "cfg": 1.0, "seed": 42,
                     "sampler": "euler", "scheduler": "simple", "denoise": 1.0,
                     "unet": "krea2_turbo_fp8_scaled.safetensors",
                     "clip": "qwen3vl_4b_fp8_scaled.safetensors", "vae": "qwen_image_vae.safetensors"},
        "verified": True, "model": "Krea-2 Turbo fp8", "model_en": "Krea-2 Turbo fp8",
        "spec": "832×1216 · 8步 · 4张",
    },
    {
        "id": "char_video", "graph": "h3_char_i2v.json", "category": "character",
        "name": "人物视频-图生视频", "name_en": "Character clip, image to video",
        "desc": "MiniMax H3 用选定的人物图当首帧出 5 秒短片，带原生声音。首帧是关键帧、每步重注入不参与"
                "去噪，所以脸和衣服由这张图钉住。实测 480×864×124帧 8步 = 89.0s，显存最低 0.75 GiB。",
        "desc_en": "MiniMax H3 takes the picked character photo as the first keyframe and renders a 5s clip with "
                   "native audio. The keyframe is re-injected every step and never denoised, so identity rides on "
                   "that image. Measured 480x864x124 at 8 steps: 89.0s, 0.75 GiB VRAM free at the floor.",
        "map": H3_MAP,
        "fields": ["prompt", "image", "width", "height", "length", "steps", "seed", "fps",
                   "unet", "clip", "vae", "lora", "lora_strength"],
        "defaults": {"prompt": "the person turns their head slowly toward the camera and smiles, arms relaxed "
                               "at their sides, hands visible, steady camera, no cuts",
                     "image": "", "width": 480, "height": 864, "length": 124, "steps": 8, "seed": 42,
                     "fps": 24.0, "unet": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
                     "clip": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
                     "vae": "minimax_h3_video_vae_fp16.safetensors",
                     "lora": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
                     "lora_strength": 1.0, "sampler": "res_multistep", "scheduler": "simple",
                     "denoise": 1.0},
        "verified": True, "model": "MiniMax H3 fl2va int8", "model_en": "MiniMax H3 fl2va int8",
        "spec": "480×864 · 124帧 · 8步", "media": "video",
        # The first run of the day pays for a 20GB DiT plus a 15GB text encoder off disk;
        # 89s is the warm sampling number, not the wall number a cold queue sees.
        "timeout": 1800,
    },
    {
        "id": "char_video_ref", "graph": "h3_char_ref2v.json", "category": "character",
        "name": "人物视频-参考锁脸", "name_en": "Character clip, by reference",
        "desc": "MiniMax H3 ref2va：身份靠参考图本身，不靠首帧。提示词里用 <Picture 1> 指代第几张参考图，"
                "最多 9 张。实测 480×864×124帧 4步：match 53.6s、max 55.6s（max 只贵 4%）。脸、发带、"
                "外套、背景都跟住了 —— 但它不锁构图：提示词写了 no zoom，它仍会自己推成脸部特写。"
                "要保住原来那张图的景别，走首帧路线。",
        "desc_en": "MiniMax H3 ref2va: identity rides on the reference image itself rather than on a first "
                   "frame. Quote references by tag (<Picture 1>), up to nine. Measured at 480x864x124, 4 "
                   "steps: 53.6s for match, 55.6s for max -- max costs 4%, not the several-fold the node "
                   "tooltip warns of. Face, headband, jacket and backdrop all held; the framing did not. "
                   "Despite 'no zoom' it pushes into a close-up, so use the first-frame route to keep the "
                   "shot you picked.",
        "map": H3_REF_MAP,
        "fields": ["prompt", "image", "width", "height", "length", "ref_size", "steps", "seed", "fps",
                   "unet", "clip", "vae", "lora", "lora_strength"],
        "defaults": {"prompt": "<Picture 1> is the character. She turns her head slowly to her left and back "
                               "to the camera, then lifts her right hand and waves once, arms and hands stay "
                               "fully visible, steady camera, no cuts, no zoom",
                     "image": "", "width": 480, "height": 864, "length": 124, "ref_size": "match",
                     "steps": 4, "seed": 42, "fps": 24.0,
                     "unet": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
                     "clip": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
                     "vae": "minimax_h3_video_vae_fp16.safetensors",
                     "lora": "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
                     "lora_strength": 1.0, "sampler": "res_multistep", "scheduler": "simple",
                     "denoise": 1.0},
        "verified": True, "model": "MiniMax H3 ref2va int8", "model_en": "MiniMax H3 ref2va int8",
        "spec": "480×864 · 124帧 · 4步", "media": "video",
        "timeout": 1800,
    },
    {
        "id": "upscale_image", "graph": "upscale_image.json", "category": "enhance",
        "name": "图片转高清", "name_en": "Image to HD",
        "desc": "4 倍模型超分，不重画内容。两个权重本机已装：4x-UltraSharp 通用（实测 832×1216 "
                "→ 3328×4864，6.0s）、RealESRGAN_x4plus_anime 偏动漫线条（热态 1.0s）。"
                "输入可上传，也可从已有任务结果直接绑定。",
        "desc_en": "4x model super-resolution, no re-imagining. Both weights are local: "
                   "4x-UltraSharp general (832x1216 -> 3328x4864 measured 6.0s), "
                   "RealESRGAN_x4plus_anime for anime linework (1.0s warm). "
                   "Input is an upload or a bound result from an earlier task.",
        "map": UP_IMG_MAP,
        "fields": ["image", "model"],
        "defaults": {"image": "", "model": "4x-UltraSharp.pth"},
        "verified": True, "model": "4x-UltraSharp / RealESRGAN-anime",
        "model_en": "4x-UltraSharp / RealESRGAN-anime",
        "spec": "输出 = 输入 × 4",
    },
    {
        "id": "upscale_video", "graph": "upscale_video.json", "category": "enhance",
        "name": "视频转高清", "name_en": "Video to HD",
        "desc": "整条片子逐帧过 4 倍模型超分，帧率与声音原样带走（实测音轨保留）。全批帧"
                "一次性进内存：832×480×33帧 42.3s、480×864×62帧 82.6s 通过；"
                "480×864×124帧 与 832×480×81帧 都会把引擎 OOM 压死，这条线之前别提交。",
        "desc_en": "Every frame through a 4x model; fps and audio carried through (audio track "
                   "verified in the output). The whole batch lands in RAM at once: 832x480x33 "
                   "measured 42.3s and 480x864x62 measured 82.6s, while 480x864x124 and "
                   "832x480x81 OOM-killed the engine.",
        "map": UP_VID_MAP,
        "fields": ["video", "model"],
        "defaults": {"video": "", "model": "4x-UltraSharp.pth"},
        "verified": True, "model": "4x-UltraSharp / RealESRGAN-anime",
        "model_en": "4x-UltraSharp / RealESRGAN-anime",
        "spec": "逐帧 4× 超分", "media": "video",
        "timeout": 1800,
    },
    {
        "id": "xianxia_char", "graph": "gen_icon.json", "category": "concept_art",
        "name": "仙侠动漫人物", "name_en": "Xianxia anime character",
        "desc": "Z-Image Turbo 走仙侠动漫预设：发丝逐缕、玉冠金链、袖纹刺绣写进风格后缀。"
                "16 步 1024×1536，一次 2 张 34.4s（8 步版发带区锐度 479，这套 731-820，已 A/B）。",
        "desc_en": "The measured Z-Image graph on a xianxia preset with strand-by-strand hair, jade "
                   "crown and embroidered sleeves in the style suffix. 16 steps at 1024x1536, 34.4s "
                   "per 2-image run: head-band sharpness measured 731-820 against 479 on the old 8-step recipe.",
        "fields": ["prompt", "negative", "width", "height", "batch", "steps", "cfg", "seed", "unet", "clip"],
        "defaults": {"prompt": "a young sword-bearing immortal standing on a drifting crane, full body, "
                               "robes moving in the wind",
                     "style": XIANXIA_STYLE, "negative": ART_NEG,
                     "width": 1024, "height": 1536, "batch": 2, "steps": 16, "cfg": 1.8, "seed": 42,
                     "shift": 3.5},
        "verified": True, "model": "Z-Image Turbo int8", "model_en": "Z-Image Turbo int8",
        "spec": "1024×1536 · 16步 · 2张",
    },
    {
        "id": "xuanhuan_world", "graph": "gen_icon.json", "category": "concept_art",
        "name": "玄幻世界场景", "name_en": "Xuanhuan world scene",
        "desc": "同一张 Z-Image 图走玄幻世界观预设：岩纹、水丝、单叶、斗拱灯笼写进后缀。"
                "16 步 1536×1024，一次 2 张 34.4s（头部区外按场景带量：锐度 139-308 → 566-636）。",
        "desc_en": "Same graph, xuanhuan preset with rock grain, waterfall threads, individual leaves "
                   "and bracket-set roofs in the suffix. 16 steps at 1536x1024, 34.4s per 2-image run; "
                   "detail-band sharpness measured 566-636 against 139-308 on the old recipe.",
        "fields": ["prompt", "negative", "width", "height", "batch", "steps", "cfg", "seed", "unet", "clip"],
        "defaults": {"prompt": "an endless sky realm with floating stone islands and waterfalls pouring "
                               "into clouds, a glowing array gate on the horizon",
                     "style": XUANHUAN_STYLE, "negative": ART_NEG,
                     "width": 1536, "height": 1024, "batch": 2, "steps": 16, "cfg": 1.8, "seed": 42,
                     "shift": 3.5},
        "verified": True, "model": "Z-Image Turbo int8", "model_en": "Z-Image Turbo int8",
        "spec": "1536×1024 · 16步 · 2张",
    },
    {
        "id": "qwen_image", "graph": "qwen_image_21.json", "category": "general",
        "name": "通用生图-Qwen Image 2.1", "name_en": "General image, Qwen-Image 2.1",
        "desc": "Qwen-Image-2.1（7B，生图与改图同一份权重）文生图：官方原生 2K 直出，尺寸取 32 的倍数；"
                "cfg 保持 1 是官方路径，此时反向提示词不参与采样，抬 cfg 才生效。"
                "本机实测 25 步（官方 pipeline 用 40-50）：1024² 冷 15.1s / 暖 9.1s，2048² 62.7s，"
                "一次 4 张 35.3s；"
                "WSL 内存余量最低 1.83 GiB，显存最低只剩 0.49 GiB；2K×4 出片 278.3s 不炸。"
                "透明底要按官方措辞包一层 RGBA：包了实测 97.69% 像素透明，不包 0.00%"
                "（文件永远是 RGBA 形状，别拿通道当证据）。",
        "desc_en": "Qwen-Image-2.1 (7B, one checkpoint for generation and editing) text to image: "
                   "native 2K direct output on multiples of 32. cfg 1 is the official path, where the "
                   "negative prompt is not sampled -- raise cfg to use it. Measured here at 25 steps: "
                   "1024² cold 15.1s / warm 9.1s, 2048² 62.7s, 4-up 35.3s, 2K 4-up 278.3s; WSL never "
                   "dropped below 1.83 GiB available and VRAM got to within 0.49 GiB of full. "
                   "Transparency needs the official RGBA wording: 97.69% of pixels transparent with it, "
                   "0.00% without -- every file is RGBA-shaped, so the colour type is not the evidence.",
        # The trio is pinned rather than offered: int8 DiT + the int8 encoder the shipped
        # template names is 16.10 GiB, past the distro's ceiling -- the failure is not an
        # error message, it is the whole WSL VM wedging. The keys stay in defaults, so
        # graph_for still writes exactly what was measured.
        "map": QWEN_MAP,
        "fields": ["prompt", "negative", "width", "height", "batch", "steps", "cfg", "seed"],
        "sizes": [[1024, 1024], [2048, 2048], [2048, 1536], [1536, 2048],
                  [2048, 1152], [1152, 2048], [1152, 896], [896, 1152]],
        "defaults": {"prompt": "a studio product shot of a matte black ceramic coffee mug on a "
                               "seamless grey sweep, soft box lighting, sharp focus",
                     "negative": "", "width": 1024, "height": 1024, "batch": 1, "steps": 25,
                     "cfg": 1.0, "seed": 42, "sampler": "euler", "scheduler": "simple",
                     "denoise": 1.0, "unet": QWEN_UNET, "clip": QWEN_CLIP, "vae": QWEN_VAE},
        "verified": True, "model": "Qwen-Image 2.1 int8", "model_en": "Qwen-Image 2.1 int8",
        "spec": "1024×1024 · 25步 · 暖 9.1s",
        # The first run of the day reads 13.27 GiB of weights off disk; the sampling
        # number is only the warm part of it.
        "timeout": 1800,
    },
    {
        "id": "qwen_image_edit", "graph": "qwen_image_21.json", "category": "general",
        "name": "通用改图-Qwen Image 2.1", "name_en": "General edit, Qwen-Image 2.1",
        "desc": "同一条图、参考图驱动：ref1 是被改的对象，ref2-4 是额外参考，提示词里用 "
                "<image1>…<image4> 指代（官方上限 10 张）。画布跟 ref1 走，resolution 是总像素预算"
                "不是宽高，0 = 只按 32 对齐不缩放；官方默认 1024、最高 2048。"
                "实测 25 步：1 张参考 15.1s、2 张 33.3s；1152×896 的 ref 进去就是 1152×896 出来。"
                "结果上点 ✎ 直接把那张图当 ref1。",
        "desc_en": "Same graph, driven by reference images: ref1 is the edit target, ref2-4 extra "
                   "references, quoted in the prompt as <image1>…<image4> (the model takes ten). The "
                   "canvas follows ref1; resolution is a total pixel budget, not width or height, and "
                   "0 keeps each reference at its own size rounded to 32. Official default 1024, up "
                   "to 2048. Measured at 25 steps: 15.1s with one reference, 33.3s with two; a "
                   "1152x896 reference comes back 1152x896.",
        "map": QWEN_EDIT_MAP,
        "fields": ["prompt", "negative", "ref1", "ref2", "ref3", "ref4", "resolution",
                   "batch", "steps", "cfg", "seed"],
        "defaults": {"prompt": "<image1> on a seamless white studio sweep, soft key light, product "
                               "photography, nothing else in frame",
                     "negative": "", "ref1": "", "ref2": "", "ref3": "", "ref4": "",
                     "resolution": 1024, "batch": 1, "steps": 25, "cfg": 1.0, "seed": 42,
                     "sampler": "euler", "scheduler": "simple", "denoise": 1.0,
                     "unet": QWEN_UNET, "clip": QWEN_CLIP, "vae": QWEN_VAE},
        "verified": True, "model": "Qwen-Image 2.1 int8", "model_en": "Qwen-Image 2.1 int8",
        "spec": "跟 ref1 · 25步 · 15.1s",
        "timeout": 1800,
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


def _qwen_mode(g, template, merged):
    """Make the graph either generate or edit, and drop the reference slots nobody filled.

    ComfyUI validates *every* node it is handed, not just the ones that reach an output, so
    an unused LoadImage with an empty filename fails the whole submission as "value not in
    list" -- the slot has to leave the graph, not merely stay blank. With a reference
    present the canvas becomes that image's own latent (switch False) and the KV cache turns
    on, since reusing the prefix is what keeps an edit from drifting; with none, a fresh
    EmptyLatentImage and the cache ruled out (there is no prefix to keep).

    Only slots the template's own map declares count: a stray `ref1` in a generation call
    must not quietly turn it into an edit that skipped the edit checks.
    """
    live = 0
    for i, (field, node) in enumerate(QWEN_REFS.items(), start=1):
        if field in template["map"] and merged.get(field):
            live += 1
            continue
        g.pop(node, None)
        g["5"]["inputs"].pop(f"images.image_{i}", None)
    edit = live > 0
    g["7"]["inputs"]["switch"] = not edit
    g["4"]["inputs"]["device"] = "auto" if edit else "off"
    return edit


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
    if template["map"] in (QWEN_MAP, QWEN_EDIT_MAP):
        _qwen_mode(g, template, merged)
    return g


# The media inputs a previous step's output can be wired into, with the type the canvas
# matches on. ref2-4 are deliberately absent: they are extra references rather than the
# subject of the step, and the binding mechanism carries one picture per run, so offering
# them as sockets would advertise a wire the runner cannot pull.
BIND_IN = {"image": "image", "ref1": "image", "video": "video"}


def ports_of(t):
    """The sockets of a step, derived from the fields the form already renders.

    A template cannot advertise an input its own parameter panel has no control for, and
    adding a media field to a template gives it a port without editing the canvas.
    """
    return {"in": [{"name": f, "type": k} for f in t["fields"] if (k := BIND_IN.get(f))],
            "out": [{"name": t["media"], "type": t["media"]}]}


def public():
    """What the browser may show -- no node ids, no graph internals."""
    return [{"id": t["id"], "name": t["name"], "name_en": t["name_en"], "category": t["category"],
             "desc": t["desc"], "desc_en": t["desc_en"], "fields": t["fields"],
             "defaults": {k: v for k, v in t["defaults"].items() if k != "style"},
             "verified": t["verified"], "model": t["model"], "model_en": t["model_en"],
             "media": t["media"], "spec": t["spec"], "sizes": t.get("sizes"), "ports": ports_of(t),
             # The browser shows how long one attempt may take, so a step configured to
             # run nine times cannot be a surprise about how long that can cost.
             "timeout": t.get("timeout", 900)}
            for t in TEMPLATES]
