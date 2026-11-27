import json
import re
from pathlib import Path

_HERE = Path(__file__).parent
_VENDOR = ("three.min.js", "GLTFLoader.js", "OrbitControls.js")


def json_for_script(value) -> str:
    """JSON an toàn để nhúng trong <script>: không còn '<', '>', '&', U+2028/2029 nguyên dạng."""
    text = json.dumps(value, ensure_ascii=True)
    esc = {"<": "\\u003c", ">": "\\u003e", "&": "\\u0026"}
    for ch, rep in esc.items():
        text = text.replace(ch, rep)
    return text


def load_editor_html(token) -> str:
    template = (_HERE / "editor.html").read_text(encoding="utf-8")
    scripts = {}
    for name in _VENDOR:
        text = (_HERE / "vendor" / name).read_text(encoding="utf-8")
        if "</script" in text.lower():
            raise ValueError(f"{name} chứa '</script', không nhúng được vào HTML")
        scripts[name] = text
    values = {
        "__TOKEN__": json_for_script(str(token)),
        "__THREE__": scripts["three.min.js"],
        "__GLTF_LOADER__": scripts["GLTFLoader.js"],
        "__ORBIT__": scripts["OrbitControls.js"],
    }
    # một lượt thay thế để nội dung script không bị quét lại tìm chỗ giữ chỗ
    return re.sub("|".join(values), lambda m: values[m.group(0)], template)
