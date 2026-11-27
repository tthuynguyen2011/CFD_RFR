"""Server cục bộ cho trình chỉnh 3D phương án bố trí dàn nóng (`odu-cfd edit`).

Chỉ nghe 127.0.0.1. Bảo vệ: kiểm tra Host/Origin, token X-Token cho mọi POST, giới hạn thân 1 MB,
tên phương án theo regex, không bao giờ ghi ngoài `layouts/` và `balconies.yaml`.
"""

import json
import re
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ..errors import ConfigError
from ..odu import load_odu_library
from ..schema import load_project
from ..viewer.editor_page import load_editor_html
from .balconies import read_balconies, set_allowed
from .io import check_layout, layout_path, list_layouts, read_layout, write_layout
from .model import NAME_RE, Layout, OduPlacement, format_floors, parse_floors
from .validate import Problem, validate_layout

MAX_BODY = 1024 * 1024
CHUNK = 32768
CSP = "default-src 'self' 'unsafe-inline' data: blob:; base-uri 'none'; form-action 'none'"
SOCKET_TIMEOUT_S = 30  # kết nối treo (gửi dở thân) tự đóng, giải phóng luồng


class _HttpError(Exception):
    def __init__(self, status, message, extra=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra or {}


# ---------- chuyển đổi layout <-> JSON ----------


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def layout_to_json(layout: Layout) -> dict:
    return {
        "name": layout.name,
        "description": layout.description,
        "source": layout.source,
        "floors": format_floors(layout.floors),
        "odus": [
            {
                "id": o.odu_id,
                "x": float(o.x),
                "y": float(o.y),
                "rotation_deg": float(o.rotation_deg),
                "model_id": o.model_id,
                "size": None if o.size is None else [float(o.size[0]), float(o.size[1])],
                "floors": None if o.floors is None else format_floors(o.floors),
            }
            for o in layout.odus
        ],
    }


def layout_from_json(data, name=None) -> Layout:
    """JSON từ trình duyệt -> Layout. Lỗi cấu trúc/kiểu: ConfigError tiếng Việt (không kiểm tra miền giá trị)."""
    if not isinstance(data, dict):
        raise ConfigError("'layout' phải là một đối tượng JSON")
    nm = name if name is not None else data.get("name")
    if not isinstance(nm, str):
        raise ConfigError("thiếu tên phương án")
    desc = data.get("description", "")
    if desc is None:
        desc = ""
    if not isinstance(desc, str):
        raise ConfigError("'description' phải là chuỗi")
    source = data.get("source", "manual")
    if not isinstance(source, str):
        raise ConfigError("'source' phải là chuỗi")
    floors = parse_floors(data.get("floors"))
    items = data.get("odus")
    if not isinstance(items, list):
        raise ConfigError("'odus' phải là danh sách")
    odus = []
    for i, it in enumerate(items):
        where = f"odus[{i}]"
        if not isinstance(it, dict):
            raise ConfigError(f"{where} phải là một đối tượng")
        oid = it.get("id")
        if not isinstance(oid, str):
            raise ConfigError(f"{where}.id phải là chuỗi")
        nums = {}
        for k in ("x", "y", "rotation_deg"):
            if not _is_num(it.get(k)):
                raise ConfigError(f"{where}.{k} phải là số")
            nums[k] = float(it[k])
        model_id = it.get("model_id")
        if model_id is not None and not isinstance(model_id, str):
            raise ConfigError(f"{where}.model_id phải là chuỗi hoặc null")
        size = it.get("size")
        if size is not None:
            if not (isinstance(size, list) and len(size) == 2 and all(_is_num(s) for s in size)):
                raise ConfigError(f"{where}.size phải là [w, d] hoặc null")
            size = (float(size[0]), float(size[1]))
        of = it.get("floors")
        if of is not None:
            of = parse_floors(of)
        odus.append(OduPlacement(oid, nums["x"], nums["y"], nums["rotation_deg"], model_id, size, of))
    return Layout(nm, desc, source, floors, tuple(odus))


def _problems_json(problems):
    return [{"level": p.level, "odu_id": p.odu_id, "message": p.message} for p in problems]


def _balconies_json(infos):
    out = []
    for b in infos:
        ring = [[float(x), float(y)] for x, y in list(b.polygon.exterior.coords)[:-1]]
        out.append(
            {
                "id": b.balcony_id,
                "polygon": ring,
                "allowed": bool(b.allowed),
                "note": b.note,
                "area_m2": float(b.polygon.area),
            }
        )
    return out


# ---------- server ----------


class EditorServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, project_dir, layout_name, library_dir, port):
        self.project_dir = Path(project_dir)
        self.token = secrets.token_urlsafe(16)
        self.layout_name = layout_name
        self.library_dir = library_dir
        self.project = load_project(self.project_dir / "project.yaml")
        self.library, self.library_note = {}, None
        if library_dir:
            try:
                self.library = load_odu_library(library_dir)
            except ConfigError as e:
                self.library_note = str(e)
        self.write_lock = threading.Lock()
        super().__init__(("127.0.0.1", port), _Handler)

    @property
    def port(self):
        return self.server_address[1]

    # --- dữ liệu dự án ---
    def read_plan(self):
        path = self.project_dir / "input" / "geometry" / "plan.json"
        if not path.is_file():
            raise _HttpError(404, f"chưa có '{path}': chạy `odu-cfd geometry {self.project_dir}` trước")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise _HttpError(500, f"'{path}' không đọc được: {e}") from None

    def read_balconies(self):
        try:
            return read_balconies(self.project_dir)
        except ConfigError as e:
            raise _HttpError(404, str(e)) from None

    def models_json(self):
        return [
            {"model_id": m.model_id, "width_m": m.width_m, "depth_m": m.depth_m, "height_m": m.height_m}
            for m in sorted(self.library.values(), key=lambda m: m.model_id)
        ]

    def resolve_dims(self, layout):
        """({id: (w, d)}, {id: h}): size riêng, rồi thư viện theo model, rồi mặc định trong geometry."""
        geo = self.project.geometry
        sizes, heights = {}, {}
        for o in layout.odus:
            mid = o.model_id or self.project.odu.model_id
            model = self.library.get(mid)
            if o.size is not None:
                sizes[o.odu_id] = (float(o.size[0]), float(o.size[1]))
            elif model is not None:
                sizes[o.odu_id] = (model.width_m, model.depth_m)
            else:
                sizes[o.odu_id] = (geo.odu_default_width_m, geo.odu_default_depth_m)
            heights[o.odu_id] = model.height_m if model is not None else geo.odu_default_height_m
        return sizes, heights

    def check(self, layout, balconies, plan):
        num_floors = int(plan.get("num_floors", self.project.building.num_floors))
        sizes, heights = self.resolve_dims(layout)
        problems = validate_layout(layout, balconies, num_floors, sizes)
        fh = float(plan.get("floor_height_m", self.project.building.floor_height_m))
        slab = float(plan.get("slab_thickness_m", self.project.geometry.slab_thickness_m))
        for oid, h in heights.items():
            if slab + h >= fh:
                problems.append(
                    Problem(
                        "warning",
                        oid,
                        f"{oid}: cao {h:g} m cộng sàn {slab:g} m không thấp hơn chiều cao tầng {fh:g} m, "
                        "dựng 3D (geometry --layout) sẽ bị từ chối",
                    )
                )
        return problems, sizes, heights

    def blank_layout(self, name, plan):
        n = int(plan.get("num_floors", self.project.building.num_floors))
        return Layout(name, "", "manual", tuple(range(1, n + 1)), ())


def _is_allowed_host(server, host):
    return host in (f"127.0.0.1:{server.port}", f"localhost:{server.port}")


def _is_allowed_origin(server, origin):
    return origin in (f"http://127.0.0.1:{server.port}", f"http://localhost:{server.port}")


class _Handler(BaseHTTPRequestHandler):
    server_version = "odu-cfd-editor"
    timeout = SOCKET_TIMEOUT_S

    def log_message(self, fmt, *args):  # im lặng
        pass

    # --- phản hồi ---
    def _send(self, status, body, ctype, extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        # ghi từng khúc nhỏ: ghi một lần cả trăm KB vào socket loopback Windows có thể bị kẹt
        for i in range(0, len(body), CHUNK):
            self.wfile.write(body[i : i + CHUNK])

    def _json(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status, message, extra=None):
        payload = {"error": message}
        payload.update(extra or {})
        self._json(status, payload)

    # --- bảo vệ ---
    def _guard(self, post):
        srv = self.server
        host = self.headers.get("Host")
        if host is None or not _is_allowed_host(srv, host):
            raise _HttpError(403, "Host không được phép (chỉ nhận 127.0.0.1 hoặc localhost đúng cổng)")
        origin = self.headers.get("Origin")
        if origin is not None and not _is_allowed_origin(srv, origin):
            raise _HttpError(403, "Origin không được phép")
        if post:
            sent = self.headers.get("X-Token") or ""
            if not secrets.compare_digest(sent.encode("utf-8"), srv.token.encode("utf-8")):
                raise _HttpError(403, "thiếu hoặc sai token (X-Token)")

    def _drain(self):
        """Đọc bỏ thân yêu cầu chưa đọc trước khi trả lỗi, để client không nhận RST thay vì phản hồi.

        Content-Length hợp lệ và <= 1 MB: đọc đủ. Trường hợp khác (quá lớn, sai định dạng, chunked): chỉ đọc
        nốt phần đã tới (tối đa 64 KB, chờ rất ngắn), không bao giờ đọc thân lớn.
        """
        if self._body_read:
            return
        self._body_read = True
        raw = self.headers.get("Content-Length")
        try:
            if raw and raw.isascii() and raw.isdigit() and 0 < int(raw) <= MAX_BODY:
                self.rfile.read(int(raw))
                return
            old = self.connection.gettimeout()
            self.connection.settimeout(0.05)
            try:
                self.connection.recv(65536)
            finally:
                self.connection.settimeout(old)
        except OSError:
            pass

    def _read_json(self):
        if self.headers.get("Transfer-Encoding"):
            raise _HttpError(411, "cần Content-Length, không nhận Transfer-Encoding")
        raw = self.headers.get("Content-Length")
        if raw is None:
            raise _HttpError(411, "thiếu Content-Length")
        if not raw.isascii() or not raw.isdigit():
            raise _HttpError(400, "Content-Length không hợp lệ")
        n = int(raw)
        if n > MAX_BODY:
            raise _HttpError(413, f"thân yêu cầu quá lớn (tối đa {MAX_BODY} byte)")
        self._body_read = True
        body = self.rfile.read(n)
        try:
            return json.loads(body.decode("utf-8"))
        except RecursionError:
            raise _HttpError(400, "JSON lồng quá sâu") from None
        except (ValueError, UnicodeDecodeError):
            raise _HttpError(400, "thân yêu cầu không phải JSON UTF-8 hợp lệ") from None

    # --- điều phối ---
    def _dispatch(self, post):
        self._body_read = False
        try:
            self._guard(post)
            parts = urlsplit(self.path)
            route = (self.command, parts.path)
            handler = (POST_ROUTES if post else GET_ROUTES).get(parts.path)
            if handler is None:
                raise _HttpError(404, "không có đường dẫn này")
            query = parse_qs(parts.query)
            handler(self, query)
        except _HttpError as e:
            self._drain()
            self._error(e.status, e.message, e.extra)
        except ConfigError as e:
            self._error(400, str(e))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # không lộ stack trace ra mạng
            print(f"Lỗi server chỉnh: {e!r}", file=sys.stderr)
            self._error(500, "lỗi nội bộ của server")

    def do_GET(self):
        self._dispatch(False)

    def do_POST(self):
        self._dispatch(True)

    def do_HEAD(self):
        self._error(405, "không hỗ trợ")

    def do_PUT(self):
        self._error(405, "không hỗ trợ")

    do_DELETE = do_PATCH = do_PUT

    # --- GET ---
    def _get_index(self, query):
        page = load_editor_html(self.server.token)
        self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")

    def _get_scene(self, query):
        path = self.server.project_dir / "input" / "geometry" / "base.glb"
        if not path.is_file():
            raise _HttpError(404, f"chưa có '{path}': chạy `odu-cfd geometry {self.server.project_dir}` trước")
        self._send(200, path.read_bytes(), "model/gltf-binary")

    def _layout_json_or_none(self, name):
        path = layout_path(self.server.project_dir, name)
        if not path.is_file():
            return None
        return layout_to_json(read_layout(path))

    def _get_state(self, query):
        srv = self.server
        plan = srv.read_plan()
        balconies = srv.read_balconies()
        names = list_layouts(srv.project_dir)
        name = srv.layout_name or (names[0] if names else "layout-1")
        layout = self._layout_json_or_none(name)
        exists = layout is not None
        if not exists:
            layout = layout_to_json(srv.blank_layout(name, plan))
        geo = srv.project.geometry
        self._json(
            200,
            {
                "project": srv.project.name,
                "layout": layout,
                "layout_exists": exists,
                "layouts": names,
                "plan": plan,
                "balconies": _balconies_json(balconies),
                "models": srv.models_json(),
                "project_model_id": srv.project.odu.model_id,
                "library_note": srv.library_note,
                "defaults": {
                    "width_m": geo.odu_default_width_m,
                    "depth_m": geo.odu_default_depth_m,
                    "height_m": geo.odu_default_height_m,
                },
                "num_floors": plan.get("num_floors", srv.project.building.num_floors),
                "floor_height_m": plan.get("floor_height_m", srv.project.building.floor_height_m),
                "slab_thickness_m": plan.get("slab_thickness_m", geo.slab_thickness_m),
                "token_ok": True,
            },
        )

    def _get_layout(self, query):
        names = query.get("name") or []
        if len(names) != 1:
            raise _HttpError(400, "cần đúng một tham số name")
        layout = self._layout_json_or_none(names[0])  # ConfigError nếu tên sai -> 400
        if layout is None:
            raise _HttpError(404, f"không có phương án '{names[0]}'")
        self._json(200, layout)

    # --- POST ---
    def _post_validate(self, query):
        srv = self.server
        body = self._read_json()
        if not isinstance(body, dict) or "layout" not in body:
            raise _HttpError(400, "thiếu 'layout' trong yêu cầu")
        plan = srv.read_plan()
        balconies = srv.read_balconies()
        try:
            layout = layout_from_json(body["layout"])
            check_layout(layout)  # cùng bộ kiểm tra với /api/save và read_layout
        except ConfigError as e:
            self._json(
                200,
                {"problems": _problems_json([Problem("error", None, str(e))]), "sizes": {}, "heights": {}},
            )
            return
        problems, sizes, heights = srv.check(layout, balconies, plan)
        self._json(
            200,
            {
                "problems": _problems_json(problems),
                "sizes": {k: list(v) for k, v in sizes.items()},
                "heights": heights,
            },
        )

    def _post_save(self, query):
        srv = self.server
        body = self._read_json()
        if not isinstance(body, dict) or "layout" not in body:
            raise _HttpError(400, "thiếu 'layout' trong yêu cầu")
        name = body.get("name")
        if name is not None and not isinstance(name, str):
            raise _HttpError(400, "'name' phải là chuỗi")
        target = name if name is not None else (body["layout"].get("name") if isinstance(body["layout"], dict) else None)
        if not isinstance(target, str) or re.fullmatch(NAME_RE, target) is None or target in (".", ".."):
            raise _HttpError(
                400,
                f"tên phương án {target!r} không hợp lệ: chỉ dùng chữ cái không dấu, số, '_', '.', '-' (tối đa 64 ký tự)",
            )
        path = layout_path(srv.project_dir, target)
        layout = layout_from_json(body["layout"], name=target)  # ConfigError -> 400
        plan = srv.read_plan()
        balconies = srv.read_balconies()
        problems, _, _ = srv.check(layout, balconies, plan)
        errors = [p for p in problems if p.level == "error"]
        if errors:
            raise _HttpError(422, "phương án có lỗi, không lưu", {"problems": _problems_json(problems)})
        with srv.write_lock:
            if name is not None and path.exists() and body.get("overwrite") is not True:
                raise _HttpError(409, f"phương án '{target}' đã có; chọn tên khác hoặc xác nhận ghi đè")
            write_layout(path, layout, backup=True)
            names = list_layouts(srv.project_dir)
        self._json(200, {"saved": True, "name": target, "problems": _problems_json(problems), "layouts": names})

    def _post_balconies(self, query):
        srv = self.server
        body = self._read_json()
        if not isinstance(body, dict):
            raise _HttpError(400, "yêu cầu phải là một đối tượng JSON")
        lists = {}
        for key in ("allowed", "denied"):
            v = body.get(key, [])
            if not (isinstance(v, list) and all(isinstance(i, str) for i in v)):
                raise _HttpError(400, f"'{key}' phải là danh sách id (chuỗi)")
            lists[key] = v
        with srv.write_lock:
            infos = set_allowed(srv.project_dir, allowed_ids=lists["allowed"], denied_ids=lists["denied"])
        self._json(200, {"balconies": _balconies_json(infos)})


GET_ROUTES = {
    "/": _Handler._get_index,
    "/scene.glb": _Handler._get_scene,
    "/api/state": _Handler._get_state,
    "/api/layout": _Handler._get_layout,
}
POST_ROUTES = {
    "/api/validate": _Handler._post_validate,
    "/api/save": _Handler._post_save,
    "/api/balconies": _Handler._post_balconies,
}


def make_server(project_dir, layout_name, library_dir=None, port=0):
    """Trả (server, url có token). Chỉ bind 127.0.0.1."""
    if layout_name is not None:
        layout_path(project_dir, layout_name)  # kiểm tra tên sớm (ConfigError)
    srv = EditorServer(project_dir, layout_name, library_dir, port)
    return srv, f"http://127.0.0.1:{srv.port}/?token={srv.token}"


def run_editor(project_dir, layout_name, library_dir=None, port=0, open_browser=True) -> int:
    srv, url = make_server(project_dir, layout_name, library_dir, port)
    print(f"Trình chỉnh đang chạy tại: {url}")
    print("Nhấn Ctrl+C để dừng.")
    if srv.library_note:
        print(f"Cảnh báo: không đọc được thư viện dàn nóng, dùng kích thước mặc định: {srv.library_note}", file=sys.stderr)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"Cảnh báo: không mở được trình duyệt ({e}); hãy mở URL trên bằng tay", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("Đã dừng trình chỉnh.")
    finally:
        srv.server_close()
    return 0
