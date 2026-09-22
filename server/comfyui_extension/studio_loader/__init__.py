"""Studio loader: lets the comfy-ui-workflow desk app open a workflow on this canvas.

No nodes here. The pack exists to publish ``web_extensions/studio_load.js``; ComfyUI's
loader still refuses a package that declares neither a node mapping nor an entry point
(nodes.py:2295 checks for the attribute, so an empty mapping is enough), and the empty
dict is what that check wants.

The desk app writes the workflow into this server's own ``workflows/studio/`` through
ComfyUI's userdata API, then posts its path to the tab -- so the fetch stays same-origin
and nothing in ComfyUI needs a CORS exception. Without this pack the feature degrades by
one click: the file still shows up under the Workflow menu.
"""

WEB_DIRECTORY = "./web_extensions"
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
__version__ = "0.1.0"
