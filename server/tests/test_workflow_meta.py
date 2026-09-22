"""Row appearance: a name, a note, and a cover that is its own file.

The cover is uploaded, copied into work/covers, and served back from there -- so what is
asserted here is that the bytes stored are the bytes sent, that the magic number rather than
the filename decides what counts as an image, and that a row with no pinned cover still gets
one from its own newest picture.
"""

import base64

import pytest
from fastapi.testclient import TestClient

from app import workflow_meta as wm
from app.db import Session
from app.main import app
from app.models import Task

PNG = b"\x89PNG\r\n\x1a\n" + b"a" * 40
JPG = b"\xff\xd8\xff" + b"b" * 40
STUDIO = ("output", "studio")


@pytest.fixture
def root(tmp_path, monkeypatch):
    """A stand-in engine output directory, and the directory covers get copied into."""
    out = tmp_path.joinpath(*STUDIO)
    out.mkdir(parents=True)
    (out / "icon_00001_.png").write_bytes(PNG)
    (out / "icon_00002_.png").write_bytes(PNG)
    monkeypatch.setattr(wm, "COVERS", tmp_path / "covers")
    return tmp_path


@pytest.fixture
def run(client):
    """One finished generation with two pictures, as the runner records it."""
    with Session() as s:
        t = Task(template="icon_flat", state="done", params={},
                 outputs=[{"subfolder": "studio", "filename": "icon_00001_.png"},
                          {"subfolder": "studio", "filename": "icon_00002_.png"}])
        s.add(t)
        s.commit()
        return t.id


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def row_of(client, tpl="icon_flat"):
    return next(x for x in client.get("/templates").json()["templates"] if x["id"] == tpl)


def upload(client, tpl, data, filename="cover.png"):
    body = {"filename": filename, "image": "data:image/png;base64," + base64.b64encode(data).decode()}
    return client.post(f"/workflow/{tpl}/cover", json=body)


def test_name_and_note_override_both_languages_and_fall_back_when_cleared(client):
    before = row_of(client)
    assert before["name"] == "企业图标生成" and before["name_en"] == "Enterprise icon"

    r = client.put("/workflow/icon_flat/meta", json={"name": "我的图标线", "desc": "只给内部工具用"})
    assert r.status_code == 200, r.text
    after = row_of(client)
    # One field, two languages: the row is the person's own label, not a translation target.
    assert after["name"] == after["name_en"] == "我的图标线"
    assert after["desc"] == after["desc_en"] == "只给内部工具用"
    assert after["custom"] == {"name": "我的图标线", "desc": "只给内部工具用"}

    client.put("/workflow/icon_flat/meta", json={"name": "", "desc": ""})
    back = row_of(client)
    assert (back["name"], back["desc"]) == (before["name"], before["desc"])


def test_unknown_row_and_overlong_text_are_refused(client):
    assert client.put("/workflow/nope/meta", json={"name": "x"}).status_code == 422
    assert client.put("/workflow/icon_flat/meta", json={"name": "x" * 61}).status_code == 422
    assert client.put("/workflow/icon_flat/meta", json={"desc": "x" * 401}).status_code == 422


def test_an_uploaded_cover_is_stored_as_its_own_bytes(client, root, run):
    r = upload(client, "icon_flat", JPG, "whatever.png")     # a JPEG named .png
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cover"].startswith("/covers/icon_flat?v=") and body["type"] == "jpg"
    assert row_of(client)["cover_pinned"] is True
    stored = root / "covers" / "icon_flat.jpg"
    assert stored.read_bytes() == JPG
    got = client.get("/covers/icon_flat")
    assert got.status_code == 200 and got.content == JPG


def test_replacing_a_cover_leaves_no_orphan_behind(client, root, run):
    assert upload(client, "icon_flat", JPG).status_code == 200
    upload(client, "icon_flat", PNG)
    assert [p.name for p in (root / "covers").iterdir()] == ["icon_flat.png"]


def test_a_cleared_cover_falls_back_to_the_rows_newest_picture(client, root, run):
    upload(client, "icon_flat", PNG)
    assert client.delete("/workflow/icon_flat/cover").status_code == 200
    assert not list((root / "covers").glob("icon_flat.*"))
    row = row_of(client)
    assert row["cover_pinned"] is False and row["cover"].startswith("/comfy/view?")
    assert "icon_00001_.png" in row["cover"]
    assert client.get("/covers/icon_flat").status_code == 404


def test_pinning_one_row_does_not_touch_another(client, root, run):
    upload(client, "icon_flat", PNG)
    other = row_of(client, "char_portrait")
    assert other["cover_pinned"] is False
    assert not (other["cover"] or "").startswith("/covers/")


def test_the_magic_number_decides_not_the_filename(client, root, run):
    r = upload(client, "icon_flat", b"just a text file, honestly", "sneaky.png")
    assert r.status_code == 422 and "PNG" in r.json()["detail"]
    assert not (root / "covers").exists() or not list((root / "covers").glob("icon_flat.*"))


def test_an_oversized_upload_is_refused_before_it_is_written(client, root, run):
    r = upload(client, "icon_flat", PNG + b"x" * wm.MAX_BYTES)
    assert r.status_code == 422 and "8 MB" in r.json()["detail"]
    assert not (root / "covers").exists() or not list((root / "covers").glob("icon_flat.*"))


def test_uploading_the_same_filename_twice_still_moves_the_url(client, root, run):
    first = upload(client, "icon_flat", PNG).json()["cover"]
    again = upload(client, "icon_flat", PNG + b"more bytes").json()["cover"]
    assert first != again, "同样的文件名同样的扩展名，URL 不动就是让浏览器继续画旧图"


def test_a_pinned_cover_whose_file_vanished_falls_back(client, root, run):
    upload(client, "icon_flat", PNG)
    (root / "covers" / "icon_flat.png").unlink()      # work/ is disposable; the row is not
    row = row_of(client)
    assert row["cover_pinned"] is False and row["cover"].startswith("/comfy/view?")


def test_a_body_that_is_not_an_image_payload_is_refused(client, root, run):
    assert client.post("/workflow/icon_flat/cover",
                       json={"filename": "a.png", "image": "data:image/png," + "AAAA"}).status_code == 422
    assert client.post("/workflow/icon_flat/cover",
                       json={"filename": "a.png", "image": "data:image/png;base64!!!"}).status_code == 422


def test_only_a_known_row_can_have_a_cover(client, root, run):
    assert upload(client, "no_such_row", PNG).status_code == 422
    assert client.delete("/workflow/no_such_row/cover").status_code == 422
