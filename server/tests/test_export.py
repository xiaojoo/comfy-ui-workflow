"""Export: the four things that make ComfyUI's file format not a key rename.

Every rule here was measured against the installed frontend serialising the shipped graphs
(.probe/export_check.py diffs all nine). What that diff cannot pin down is the arithmetic of
the widget list: the seed control storing a value without claiming a row, the upload button
being a widget of its own, autogrow rows running one past what the graph fills, a match-type
row reporting the type its wire carries. Get any of them wrong and every value after it
shifts one place -- the file still opens, and quietly feeds the engine the wrong numbers.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app import comfy_export, templates
from app.main import app

DEFS = {
    "UNETLoader": {"input": {"required": {"unet_name": [["m.safetensors"], {}]}}, "output": ["MODEL"]},
    "ClipLoader": {"input": {"required": {"clip_name": [["qwen.safetensors"], {}]}}, "output": ["CLIP"]},
    "VAELoader": {"input": {"required": {"vae_name": [["v.safetensors"], {}]}}, "output": ["VAE"]},
    "EmptyLatentImage": {"input": {"required": {"width": ["INT", {"default": 1024}],
                                                "height": ["INT", {"default": 1024}]}},
                         "output": ["LATENT"], "output_name": ["LATENT"]},
    "LoadImage": {"input": {"required": {"image": [["a.png", "b.png"], {"image_upload": True}]}},
                  "output": ["IMAGE", "MASK"], "output_name": ["IMAGE", "MASK"]},
    "Encoder": {"input": {"required": {"clip": ["CLIP", {}], "text": ["STRING", {"multiline": True}],
                                       "imgs": ["COMFY_AUTOGROW_V3", {"template": {
                                           "input": {"required": {"image": ["IMAGE", {}]}},
                                           "names": ["image_1", "image_2"], "min": 0}}]}},
                "output": ["CONDITIONING"], "output_name": ["cond"]},
    "KSampler": {"input": {"required": {"model": ["MODEL", {}],
                                        "seed": ["INT", {"default": 0, "max": 10,
                                                         "control_after_generate": True}],
                                        "steps": ["INT", {"default": 20}],
                                        "positive": ["CONDITIONING", {}], "latent": ["LATENT", {}]},
                 "optional": {"noise": ["COMFY_MATCHTYPE_V3", {"template": {"template_id": "n",
                                                                            "allowed_types": "*"}}]}},
     "output": ["LATENT"], "output_name": ["LATENT"]},
    "VAEDecode": {"input": {"required": {"samples": ["LATENT", {}], "vae": ["VAE", {}]}},
                  "output": ["IMAGE"]},
}

GRAPH = {
    "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
    "2": {"class_type": "ClipLoader", "inputs": {"clip_name": "qwen.safetensors"}},
    "3": {"class_type": "LoadImage", "inputs": {"image": "b.png", "upload": "image"}},
    "4": {"class_type": "Encoder", "inputs": {"clip": ["2", 0], "text": "a gear", "imgs.image_1": ["3", 0]}},
    "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["4", 0], "latent": ["7", 0],
                                               "seed": 7, "steps": 4, "noise": ["3", 0]}},
    "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["8", 0]}},
    "7": {"class_type": "EmptyLatentImage", "inputs": {"width": 64, "height": 64}},
    "8": {"class_type": "VAELoader", "inputs": {"vae_name": "v.safetensors"}},
}


def built():
    return comfy_export.to_workflow(GRAPH, DEFS)


def by_type(wf, cls):
    return next(n for n in wf["nodes"] if n["type"] == cls)


def names(node):
    return [r["name"] for r in node["inputs"]]


def test_seed_control_stores_a_value_without_a_row():
    ks = by_type(built(), "KSampler")
    assert "seed#cag" not in names(ks)
    assert ks["widgets_values"] == [7, "fixed", 4]
    assert ks["widgets_values_named"]["control_after_generate"] == "fixed"


def test_upload_button_is_its_own_widget_row():
    li = by_type(built(), "LoadImage")
    assert names(li) == ["image", "upload"]
    assert li["widgets_values"] == ["b.png", "image"]


def test_autogrow_leaves_one_free_row_and_keeps_wires_in_the_wire_block():
    enc = by_type(built(), "Encoder")
    assert names(enc) == ["clip", "imgs.image_1", "imgs.image_2", "text"]
    assert enc["inputs"][2]["link"] is None
    assert enc["inputs"][2]["shape"] == 7
    assert enc["widgets_values"] == ["a gear"]


def test_matchtype_row_reports_the_type_its_wire_carries():
    ks = by_type(built(), "KSampler")
    noise = next(r for r in ks["inputs"] if r["name"] == "noise")
    assert noise["type"] == "IMAGE", "还写着 schema 名的话，桌面端会拒绝这根线"
    assert noise["link"] is not None
    assert ks["outputs"][0]["type"] == "LATENT"


def test_a_node_with_nothing_to_type_carries_no_widget_list():
    assert "widgets_values" not in by_type(built(), "VAEDecode")


def test_every_wire_arrives_at_the_row_the_file_names():
    wf = built()
    links = {l[0]: l for l in wf["links"]}
    byid = {n["id"]: n for n in wf["nodes"]}
    wired = 0
    for n in wf["nodes"]:
        for i, row in enumerate(n["inputs"]):
            if row["link"] is None:
                continue
            src = links[row["link"]]
            assert (src[3], src[4]) == (n["id"], i), f"{n['type']}.{row['name']} 的线指向了别的槽"
            assert byid[src[1]]["outputs"][src[2]]["type"] == row["type"]
            wired += 1
    assert wired == 8


def test_no_two_nodes_share_ground():
    wf = built()
    boxes = [(n["pos"][0], n["pos"][1], n["pos"][0] + n["size"][0], n["pos"][1] + n["size"][1])
             for n in wf["nodes"]]
    assert all(a[0] >= b[2] or b[0] >= a[2] or a[1] >= b[3] or b[1] >= a[3]
               for i, a in enumerate(boxes) for b in boxes[i + 1:])


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(comfy_export, "defs", lambda force=False: ("engine", DEFS))


def test_export_endpoint_hands_the_panel_parameters_to_the_graph(patched, monkeypatch):
    seen = {}

    def fake_graph_for(tpl, params):
        seen.update(params)
        return dict(GRAPH)

    monkeypatch.setattr(templates, "graph_for", fake_graph_for)
    with TestClient(app) as c:
        r = c.post("/workflow/export", json={"template": "icon_flat", "params": {"seed": 9}})
        assert r.status_code == 200, r.text
        body = r.json()
        assert (body["filename"], body["format"], body["defs_from"]) == ("icon_flat.json", "ui", "engine")
        assert (body["nodes"], body["links"]) == (8, 8)
        assert body["unfilled"] == []
        # What the drawer holds, defaults included -- the file is the graph this row submits.
        assert (seen["seed"], seen["steps"], seen["unet"]) == (9, 8, "z_image_turbo_int8_convrot.safetensors")
        # ...and that value reaches the widget list, on the row the desktop reads.
        ks = next(n for n in body["workflow"]["nodes"] if n["type"] == "KSampler")
        assert ks["widgets_values_named"]["seed"] == 7

        # A row whose picture is still unset says so, rather than shipping a red node quietly.
        assert c.post("/workflow/export", json={"template": "upscale_image"}).json()["unfilled"] == ["image"]


def test_export_endpoint_refuses_rows_that_are_not_there(patched):
    with TestClient(app) as c:
        assert c.post("/workflow/export", json={"template": "no_such_row"}).status_code == 422
        assert c.post("/workflow/export", json={"template": "icon_flat", "format": "xml"}).status_code == 422


def test_push_hands_the_engine_a_file_its_own_menu_can_list(patched, monkeypatch):
    saved = {}
    monkeypatch.setattr(templates, "graph_for", lambda tpl, params: dict(GRAPH))
    monkeypatch.setattr(comfy_export.comfy, "put_workflow",
                        lambda path, body: saved.update(path=path, wf=json.loads(body))
                        or path.replace("/", "%2F"))

    out = comfy_export.push("icon_flat", {"seed": 9})

    # The sub-directory rides inside the name because ?dir= is ignored on write (measured).
    assert saved["path"] == "workflows/studio/icon_flat.json"
    assert out["path"] == "workflows%2Fstudio%2Ficon_flat.json"
    assert out["comfy_url"].endswith(":8188/")
    assert [n["type"] for n in saved["wf"]["nodes"]][:2] == ["UNETLoader", "ClipLoader"]
    assert out["nodes"] == len(saved["wf"]["nodes"])
