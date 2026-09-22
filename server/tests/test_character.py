"""S-character: the two figure workflows must assemble, and must refuse to run blind.

graph_for() silently skips a mapped node that is not in the graph, so a node id that
drifts during a graph rewrite would drop a parameter without any error anywhere. That
is what the first test pins: every field a template claims to drive must land somewhere.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.config import WORKFLOWS
from app.main import app
from app import templates


@pytest.mark.parametrize("tpl", templates.TEMPLATES, ids=[t["id"] for t in templates.TEMPLATES])
def test_every_mapped_field_lands_on_a_node_that_exists(tpl):
    g = json.loads((WORKFLOWS / tpl["graph"]).read_text(encoding="utf-8"))
    for field, (node, key) in tpl["map"].items():
        assert node in g, f'{tpl["id"]}: field {field!r} points at missing node {node}'
        assert key in g[node]["inputs"], f'{tpl["id"]}: node {node} has no input {key!r}'


def test_character_clip_is_a_portrait_canvas_on_the_models_frame_grid():
    """H3 stretches the first frame to the canvas, and only accepts 17k+5 frames."""
    d = templates.BY_ID["char_video"]["defaults"]
    assert d["width"] % 32 == 0 and d["height"] % 32 == 0, "canvas must be a multiple of 32"
    assert d["width"] * d["height"] <= 768 * 1344, "above the model's own pixel cap"
    assert d["length"] % 17 == 5, f'{d["length"]} frames is off the grid'


def test_reference_slot_is_the_form_the_engine_executes():
    """The autogrow reference is a dotted key holding a link, measured not read.

    Three spellings were tried against the live engine. A flat ``ref_image_0`` passes
    validation and then dies in execute with an unexpected keyword. A ``ref_images`` dict
    holding the link passes validation AND runs -- and silently drops the reference: the
    engine's cache shows LoadImage never executed, and swapping in a different figure
    returns the same clip from cache. Only the dotted key re-computes per reference.
    """
    g = json.loads((WORKFLOWS / "h3_char_ref2v.json").read_text(encoding="utf-8"))
    link = g["6"]["inputs"].get("ref_images.ref_image_0")
    assert link == ["5", 0], f"reference must be a dotted link, got {link!r}"
    for dead in ("ref_image_0", "ref_images"):
        assert dead not in g["6"]["inputs"], f"{dead} is the form that validates but ignores it"


def test_figure_prompt_carries_the_anatomy_suffix():
    """The style string is part of the measured prompt, so it must reach the node."""
    tpl = templates.BY_ID["char_portrait"]
    g = templates.graph_for(tpl, {"prompt": "a young man standing"})
    assert "five separate fingers" in g["4"]["inputs"]["text"]


def test_clip_refuses_to_queue_without_a_figure():
    """An unbound image would fail inside the engine as 'image not in list'."""
    with TestClient(app) as c:
        r = c.post("/tasks", json={"template": "char_video", "prompt": "turns to camera",
                                   "params": {}})
        assert r.status_code == 422, r.text
        assert "图" in r.text
