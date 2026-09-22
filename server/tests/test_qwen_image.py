"""Qwen-Image-2.1: one graph in two modes, and the weight set has to stay under the cap.

Two failures here are invisible from outside the engine. A reference slot left in the graph
with an empty filename does not degrade an edit -- ComfyUI validates every node it is handed,
so it refuses the whole submission. And a canvas off the model's 32-grid surfaces deep inside
the sampler as a latent-shape error. Both are pinned below, plus the memory arithmetic that
chose the w4a8 text encoder over the one the shipped template names.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app import runner, templates
from app.config import WORKFLOWS
from app.main import app

T2I = templates.BY_ID["qwen_image"]
EDIT = templates.BY_ID["qwen_image_edit"]

# /system_stats on this box reports ram_total 16634290176 = 15.5 GiB: the WSL2 default at
# half the 31.8 GiB host, with no .wslconfig. Byte arithmetic on the weight group predicts
# whether a run fits, which is what it was wrong about twice before.
CAP_GIB = 15.5
Q21_GIB = {"qwen_image_2.1_int8_convrot.safetensors": 6.76,
           "qwen3vl_8b_w4a8.safetensors": 5.88,
           "qwen_image_2.1_vae_bf16.safetensors": 0.63}


def test_the_registered_weight_group_fits_the_wsl_ceiling():
    total = sum(Q21_GIB.values())
    assert total < CAP_GIB, f"the trio is {total:.2f} GiB, over the {CAP_GIB} GiB cap"
    assert {t["defaults"][k] for t in (T2I, EDIT) for k in ("unet", "clip", "vae")} <= set(Q21_GIB)
    # The pairing the shipped official template names: int8 DiT + int8 encoder + VAE.
    assert 6.76 + 8.71 + 0.63 > CAP_GIB, "the int8 text encoder is the one that does not fit"


def test_the_registered_weights_are_the_ones_the_graph_loads():
    g = json.loads((WORKFLOWS / T2I["graph"]).read_text(encoding="utf-8"))
    for field in ("unet", "clip", "vae"):
        node, key = T2I["map"][field]
        assert g[node]["inputs"][key] == T2I["defaults"][field], f"{field} drifted"
    assert g["2"]["inputs"]["type"] == "qwen_image", "wrong CLIP role means wrong conditioning"


def test_generation_mode_drops_every_reference_slot():
    g = templates.graph_for(T2I, {"prompt": "a mug"})
    assert not [n for n in templates.QWEN_REFS.values() if n in g], "an empty LoadImage fails the submit"
    assert not [k for k in g["5"]["inputs"] if k.startswith("images.")]
    assert g["7"]["inputs"]["switch"] is True, "no reference: sample a fresh canvas"
    assert g["4"]["inputs"]["device"] == "off", "with no prefix there is nothing to cache"


def test_edit_mode_keeps_the_filled_reference_and_moves_the_canvas():
    g = templates.graph_for(EDIT, {"prompt": "<image1> on white", "ref1": "mug.png"})
    assert g["21"]["inputs"]["image"] == "mug.png"
    assert g["5"]["inputs"]["images.image_1"] == ["21", 0]
    assert "22" not in g and "images.image_2" not in g["5"]["inputs"]
    assert g["7"]["inputs"]["switch"] is False, "with a reference the canvas is image_1's own latent"
    assert g["4"]["inputs"]["device"] == "auto"


def test_a_stray_reference_cannot_drag_the_generation_template_into_edit_mode():
    g = templates.graph_for(T2I, {"prompt": "a mug", "ref1": "mug.png"})
    assert "21" not in g and g["7"]["inputs"]["switch"] is True


def test_batch_drives_both_modes_from_one_node():
    """RepeatLatentBatch sits downstream of the switch, so `batch` is live in edit mode too."""
    for tpl in (T2I, EDIT):
        g = templates.graph_for(tpl, {"prompt": "x", "ref1": "mug.png", "batch": 4})
        assert g["8"]["inputs"]["amount"] == 4, tpl["id"]
        assert g["10"]["inputs"]["latent_image"] == ["8", 0], tpl["id"]


def test_edit_refuses_to_queue_without_a_reference():
    with TestClient(app) as c:
        r = c.post("/tasks", json={"template": "qwen_image_edit", "prompt": "re-light it",
                                   "params": {}})
        assert r.status_code == 422, r.text
        assert "参考图" in r.text


@pytest.mark.parametrize("params", [{"width": 1000, "height": 1000},
                                    {"width": 2048, "height": 2176}])
def test_canvas_refused_before_the_engine_sees_it(params):
    """Off the 32-grid or over the 2K budget: refused here, not inside the sampler.

    Nothing in this file may reach a 202 without monkeypatching the queue -- an accepted
    task posts a real graph to the live engine, which is the measured run's job, not a
    unit test's.
    """
    with TestClient(app) as c:
        r = c.post("/tasks", json={"template": "qwen_image", "prompt": "a mug", "params": params})
        assert r.status_code == 422, f"{params} -> {r.status_code} {r.text}"


def test_resolution_off_the_budget_is_refused():
    with TestClient(app) as c:
        r = c.post("/tasks", json={"template": "qwen_image_edit", "prompt": "<image1> on white",
                                   "params": {"ref1": "mug.png", "resolution": 2112}})
        assert r.status_code == 422, r.text


def test_native_2k_is_accepted_and_recorded(monkeypatch):
    monkeypatch.setattr(runner.runner, "submit_task", lambda tid: 0)
    with TestClient(app) as c:
        r = c.post("/tasks", json={"template": "qwen_image", "prompt": "a mug",
                                   "params": {"width": 2048, "height": 2048}})
        assert r.status_code == 202, r.text
        row = c.get(f"/tasks/{r.json()['task_id']}").json()
    assert (row["params"]["width"], row["params"]["height"]) == (2048, 2048)
