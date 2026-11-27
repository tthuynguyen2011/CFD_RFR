import http.client
from urllib.parse import quote
import json
import threading

import pytest
import yaml

from editor_fixtures import make_editor_project, write_library
from odu_cfd.errors import ConfigError
from odu_cfd.layout.balconies import read_balconies
from odu_cfd.layout.io import layout_path, read_layout
from odu_cfd.layout.model import OduPlacement
from odu_cfd.layout.server import make_server


def _snapshot(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


class Client:
    def __init__(self, server, url):
        self.server = server
        self.port = server.server_address[1]
        self.token = url.split("token=")[1]

    def req(self, method, path, body=None, headers=None, raw=None, host="default", origin=None, token="default"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {} if headers is None else dict(headers)
        h["Host"] = f"127.0.0.1:{self.port}" if host == "default" else host
        if origin is not None:
            h["Origin"] = origin
        data = raw
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if data is not None:
            h.setdefault("Content-Type", "application/json")
        if method == "POST":
            if token == "default":
                h["X-Token"] = self.token
            elif token is not None:
                h["X-Token"] = token
        conn.request(method, path, body=data, headers=h)
        r = conn.getresponse()
        payload = r.read()
        hdrs = {k.lower(): v for k, v in r.getheaders()}
        conn.close()
        return r.status, hdrs, payload

    def json(self, *a, **k):
        status, hdrs, payload = self.req(*a, **k)
        return status, json.loads(payload.decode("utf-8")), hdrs


@pytest.fixture
def project(tmp_path, tower_dxf):
    return make_editor_project(tmp_path, tower_dxf)


def _start(project, layout="KT-v1", library_dir=None):
    srv, url = make_server(project, layout, library_dir=library_dir, port=0)
    t = threading.Thread(target=lambda: srv.serve_forever(poll_interval=0.02), daemon=True)
    t.start()
    return srv, Client(srv, url), url


def _stop(srv):
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def client(project):
    srv, c, _ = _start(project)
    yield c
    _stop(srv)


def _layout_json(c):
    status, state, _ = c.json("GET", "/api/state")
    assert status == 200
    return state["layout"]


# ---------- khởi tạo ----------
def test_bind_only_loopback_and_url_has_token(project):
    srv, c, url = _start(project)
    try:
        assert srv.server_address[0] == "127.0.0.1"
        assert url.startswith(f"http://127.0.0.1:{srv.server_address[1]}/?token=")
        assert len(c.token) >= 16
    finally:
        _stop(srv)


def test_two_servers_have_different_tokens(project):
    s1, c1, _ = _start(project)
    s2, c2, _ = _start(project)
    try:
        assert c1.token != c2.token
    finally:
        _stop(s1)
        _stop(s2)


def test_bad_layout_name_rejected_at_start(project):
    with pytest.raises(ConfigError):
        make_server(project, "../x")


# ---------- GET ----------
def test_index_has_token_csp_and_no_store(client):
    status, h, body = client.req("GET", "/")
    assert status == 200
    assert h["content-type"].startswith("text/html") and "utf-8" in h["content-type"].lower()
    assert h["content-security-policy"] == (
        "default-src 'self' 'unsafe-inline' data: blob:; base-uri 'none'; form-action 'none'"
    )
    assert h["cache-control"] == "no-store"
    text = body.decode("utf-8")
    assert client.token in text and "EditorAPI" in text and "__TOKEN__" not in text


def test_scene_glb_served(client, project):
    status, h, body = client.req("GET", "/scene.glb")
    assert status == 200 and body[:4] == b"glTF"
    assert body == (project / "input" / "geometry" / "base.glb").read_bytes()


def test_scene_missing_is_404_vietnamese(client, project):
    (project / "input" / "geometry" / "base.glb").unlink()
    status, data, _ = client.json("GET", "/scene.glb")
    assert status == 404 and "geometry" in data["error"]


def test_unknown_paths_404_and_no_arbitrary_files(client):
    for path in ("/nope", "/project.yaml", "/../project.yaml", "/input/ingest.yaml", "/%2e%2e/project.yaml",
                 "/layouts/KT-v1.yaml", "/api/state/x"):
        status, _, _ = client.req("GET", path)
        assert status == 404, path


def test_state_contents(client):
    status, st, h = client.json("GET", "/api/state")
    assert status == 200 and "application/json" in h["content-type"] and "utf-8" in h["content-type"].lower()
    assert st["layout_exists"] is True and st["layouts"] == ["KT-v1"]
    assert st["layout"]["name"] == "KT-v1" and st["layout"]["floors"] == "4-19"
    assert st["layout"]["description"] == "Phương án thử nghiệm tiếng Việt"
    assert [o["id"] for o in st["layout"]["odus"]] == ["ODU-01", "ODU-02"]
    assert [b["id"] for b in st["balconies"]] == ["B01", "B02"]
    assert st["balconies"][0]["polygon"] and st["balconies"][0]["allowed"] is True
    assert st["num_floors"] == 19 and st["floor_height_m"] == 3.3 and st["slab_thickness_m"] == 0.15
    assert st["defaults"] == {"width_m": 1.0, "depth_m": 0.4, "height_m": 1.0}
    assert st["models"] == [] and st["token_ok"] is True and len(st["plan"]["envelope"]) == 1
    assert st["project"]


def test_state_models_from_library(project, tmp_path):
    lib = write_library(tmp_path)
    srv, c, _ = _start(project, library_dir=lib)
    try:
        _, st, _ = c.json("GET", "/api/state")
        assert st["models"] == [{"model_id": "test-odu", "width_m": 0.9, "depth_m": 0.35, "height_m": 0.8}]
    finally:
        _stop(srv)


def test_missing_library_does_not_block(project, tmp_path):
    srv, c, _ = _start(project, library_dir=tmp_path / "khong-co")
    try:
        status, st, _ = c.json("GET", "/api/state")
        assert status == 200 and st["models"] == [] and st["library_note"]
    finally:
        _stop(srv)


def test_state_nonexistent_layout_is_blank(project):
    srv, c, _ = _start(project, layout="moi-1")
    try:
        _, st, _ = c.json("GET", "/api/state")
        assert st["layout_exists"] is False and st["layout"]["name"] == "moi-1" and st["layout"]["odus"] == []
        assert st["layout"]["floors"] == "1-19" and st["layout"]["source"] == "manual"
        assert not layout_path(project, "moi-1").exists()
    finally:
        _stop(srv)


def test_state_without_plan_is_404(project):
    (project / "input" / "geometry" / "plan.json").unlink()
    srv, c, _ = _start(project)
    try:
        status, data, _ = c.json("GET", "/api/state")
        assert status == 404 and "geometry" in data["error"]
    finally:
        _stop(srv)


def test_get_layout_by_name(client):
    status, lay, _ = client.json("GET", "/api/layout?name=KT-v1")
    assert status == 200 and lay["name"] == "KT-v1" and len(lay["odus"]) == 2
    assert client.json("GET", "/api/layout?name=khong-co")[0] == 404
    assert client.json("GET", "/api/layout?name=..%2Fx")[0] == 400
    assert client.json("GET", "/api/layout?name=a%20b")[0] == 400
    assert client.json("GET", "/api/layout")[0] == 400


# ---------- validate ----------
def _odu(i, x, y, rot=0.0):
    return {"id": i, "x": x, "y": y, "rotation_deg": rot, "model_id": None, "size": None, "floors": None}


def test_validate_clean_and_sizes(client):
    lay = _layout_json(client)
    status, data, _ = client.json("POST", "/api/validate", {"layout": lay})
    assert status == 200 and data["problems"] == []
    assert data["sizes"] == {"ODU-01": [1.0, 0.4], "ODU-02": [1.0, 0.4]}
    assert data["heights"]["ODU-01"] == 1.0


def test_validate_reports_outside_and_overlap(client):
    lay = _layout_json(client)
    lay["odus"].append(_odu("ODU-03", 15.0, 10.0))
    lay["odus"].append(_odu("ODU-04", 21.2, 1.0))
    _, data, _ = client.json("POST", "/api/validate", {"layout": lay})
    msgs = [p["message"] for p in data["problems"] if p["level"] == "error"]
    assert any("ODU-03" in m and "ngoài ban công" in m for m in msgs)
    assert any("chồng" in m for m in msgs)


def test_validate_size_resolution_order(tmp_path, tower_dxf):
    lib = write_library(tmp_path)
    pl = [
        OduPlacement("A", 21.0, 1.0, 0.0),
        OduPlacement("B", 22.5, 1.0, 0.0, size=(0.5, 0.3)),
        OduPlacement("C", 23.2, 0.7, 0.0, model_id="khong-co"),
    ]
    p2 = make_editor_project(tmp_path, tower_dxf, odus=pl, model_id="test-odu")
    srv, c, _ = _start(p2, library_dir=lib)
    try:
        _, data, _ = c.json("POST", "/api/validate", {"layout": _layout_json(c)})
        assert data["sizes"]["A"] == [0.9, 0.35]  # thư viện theo model của dự án
        assert data["sizes"]["B"] == [0.5, 0.3]  # size riêng
        assert data["sizes"]["C"] == [1.0, 0.4]  # model lạ -> mặc định geometry
        assert data["heights"]["A"] == 0.8 and data["heights"]["C"] == 1.0
    finally:
        _stop(srv)


def test_validate_height_warning(project):
    data = yaml.safe_load((project / "project.yaml").read_text(encoding="utf-8"))
    data.setdefault("geometry", {})["odu_default_height_m"] = 3.2
    (project / "project.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    srv, c, _ = _start(project)
    try:
        _, res, _ = c.json("POST", "/api/validate", {"layout": _layout_json(c)})
        assert any(p["level"] == "warning" and "tầng" in p["message"] for p in res["problems"])
    finally:
        _stop(srv)


def test_validate_structure_error_is_a_problem_not_http_error(client):
    lay = _layout_json(client)
    lay["floors"] = "abc"
    status, data, _ = client.json("POST", "/api/validate", {"layout": lay})
    assert status == 200 and data["problems"][0]["level"] == "error" and "tầng" in data["problems"][0]["message"]


# ---------- save ----------
def test_save_valid_then_read_back(client, project):
    lay = _layout_json(client)
    lay["odus"][0]["x"] = 20.6
    lay["description"] = "đã chỉnh"
    status, data, _ = client.json("POST", "/api/save", {"layout": lay})
    assert status == 200 and data["saved"] is True and data["name"] == "KT-v1" and data["problems"] == []
    got = read_layout(layout_path(project, "KT-v1"))
    assert got.odus[0].x == 20.6 and got.description == "đã chỉnh"
    assert (project / "layouts" / "KT-v1.yaml.bak").is_file()  # sao lưu bản cũ


def test_save_with_errors_is_422_and_keeps_file(client, project):
    before = layout_path(project, "KT-v1").read_bytes()
    lay = _layout_json(client)
    lay["odus"][0]["x"] = 15.0
    lay["odus"][0]["y"] = 10.0
    status, data, _ = client.json("POST", "/api/save", {"layout": lay})
    assert status == 422 and any("ngoài ban công" in p["message"] for p in data["problems"])
    assert layout_path(project, "KT-v1").read_bytes() == before
    assert not (project / "layouts" / "KT-v1.yaml.bak").exists()


def test_save_as_new_name_and_conflict(client, project):
    lay = _layout_json(client)
    status, data, _ = client.json("POST", "/api/save", {"layout": lay, "name": "PA-2"})
    assert status == 200 and data["name"] == "PA-2" and "PA-2" in data["layouts"]
    assert read_layout(layout_path(project, "PA-2")).name == "PA-2"
    status, data, _ = client.json("POST", "/api/save", {"layout": lay, "name": "PA-2"})
    assert status == 409 and "đã có" in data["error"]
    status, data, _ = client.json("POST", "/api/save", {"layout": lay, "name": "PA-2", "overwrite": True})
    assert status == 200


@pytest.mark.parametrize("bad", ["../x", "a/b", "", "a b", "x" * 65, "..", ".", "a\\b", "ngôn"])
def test_save_bad_name_is_400_and_writes_nothing(client, project, bad):
    before = _snapshot(project)
    status, data, _ = client.json("POST", "/api/save", {"layout": _layout_json(client), "name": bad})
    assert status == 400 and "tên phương án" in data["error"]
    assert _snapshot(project) == before


def test_save_bad_layout_name_in_body_is_400(client, project):
    lay = _layout_json(client)
    lay["name"] = "../../evil"
    before = _snapshot(project)
    assert client.json("POST", "/api/save", {"layout": lay})[0] == 400
    assert _snapshot(project) == before


def test_save_structural_errors_are_400(client):
    lay = _layout_json(client)
    lay["odus"][0]["x"] = "6"
    assert client.json("POST", "/api/save", {"layout": lay})[0] == 400
    assert client.json("POST", "/api/save", {})[0] == 400
    assert client.json("POST", "/api/save", {"layout": 5})[0] == 400


def test_writes_only_under_layouts_and_balconies(client, project):
    before = set(_snapshot(project))
    client.json("POST", "/api/save", {"layout": _layout_json(client), "name": "PA-3"})
    client.json("POST", "/api/balconies", {"denied": ["B01"]})
    after = set(_snapshot(project))
    assert after - before == {"layouts/PA-3.yaml"}
    assert before - after == set()
    # file khác không bị đổi nội dung: input/ nguyên vẹn
    assert yaml.safe_load((project / "input" / "ingest.yaml").read_text(encoding="utf-8"))


# ---------- balconies ----------
def test_balconies_toggle_updates_yaml_and_validation(client, project):
    status, data, _ = client.json("POST", "/api/balconies", {"denied": ["B02"]})
    assert status == 200 and [b["allowed"] for b in data["balconies"]] == [True, False]
    assert [b.allowed for b in read_balconies(project)] == [True, False]
    _, res, _ = client.json("POST", "/api/validate", {"layout": _layout_json(client)})
    assert any("B02" in p["message"] and "không cho phép" in p["message"] for p in res["problems"])
    status, data, _ = client.json("POST", "/api/balconies", {"allowed": ["B02"]})
    assert [b["allowed"] for b in data["balconies"]] == [True, True]
    assert [b.allowed for b in read_balconies(project)] == [True, True]


def test_balconies_unknown_id_and_bad_types(client):
    status, data, _ = client.json("POST", "/api/balconies", {"denied": ["B99"]})
    assert status == 400 and "B01" in data["error"]
    assert client.json("POST", "/api/balconies", {"denied": "B01"})[0] == 400
    assert client.json("POST", "/api/balconies", {"allowed": [1]})[0] == 400
    assert client.json("POST", "/api/balconies", [])[0] == 400


# ---------- bảo vệ ----------
@pytest.mark.parametrize("host", ["evil.com", "127.0.0.1", "localhost", "127.0.0.1:1", "evil.com:%PORT%", ""])
def test_bad_host_is_403(client, host):
    host = host.replace("%PORT%", str(client.port))
    assert client.req("GET", "/api/state", host=host)[0] == 403
    assert client.req("POST", "/api/validate", body={"layout": {}}, host=host)[0] == 403


def test_localhost_host_is_allowed(client):
    assert client.req("GET", "/api/state", host=f"localhost:{client.port}")[0] == 200


def test_missing_host_header_is_403(client):
    conn = http.client.HTTPConnection("127.0.0.1", client.port, timeout=10)
    conn.putrequest("GET", "/api/state", skip_host=True)
    conn.endheaders()
    assert conn.getresponse().status == 403
    conn.close()


def test_bad_origin_is_403_good_origin_ok(client):
    assert client.req("GET", "/api/state", origin="http://evil.com")[0] == 403
    assert client.req("GET", "/api/state", origin=f"http://127.0.0.1:{client.port + 1}")[0] == 403
    assert client.req("GET", "/api/state", origin="null")[0] == 403
    assert client.req("POST", "/api/validate", body={"layout": {}}, origin="http://evil.com")[0] == 403
    assert client.req("GET", "/api/state", origin=f"http://127.0.0.1:{client.port}")[0] == 200
    assert client.req("GET", "/api/state", origin=f"http://localhost:{client.port}")[0] == 200


@pytest.mark.parametrize("path", ["/api/validate", "/api/save", "/api/balconies"])
def test_post_without_or_with_wrong_token_is_403(client, project, path):
    before = _snapshot(project)
    body = {"layout": _layout_json(client), "name": "hack", "denied": ["B01"]}
    assert client.req("POST", path, body=body, token=None)[0] == 403
    assert client.req("POST", path, body=body, token="sai")[0] == 403
    assert client.req("POST", path, body=body, token=client.token + "x")[0] == 403
    assert client.req("POST", path, body=body, token="")[0] == 403
    assert _snapshot(project) == before
    assert [b.allowed for b in read_balconies(project)] == [True, True]


def test_non_ascii_token_header_does_not_crash(client):
    conn = http.client.HTTPConnection("127.0.0.1", client.port, timeout=10)
    conn.putrequest("POST", "/api/validate", skip_host=True)
    conn.putheader("Host", f"127.0.0.1:{client.port}")
    conn.putheader("X-Token", "tôi".encode("utf-8").decode("latin-1"))
    conn.putheader("Content-Length", "2")
    conn.endheaders(b"{}")
    assert conn.getresponse().status == 403
    conn.close()


def test_body_limits(client):
    assert client.req("POST", "/api/validate", headers={"Content-Length": str(1024 * 1024 + 1)}, raw=b"{}")[0] == 413
    # thiếu Content-Length -> 411
    conn = http.client.HTTPConnection("127.0.0.1", client.port, timeout=10)
    conn.putrequest("POST", "/api/validate", skip_host=True)
    conn.putheader("Host", f"127.0.0.1:{client.port}")
    conn.putheader("X-Token", client.token)
    conn.endheaders()
    assert conn.getresponse().status == 411
    conn.close()
    # đúng giới hạn 1 MB vẫn được nhận (JSON hợp lệ nhưng thiếu layout -> 400, không phải 413)
    pad = json.dumps({"pad": "x" * (1024 * 1024 - 20)}).encode("utf-8")
    assert len(pad) <= 1024 * 1024
    assert client.req("POST", "/api/validate", raw=pad)[0] == 400
    assert client.req("POST", "/api/validate", headers={"Content-Length": "abc"}, raw=b"{}")[0] == 400


def test_chunked_is_rejected(client):
    conn = http.client.HTTPConnection("127.0.0.1", client.port, timeout=10)
    conn.putrequest("POST", "/api/validate", skip_host=True)
    conn.putheader("Host", f"127.0.0.1:{client.port}")
    conn.putheader("X-Token", client.token)
    conn.putheader("Transfer-Encoding", "chunked")
    conn.endheaders()
    assert conn.getresponse().status == 411
    conn.close()


def test_broken_json_is_400_vietnamese(client):
    status, h, payload = client.req("POST", "/api/validate", raw=b"{khong phai json")
    data = json.loads(payload.decode("utf-8"))
    assert status == 400 and "JSON" in data["error"]
    status, _, _ = client.req("POST", "/api/validate", raw=b'{"layout": "\xe9"}')  # không phải UTF-8
    assert status == 400


def test_other_methods_not_allowed(client):
    for m in ("PUT", "DELETE", "PATCH"):
        assert client.req(m, "/api/save", headers={"Content-Length": "0"})[0] == 405


def test_json_is_utf8_unescaped_and_headers_on_errors(client):
    status, h, payload = client.req("GET", "/api/state")
    assert "Phương án thử nghiệm tiếng Việt" in payload.decode("utf-8")
    assert "charset=utf-8" in h["content-type"].lower()
    s, h, _ = client.req("GET", "/nope")
    assert "charset=utf-8" in h["content-type"].lower() and h["cache-control"] == "no-store"
    assert h["content-security-policy"].startswith("default-src 'self'")


def test_reads_do_not_change_project(client, project):
    before = _snapshot(project)
    client.req("GET", "/")
    client.req("GET", "/api/state")
    client.req("GET", "/scene.glb")
    client.json("POST", "/api/validate", {"layout": _layout_json(client)})
    assert _snapshot(project) == before


def test_run_editor_stops_cleanly(project, monkeypatch):
    from odu_cfd.layout import server as srvmod

    opened = []
    monkeypatch.setattr(srvmod.webbrowser, "open", lambda url: opened.append(url))

    def fake(self, *a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(srvmod.EditorServer, "serve_forever", fake)
    assert srvmod.run_editor(project, "KT-v1", open_browser=True) == 0
    assert len(opened) == 1 and opened[0].startswith("http://127.0.0.1:") and "token=" in opened[0]
    opened.clear()
    assert srvmod.run_editor(project, "KT-v1", open_browser=False) == 0 and opened == []


# ---------- vòng 4: timeout, JSON lồng sâu, CSP, tên phương án ----------
def test_csp_blocks_base_and_forms(client):
    _, h, _ = client.req("GET", "/")
    csp = h["content-security-policy"]
    assert "base-uri 'none'" in csp and "form-action 'none'" in csp and "default-src 'self'" in csp


def test_handler_has_socket_timeout():
    from odu_cfd.layout.server import _Handler

    assert _Handler.timeout == 30


def test_hanging_partial_body_connection_is_closed(project, monkeypatch):
    import socket
    import time

    from odu_cfd.layout import server as srvmod

    monkeypatch.setattr(srvmod._Handler, "timeout", 0.5)
    srv, c, _ = _start(project)
    try:
        s = socket.create_connection(("127.0.0.1", c.port), timeout=10)
        head = (f"POST /api/validate HTTP/1.1\r\nHost: 127.0.0.1:{c.port}\r\nX-Token: {c.token}\r\n"
                "Content-Type: application/json\r\nContent-Length: 500\r\n\r\n{\"layout\":")
        s.sendall(head.encode())
        t0 = time.time()
        data = b""
        try:
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
        except ConnectionResetError:
            pass
        assert time.time() - t0 < 5, "server phải đóng kết nối treo sau vài giây"
        s.close()
        # server vẫn phục vụ bình thường
        assert c.req("GET", "/api/state")[0] == 200
    finally:
        _stop(srv)


def test_deeply_nested_json_is_400_not_500(client):
    deep = b"[" * 100000 + b"]" * 100000
    status, h, payload = client.req("POST", "/api/validate", raw=deep)
    assert status == 400
    assert "JSON" in json.loads(payload.decode("utf-8"))["error"]
    assert client.req("GET", "/api/state")[0] == 200


@pytest.mark.parametrize("bad", ["CON", "NUL", "a.", "-x", "com1", "a b"])
def test_save_reserved_or_odd_names_are_400_and_write_nothing(client, project, bad):
    before = _snapshot(project)
    lay = _layout_json(client)
    status, body, _ = client.json("POST", "/api/save", body={"layout": lay, "name": bad})
    assert status == 400 and "error" in body
    status, _, _ = client.req("GET", "/api/layout?name=" + quote(bad))
    assert status == 400
    assert _snapshot(project) == before


@pytest.mark.parametrize("mutate", ["source", "size"])
def test_validate_and_save_agree_on_bad_source_and_oversize(client, mutate):
    """Hồi quy review 2c (M4): /api/validate báo lỗi giống /api/save cho source lạ và size > 5 m."""
    lay = _layout_json(client)
    if mutate == "source":
        lay["source"] = "khác"
    else:
        lay["odus"][0]["size"] = [9.0, 0.4]
    status, data, _ = client.json("POST", "/api/validate", {"layout": lay})
    assert status == 200 and any(p["level"] == "error" for p in data["problems"])
    status_save, _, _ = client.json("POST", "/api/save", {"layout": lay})
    assert status_save in (400, 422)
