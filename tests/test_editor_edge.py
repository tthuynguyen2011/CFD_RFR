"""Tự kiểm trang chỉnh bằng Edge headless (bỏ qua nếu máy không có Edge).

Cách chạy đã kiểm chứng: `msedge --headless=new --disable-gpu --user-data-dir=<thư mục tạm>
--virtual-time-budget=15000 --dump-dom <url>?token=...&selftest=1` (không có --virtual-time-budget thì
--dump-dom chụp DOM ngay lúc `load`, trước khi fetch/GLB xong).
"""

import html
import json
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import yaml

from editor_fixtures import make_editor_project
from odu_cfd.layout import server as srvmod
from odu_cfd.layout.balconies import read_balconies
from odu_cfd.layout.io import layout_path, read_layout
from odu_cfd.layout.server import make_server

EDGE_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def _find_edge():
    for c in EDGE_CANDIDATES:
        if Path(c).is_file():
            return c
    return shutil.which("msedge")


EDGE = _find_edge()
pytestmark = pytest.mark.skipif(EDGE is None, reason="không có Microsoft Edge")


def run_edge_dom(url, tmp_path, budget_ms=15000):
    """Trả DOM (sau JS) của trang. Trên Windows chạy qua PowerShell Start-Process: msedge chạy từ
    CreateProcess trực tiếp (Python/bash) thoát ngay, không in gì, và để lại tiến trình giữ khóa profile."""
    out = tmp_path / "edge-dom.html"

    def flags(prof):
        return ["--headless=new", "--disable-gpu", f"--user-data-dir={tmp_path / prof}",
                f"--virtual-time-budget={budget_ms}", "--dump-dom", url]

    if sys.platform == "win32":
        arglist = ",".join("'" + a.replace("'", "''") + "'" for a in flags("edge-profile-ps"))
        ps = (f"Start-Process -FilePath '{EDGE}' -ArgumentList @({arglist}) -Wait -NoNewWindow "
              f"-RedirectStandardOutput '{out}' -RedirectStandardError '{tmp_path / 'edge-err.txt'}'")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=180)
    else:
        with open(out, "wb") as f:
            subprocess.run([EDGE, *flags("edge-profile")], stdout=f, stderr=subprocess.DEVNULL,
                           stdin=subprocess.DEVNULL, timeout=180)
    return out.read_bytes().decode("utf-8", errors="replace") if out.exists() else ""


def selftest_result(dom):
    m = re.search(r'<pre id="selftest"[^>]*>(.*?)</pre>', dom, re.S)
    assert m, "không thấy <pre id=selftest> trong DOM"
    text = html.unescape(m.group(1))
    assert text.strip(), "selftest chưa ghi kết quả (DOM bị chụp quá sớm?)"
    return json.loads(text)


def _serve(project):
    srv, url = make_server(project, "KT-v1", port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, url


def _steps(res):
    return {s["step"]: s for s in res["steps"]}


def test_selftest_runs_through_editorapi_and_saves(tmp_path, tower_dxf):
    project = make_editor_project(tmp_path, tower_dxf)
    srv, url = _serve(project)
    try:
        dom = run_edge_dom(url + "&selftest=1", tmp_path)
    finally:
        srv.shutdown()
        srv.server_close()
    assert "<title>selftest-done</title>" in dom
    res = selftest_result(dom)
    assert res["ok"] is True, res.get("error")
    s = _steps(res)
    assert s["start"]["odus"] == 2 and s["start"]["balconies"] == 2 and s["start"]["first_balcony"] == "B01"
    assert s["start"]["view"]["glb"] == "đã nạp" and s["start"]["view"]["glb_meshes"] >= 2
    assert s["start"]["view"]["odu_meshes"] == 2 and s["start"]["view"]["balcony_overlays"] == 2
    assert s["add"]["id"] == "ODU-03" and (s["add"]["x"], s["add"]["y"]) == (7, 1) and s["add"]["dirty"] is True
    assert s["move"]["x"] == 7.5 and s["move"]["snap_grid_ok"] is True
    assert s["rotate"]["rotation_deg"] == 90 and s["rotate"]["front_deg"] == 180
    assert s["undo"]["undone"] is True and s["undo"]["rotation_deg"] == 0
    assert s["redo"]["redone"] is True and s["redo"]["rotation_deg"] == 90
    fc = s["front_convention"]  # I5/M7: quy ước hướng thổi, ô nhập và mũi tên vẽ
    assert fc["rot_after_front_270"] == 180 and fc["front_field_after"] == "270"
    if fc["ok_view"]:
        for key, up in (("arrow_rot0", 1), ("arrow_rot180", -1)):
            w, sc = fc[key]["world"], fc[key]["screen"]
            assert abs(w[0]) < 0.05 and w[1] * up > 0.3, (key, w)  # 0 -> +y (lên), 180 -> -y (xuống)
            assert abs(sc[0]) < 2 and sc[1] * up > 1, (key, sc)  # trên màn hình mặt bằng: 0 lên, 180 xuống
    assert "150.00°" in fc["list_text"] and "150.0000000" not in fc["list_text"] and "x=7.12" in fc["list_text"]
    assert float(fc["rot_field_precise"]) == pytest.approx(150.00000000504428, abs=1e-3)
    assert s["modes"]["plan"]["mode"] == "plan" and s["modes"]["d3"]["mode"] == "3d"
    d = s["drag_synthetic"]  # sự kiện con trỏ tổng hợp (không phải chuột thật) chạy qua cùng bộ xử lý kéo
    assert d["x_before"] == 7.5 and d["x_after"] < 7.5 and d["selected"] == "ODU-03" and d["undoable"] is True
    assert s["click_balcony_synthetic"]["selected_balcony"] == "B01"
    t = s["toggle_balcony"]
    assert t["ok1"] and t["denied_after_first"] is True and t["ok2"] and t["allowed_after_second"] is True
    assert [b.allowed for b in read_balconies(project)] == [True, True]
    assert s["validate"]["errors"] == 0
    assert s["save"]["ok"] is True and s["save"]["name"] == "selftest"
    assert s["final"]["dirty"] is False and s["final"]["x"] == d["x_after"]
    saved = read_layout(layout_path(project, "selftest"))
    by_id = {o.odu_id: o for o in saved.odus}
    assert set(by_id) == {"ODU-01", "ODU-02", "ODU-03"}
    assert (by_id["ODU-03"].x, by_id["ODU-03"].y, by_id["ODU-03"].rotation_deg) == (d["x_after"], 1.0, 90.0)
    # phương án gốc không bị đổi
    assert len(read_layout(layout_path(project, "KT-v1")).odus) == 2


def test_selftest_with_hostile_token_and_project_name(tmp_path, tower_dxf, monkeypatch):
    nasty = "a\"b'c</script><b>&amp;\\x"
    monkeypatch.setattr(srvmod.secrets, "token_urlsafe", lambda n=16: nasty)
    project = make_editor_project(tmp_path, tower_dxf)
    data = yaml.safe_load((project / "project.yaml").read_text(encoding="utf-8"))
    data["project"]["name"] = "<img src=x onerror=\"document.title='pwned'\">Tên"
    (project / "project.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    srv, url = _serve(project)
    try:
        from urllib.parse import quote

        dom = run_edge_dom(url.split("token=")[0] + "token=" + quote(nasty, safe="") + "&selftest=1", tmp_path)
    finally:
        srv.shutdown()
        srv.server_close()
    assert "<title>selftest-done</title>" in dom  # onerror không chạy (title không thành 'pwned')
    res = selftest_result(dom)
    assert res["ok"] is True and _steps(res)["save"]["ok"] is True  # token lạ vẫn được dùng đúng qua X-Token
    assert "<img src=x" not in dom  # dữ liệu server chỉ vào DOM bằng textContent
    assert "&lt;img src=x" in dom
    assert layout_path(project, "selftest").is_file()


def test_page_with_errors_shows_red_problem_list(tmp_path, tower_dxf):
    from odu_cfd.layout.model import OduPlacement

    pl = [OduPlacement("ODU-01", 21.0, 1.0, 180.0), OduPlacement("ODU-02", 15.0, 10.0, 0.0)]
    project = make_editor_project(tmp_path, tower_dxf, odus=pl)
    srv, url = _serve(project)
    try:
        dom = run_edge_dom(url + "&mode=plan", tmp_path)
    finally:
        srv.shutdown()
        srv.server_close()
    assert 'data-ready="1"' in dom
    m = re.search(r'<div id="problems">(.*?)</div></div>', dom, re.S)
    assert m and 'class="error"' in m.group(1) and "ODU-02: ngoài ban công" in html.unescape(m.group(1))
    assert "bad" in re.search(r'<div id="oduList">.*?</div></div>', dom, re.S).group(0)
