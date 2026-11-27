import base64
import html
import re
from pathlib import Path

_HERE = Path(__file__).parent
_VENDOR = ("three.min.js", "GLTFLoader.js", "OrbitControls.js")


def write_viewer_html(glb_path, out_html, title):
    template = (_HERE / "template.html").read_text(encoding="utf-8")
    scripts = {}
    for name in _VENDOR:
        text = (_HERE / "vendor" / name).read_text(encoding="utf-8")
        if "</script" in text.lower():
            raise ValueError(f"{name} chứa '</script', không nhúng được vào HTML")
        scripts[name] = text
    values = {
        "__TITLE__": html.escape(str(title)),
        "__THREE__": scripts["three.min.js"],
        "__GLTF_LOADER__": scripts["GLTFLoader.js"],
        "__ORBIT__": scripts["OrbitControls.js"],
        "__GLB_B64__": base64.b64encode(Path(glb_path).read_bytes()).decode("ascii"),
    }
    # một lượt thay thế để nội dung script không bị quét lại tìm chỗ giữ chỗ
    page = re.sub("|".join(values), lambda m: values[m.group(0)], template)
    Path(out_html).write_text(page, encoding="utf-8")
