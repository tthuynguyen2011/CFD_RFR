import base64
import re

from odu_cfd.geometry.export import write_glb
from odu_cfd.geometry.mesh import box
from odu_cfd.viewer.geometry_viewer import write_viewer_html


def _make(tmp_path):
    glb = tmp_path / "scene.glb"
    write_glb(glb, {"building": {"building": box(0, 0, 4, 4, 0, 0, 3)}, "odu": {"ODU-01_f00": box(1, 1, 1, 1, 0, 0, 1)}})
    out = tmp_path / "viewer.html"
    write_viewer_html(glb, out, title="Thử nghiệm")
    return glb, out.read_text(encoding="utf-8")


def test_glb_is_embedded_losslessly(tmp_path):
    glb, html = _make(tmp_path)
    m = re.search(r'const GLB_B64 = "([A-Za-z0-9+/=]+)"', html)
    assert m and base64.b64decode(m.group(1)) == glb.read_bytes()


def test_viewer_is_self_contained(tmp_path):
    _, html = _make(tmp_path)
    assert not re.search(r'(src|href)\s*=\s*["\']https?:', html)
    assert "<script src" not in html and "<link" not in html
    assert "THREE.GLTFLoader" in html and "OrbitControls" in html
    assert "REVISION" in html
    assert "Thử nghiệm" in html


def test_viewer_lists_groups_for_toggles(tmp_path):
    _, html = _make(tmp_path)
    assert 'id="groups"' in html


def test_title_is_escaped(tmp_path):
    glb = tmp_path / "s.glb"
    write_glb(glb, {"building": {"building": box(0, 0, 1, 1, 0, 0, 1)}})
    write_viewer_html(glb, tmp_path / "v.html", title="<b>&x")
    assert "<title>&lt;b&gt;&amp;x</title>" in (tmp_path / "v.html").read_text(encoding="utf-8")
