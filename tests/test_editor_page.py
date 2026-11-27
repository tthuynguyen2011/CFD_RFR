import json
import re

import pytest

from odu_cfd.viewer.editor_page import load_editor_html

NASTY = "a\"b'c</script><b>&amp;\\x  "


def test_page_is_self_contained():
    html = load_editor_html("tok")
    assert not re.search(r'(src|href)\s*=\s*["\']https?:', html)
    assert "<script src" not in html and "<link" not in html
    assert "REVISION" in html and "THREE.GLTFLoader" in html and "OrbitControls" in html
    assert "window.EditorAPI" in html and "selftest" in html
    assert 'lang="vi"' in html and '<meta charset="utf-8">' in html


def test_placeholders_are_replaced():
    html = load_editor_html("tok")
    # (three.min.js tự có 'window.__THREE__', nên chỉ kiểm các chỗ giữ chỗ của mẫu)
    assert "__TOKEN__" not in html and "__GLTF_LOADER__" not in html and "__ORBIT__" not in html
    assert "<script>__THREE__</script>" not in html


def test_editorapi_exposes_required_functions():
    html = load_editor_html("tok")
    for name in ("addOdu", "moveOdu", "rotateOdu", "setOdu", "deleteOdu", "duplicateOdu", "undo", "redo",
                 "snapPoint", "snapAngle", "validate", "save", "toggleBalcony"):
        assert re.search(rf"\b{name}\b\s*:", html), name


def test_no_blocking_dialogs_and_no_innerhtml():
    html = load_editor_html("tok")
    own = html[html.index("const TOKEN"):]  # phần mã của trang, không gồm thư viện vendor
    for bad in ("window.alert", "window.prompt", "window.confirm", " alert(", " prompt(", " confirm(", "innerHTML",
                "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert bad not in own, bad


def test_token_is_embedded_as_safe_json_literal():
    html = load_editor_html(NASTY)
    m = re.search(r"const TOKEN = (.*?);\r?\n", html)
    assert m
    literal = m.group(1)
    assert json.loads(literal) == NASTY
    assert "<" not in literal and ">" not in literal and "&" not in literal
    assert " " not in literal and " " not in literal


def test_special_token_does_not_break_script_structure():
    plain = load_editor_html("tok")
    nasty = load_editor_html(NASTY)
    for tag in ("<script>", "</script>", "<style>", "</style>"):
        assert nasty.count(tag) == plain.count(tag), tag
    assert "<b>&amp;" not in nasty  # token không xuất hiện thô trong HTML
    assert len(re.findall(r"</script", nasty, re.I)) == len(re.findall(r"<script", nasty, re.I))


def test_vendor_script_cannot_inject_placeholders():
    # nội dung vendor chứa chuỗi giống giữ chỗ sẽ không bị thay lại (một lượt thay thế)
    html = load_editor_html("tok")
    assert html.count("const TOKEN = ") == 1


def test_vietnamese_ui_strings_present():
    html = load_editor_html("tok")
    for text in ("Mặt bằng", "Lưu thành phương án mới", "Nhân bản", "Hoàn tác", "Làm lại", "Vấn đề", "hướng thổi",
                 "bắt dính lưới"):
        assert text in html, text
