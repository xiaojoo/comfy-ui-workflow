"""The workflow file ComfyUI's own desktop opens, rebuilt from the graphs we submit.

``icon-pipeline/workflows/*.json`` are API format: node id -> class_type + inputs. That is
what ``POST /prompt`` takes and nothing else. The desktop wants UI format -- node positions,
per-node widget order, explicit link records -- and handed an API file it has to invent all
three, which is why a graph that renders here in 9.1 s lands over there as a pile of
overlapping nodes with red loaders.

Slot order and widget order are the engine's fact, read from its /object_info, not a table
kept here: a combo list changes the moment someone adds a weight, and an export that
hard-coded the old one would mislabel the file it claims to reproduce. The definitions are
cached to disk so the detail panel still shows last known good JSON while the engine is down.

Three quirks make this more than a key rename, each measured against the installed 1.53.6
frontend serialising the same nine graphs (.probe/oracle/):
  * a widget whose spec says ``control_after_generate`` stores an extra value after itself
    ("fixed"/"randomize") that gets no row of its own in the node's input list;
  * a combo that uploads a file gains a companion ``upload`` row holding the literal
    "image" -- that is the desktop's Choose File button (``image_upload`` on LoadImage,
    ``video_upload`` on LoadVideo);
  * v3 dynamic combos (SaveVideo's container picker) and autogrow rows (the Qwen encoder's
    reference images) expand into dotted names: ``format.codec`` is a widget of its parent,
    ``images.image_1`` is a connection of its row.

A widget can also carry a wire at once (CreateVideo's ``fps`` fed from GetVideoComponents):
the row stays in the widget block, keeps its default as its stored value, and the link rides
on it. Getting that wrong shifts every value after it.
"""

import json

from fastapi import HTTPException

from . import comfy, templates
from .config import WORK

CACHE = WORK / "object_info.json"

# Types that render as a widget rather than a wire. Any other all-caps name is a socket type,
# and a comma-joined union ("MESH,FILE_3D_GLB,...") is one socket that accepts many types.
WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO", "CUSTOMWIDGET", "SECRET",
                "IMAGEUPLOAD", "AUDIOUPLOAD", "COLOR", "PREVIEW_3D", "COMFY_DYNAMICCOMBO_V3"}

_state = {"defs": None, "source": None}


def defs(force=False):
    """The engine's node specs and where they came from: ("engine"|"cache", defs).

    The engine is always asked first, so a node added ten minutes ago is in the next export.
    The cache only speaks when it cannot be reached at all.
    """
    if _state["defs"] and not force:
        return _state["source"], _state["defs"]
    try:
        got = comfy._get("/object_info")
    except Exception:
        if not _state["defs"] and CACHE.exists():
            _state["defs"] = json.loads(CACHE.read_text(encoding="utf-8"))
        if not _state["defs"]:
            raise RuntimeError("导出要读 ComfyUI 的节点定义，但引擎没应答：启动 8188 再导出")
        return "cache", _state["defs"]
    WORK.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(got), encoding="utf-8")
    _state.update(defs=got, source="engine")
    return "engine", got


class Slot:
    """One input of a node, as the desktop sees it: a wire, a widget row, or -- for the seed
    control -- a stored value with no row."""

    def __init__(self, name, head, opts, optional, conn):
        self.name = name
        self.head, self.opts = head, opts
        self.type = head if isinstance(head, str) else "COMBO"
        self.optional, self.conn = optional, conn
        self.row = True           # False only for control_after_generate
        self.link = None
        self.source_type = None

    @property
    def widget(self):
        return not self.conn

    @property
    def display(self):
        """The key this value is filed under: the seed control drops its owner's name."""
        return "control_after_generate" if self.name.endswith("#cag") else self.name


def _spec_of(info):
    """(type-or-option-list, options dict) from one input spec."""
    head = info[0] if isinstance(info, list) and info else info
    d = info[1] if isinstance(info, list) and len(info) > 1 and isinstance(info[1], dict) else {}
    return head, d


def _options(head, d):
    """The choices of a combo, in whichever shape this engine reports them: a classic combo
    carries its list as the type, a v3 schema under ``options``."""
    if isinstance(head, list):
        return head
    opts = d.get("options")
    if isinstance(opts, list) and opts and isinstance(opts[0], dict):
        return [o.get("key") for o in opts]
    return opts if isinstance(opts, list) else None


def _default(head, d):
    if "default" in d:
        return d["default"]
    opts = _options(head, d)
    if opts:
        return opts[0]
    return {"INT": 0, "FLOAT": 0.0, "BOOLEAN": False}.get(head if isinstance(head, str) else "", "")


def _ref(value):
    """The shape a wire takes in an API prompt, before anyone is asked whether it exists."""
    return isinstance(value, list) and len(value) == 2 and isinstance(value[1], int)


def _wire(value, graph):
    """A submitted input names a wire exactly when it is another node of this graph plus a slot."""
    return _ref(value) and bool(graph) and str(value[0]) in graph


def _flatten(spec, optional, api, out):
    """Append one input group's slots in engine order, expanding what the definition nests."""
    for name, info in (spec or {}).items():
        head, d = _spec_of(info)

        if head == "COMFY_AUTOGROW_V3":
            tmpl = d.get("template") or {}
            inner = (tmpl.get("input") or {}).get("required") or {}
            row_head, row_d = _spec_of(next(iter(inner.values()), ["IMAGE", {}]))
            names = tmpl.get("names") or [f"{tmpl.get('prefix', name)}{i}" for i in range(tmpl.get("max") or 1)]
            live = [n for n in names if f"{name}.{n}" in api]
            # One row past what the graph fills, and never zero: the desktop always leaves a
            # free socket to drop the next reference into.
            want = min(max(len(live) + 1, int(tmpl.get("min") or 0), 1), len(names))
            for n in names[:want]:
                out.append(Slot(f"{name}.{n}", row_head, row_d, True,
                                not (isinstance(row_head, str) and row_head in WIDGET_TYPES)))
            continue

        out.append(Slot(name, head, d, optional,
                        isinstance(head, str) and head not in WIDGET_TYPES))
        if out[-1].conn:
            continue
        if d.get("control_after_generate"):
            cag = Slot(f"{name}#cag", "COMBO", {"options": ["fixed", "increment", "decrement",
                                                            "randomize", "random range"]},
                       optional, False)
            cag.row = False
            out.append(cag)
        if any(v for k, v in d.items() if k.endswith("_upload")):
            # The desktop's Choose File button, whatever it uploads: image_upload on
            # LoadImage, video_upload on LoadVideo. Always the literal "image".
            out.append(Slot("upload", "IMAGEUPLOAD", {}, optional, False))
        if isinstance(head, str) and head.startswith("COMFY_DYNAMICCOMBO") \
                and isinstance(d.get("options"), list):
            chosen = api.get(name) if api.get(name) in _options(head, d) else _default(head, d)
            child = next((o for o in d["options"] if isinstance(o, dict) and o.get("key") == chosen), None)
            if child:
                for grp, opt in (("required", False), ("optional", True)):
                    nested = (child.get("inputs") or {}).get(grp) or {}
                    _flatten({f"{name}.{k}": v for k, v in nested.items()}, opt, api, out)


def _slots(node, cdef):
    """A node's inputs in desktop order: wires first, then widgets, each group as defined.

    ``input_order`` is consulted because a v3 node's dict order is whatever its class
    happened to build, while the desktop numbers sockets from the order it announces.
    """
    api, out = node.get("inputs") or {}, []
    info = cdef.get("input") or {}
    for grp in ("required", "optional"):
        spec = info.get(grp) or {}
        announced = (cdef.get("input_order") or {}).get(grp)
        if announced:
            ordered = {k: spec[k] for k in announced if k in spec}
            ordered.update({k: v for k, v in spec.items() if k not in announced})
            spec = ordered
        _flatten(spec, grp == "optional", api, out)
    return [s for s in out if s.conn] + [s for s in out if not s.conn]


def _value(slot, api):
    name = slot.name
    if name in api and not _ref(api[name]):
        return api[name]
    if name.endswith("#cag"):
        base = name[:-4]
        return api.get(base + "_control_after_generate") or api.get("control_after_generate") or "fixed"
    if name == "upload":
        return api.get("upload") or "image"
    return _default(slot.head, slot.opts)


def _size(slots):
    wide = any(s.head == "STRING" and s.opts.get("multiline") for s in slots)
    return [400 if wide else 270, max(58, 34 + 18 * (len(slots) + 1))]


def to_workflow(graph, defs_=None):
    """UI format: the same nodes, wires and values the runner is about to hand the engine."""
    defs_ = defs_ if defs_ is not None else defs()[1]
    order = _order(graph)
    for nid in order:
        cls = _cls(graph, nid)
        if cls not in defs_:
            raise RuntimeError(f"引擎里没有 {cls} 这个节点，导出的图在它那里打不开")
    every = {nid: _slots(graph[nid], defs_[_cls(graph, nid)]) for nid in order}
    # Only the rows the desktop paints take part in slot numbering: the seed control stores a
    # value without claiming a row, and counting it would shift every wire after it.
    rows_of = {nid: [s for s in every[nid] if s.row] for nid in order}
    links, next_link, produced = [], 1, {}

    for nid in order:
        api = graph[nid].get("inputs") or {}
        for s in rows_of[nid]:
            v = api.get(s.name)
            if not _wire(v, graph):
                continue
            src, oslot = str(v[0]), v[1]
            out_types = defs_[_cls(graph, src)].get("output") or []
            stype = out_types[oslot] if oslot < len(out_types) else s.type
            s.link, s.source_type = next_link, stype
            produced.setdefault((src, oslot), []).append(next_link)
            links.append([next_link, int(src), oslot, int(nid), rows_of[nid].index(s), stype])
            next_link += 1

    nodes = []
    for nid in order:
        cdef = defs_[_cls(graph, nid)]
        api = graph[nid].get("inputs") or {}
        rows = rows_of[nid]

        def typed(slot):
            """A match-type row reports the type its wire actually carries: the desktop will
            not connect a LATENT into a row still labelled COMFY_MATCHTYPE_V3."""
            if not slot.type.startswith("COMFY_MATCHTYPE"):
                return slot.type
            tid = (slot.opts.get("template") or {}).get("template_id")
            for other in rows:
                if other.conn and getattr(other, "source_type", None) and (tid is None or
                        (other.opts.get("template") or {}).get("template_id") == tid):
                    return other.source_type
            return "*"

        inputs = []
        for s in rows:
            row = {"name": s.name, "type": typed(s)}
            if s.optional:
                row["shape"] = 7
            if s.widget:
                row["widget"] = {"name": s.display}
            row["link"] = s.link
            inputs.append(row)
        widgets = [(s, _value(s, api)) for s in every[nid] if s.widget]
        types = cdef.get("output") or []
        names = cdef.get("output_name") or types
        match = cdef.get("output_matchtypes") or []
        outputs = []
        for i in range(len(types)):
            t = types[i]
            if t.startswith("COMFY_MATCHTYPE"):
                t = next((typed(s) for s in rows if s.conn and
                          (i >= len(match) or (s.opts.get("template") or {}).get("template_id") == match[i])
                          and getattr(s, "source_type", None)), "*")
            outputs.append({"name": names[i], "type": t, "links": produced.get((nid, i)) or None})
        node = {"id": int(nid), "type": _cls(graph, nid), "pos": [0, 0], "size": _size(every[nid]),
                "flags": {}, "order": order.index(nid), "mode": 0, "inputs": inputs,
                "outputs": outputs,
                "properties": {"Node name for S&R": _cls(graph, nid)} if cdef.get("output_name") else {}}
        # A node with nothing to type holds no widget list at all -- the desktop writes the
        # key only when there is one, and an empty list reads as a widget row to be filled.
        if widgets:
            node["widgets_values"] = [v for _, v in widgets]
            node["widgets_values_named"] = {s.display: v for s, v in widgets}
        nodes.append(node)

    _place(nodes, graph)
    return {"last_node_id": max(int(n) for n in graph), "last_link_id": next_link - 1,
            "nodes": nodes, "links": links, "groups": [], "config": {},
            "extra": {"ds": {"scale": 1, "offset": [0, 0]}}, "version": 0.4}


def push(tpl_id, params=None):
    """Write this row's file into the engine's own workflows dir, for one-click opening.

    The desk page cannot reach into the ComfyUI tab (different origin), and the frontend has
    no "open this workflow" URL, so the file goes where ComfyUI already keeps workflows and
    the tab's own loader picks it up from there. Same-origin for ComfyUI, no CORS anywhere.
    """
    wf = for_template(tpl_id, params, "ui")
    path = comfy.put_workflow(f"workflows/{PUSH_DIR}/{tpl_id}.json", json.dumps(wf["workflow"]))
    return {k: wf[k] for k in ("template", "name", "nodes", "links", "unfilled", "filename", "defs_from")} | \
        {"path": path, "comfy_url": comfy.COMFY + "/"}


def _cls(graph, nid):
    return graph[nid]["class_type"]


# The sub-folder the pushed files land in, inside ComfyUI's own workflows dir.
PUSH_DIR = "studio"


# The panel's file-and-picture knobs. Empty ones are worth naming in the export response:
# an empty picker in ComfyUI is a step the person still has to take, not a broken file.
MEDIA_FIELDS = ("image", "video", "ref1", "ref2", "ref3", "ref4")


def for_template(tpl_id, params=None, fmt="ui"):
    """One row of the workflow list as a file: the same graph the runner would submit.

    ``ui`` is what the desktop opens by dragging it onto the canvas; ``api`` is the body
    POST /prompt takes, offered beside it because that is literally what this app sends and
    the two files are read very differently by a person debugging a node.
    """
    tpl = templates.BY_ID.get(tpl_id)
    if tpl is None:
        raise HTTPException(422, f"没有这条工作流：{tpl_id!r}")
    merged = {**tpl["defaults"], **(params or {})}
    graph = templates.graph_for(tpl, merged)
    source = None
    if fmt == "api":
        wf = graph
        nodes = len(graph)
        links = sum(1 for n in graph.values() for v in (n.get("inputs") or {}).values() if _wire(v, graph))
    else:
        source, d = defs()
        wf = to_workflow(graph, d)
        nodes, links = len(wf["nodes"]), len(wf["links"])
    return {"template": tpl["id"], "name": tpl["name"], "graph_file": tpl["graph"], "format": fmt,
            "defs_from": source, "nodes": nodes, "links": links,
            "unfilled": [f for f in tpl["fields"] if f in MEDIA_FIELDS and not merged.get(f)],
            "filename": f"{tpl['id']}{'' if fmt == 'ui' else '-api'}.json", "workflow": wf}


def _order(graph):
    """Parents before children, ties by authored id, so the file reads left to right."""
    done, out = set(), []
    for nid in sorted(graph, key=lambda k: (len(k), k)):
        _visit(nid, graph, done, out)
    return out


def _visit(nid, graph, done, out):
    if nid in done:
        return
    done.add(nid)
    for v in (graph[nid].get("inputs") or {}).values():
        if _wire(v, graph):
            _visit(str(v[0]), graph, done, out)
    out.append(nid)


def _place(nodes, graph):
    """Layered left-to-right layout. Coordinates are cosmetic, but stacking ten nodes on one
    point is the exact complaint this module exists to answer, so the bar is that no two node
    rectangles overlap -- not that they match any particular pixel."""
    depth = {}
    for n in sorted(nodes, key=lambda x: x["order"]):
        srcs = [str(v[0]) for v in (graph[str(n["id"])].get("inputs") or {}).values() if _wire(v, graph)]
        depth[n["id"]] = 1 + max((depth[int(s)] for s in srcs), default=-1)
    columns = {}
    for n in nodes:
        columns.setdefault(depth[n["id"]], []).append(n)
    x = 100
    for level in sorted(columns):
        y = 130
        widest = 270
        for n in sorted(columns[level], key=lambda x: x["id"]):
            n["pos"] = [x, y]
            y += n["size"][1] + 32
            widest = max(widest, n["size"][0])
        x += widest + 100
