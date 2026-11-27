# Giai đoạn 2c: phương án bố trí dàn nóng và trình chỉnh 3D - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. TDD từng task (test đỏ đúng lý do trước, rồi code). **Không commit.** Lỗi người dùng tiếng Việt, kế thừa `ConfigError`/`IngestError`. Không phá test cũ (342 pass, 1 skip). Chạy `python -X utf8 -m pytest -q` từ `D:\CFD_Tool`.

**Goal:** Dàn nóng thành biến thiết kế: nhiều phương án bố trí (file YAML), sinh tự động theo quy tắc (a) và từ bản vẽ (c), kiểm tra hợp lệ, dựng 3D theo phương án, và trình chỉnh 3D cục bộ để kéo/xoay dàn nóng bằng tay.

**Architecture:** gói mới `odu_cfd/layout/` (mô hình, IO, ban công, kiểm tra, sinh tự động, từ bản vẽ, server) dùng chung hình học `geometry/`; `geometry` ghi `plan.json`, `base.glb`, `balconies.yaml` và dựng theo phương án; trang chỉnh `viewer/editor.html` (three.js vendored, không thêm thư viện) nói chuyện với server `127.0.0.1`. Spec: `docs/specs/2026-11-27-stage2c-odu-layouts-design.md` (đọc kỹ trước khi làm).

**Tech Stack:** Python 3.12, shapely 2.1, PyYAML, `http.server`, three.js r147 UMD (đã có trong `src/odu_cfd/viewer/vendor/`), pytest.

---

## Phân công file (để các tác tử chạy song song không đụng nhau)

- **Nhóm A (Tasks 1-5):** `src/odu_cfd/layout/{__init__,model,io,balconies,validate,auto,from_ingest}.py`, `src/odu_cfd/schema.py` (chỉ `GeometryConfig` + `_parse_geometry`), tests `tests/test_layout_*.py`, `tests/test_schema_geometry.py`.
- **Nhóm B (Tasks 6-7):** `src/odu_cfd/geometry/*.py`, `src/odu_cfd/ingest/{config,pipeline}.py`, `src/odu_cfd/cli.py`, tests `tests/test_geometry_*.py`, `tests/test_ingest_*.py`, `tests/test_cli_layout.py`.
- **Nhóm C (Tasks 8-9):** `src/odu_cfd/layout/server.py`, `src/odu_cfd/viewer/editor.html`, `src/odu_cfd/viewer/editor_page.py`, tests `tests/test_editor_*.py`.

## Giao diện cố định giữa các nhóm

```python
# layout/model.py
@dataclass(frozen=True)
class OduPlacement:
    odu_id: str
    x: float
    y: float
    rotation_deg: float
    model_id: str | None = None
    size: tuple | None = None        # (w, d) mét hoặc None
    floors: tuple | None = None      # tuple[int] mức tầng 1-based hoặc None

@dataclass(frozen=True)
class Layout:
    name: str
    description: str
    source: str                      # architect | rule | drawing | manual
    floors: tuple                    # tuple[int] tăng dần, không trùng
    odus: tuple                      # tuple[OduPlacement]
    def floors_of(self, p: OduPlacement) -> tuple     # p.floors nếu có, ngược lại self.floors

SOURCES = ("architect", "rule", "drawing", "manual")
NAME_RE = r"^[A-Za-z0-9_.-]{1,64}$";  ID_RE = r"^[A-Za-z0-9_.-]+$"
def parse_floors(text) -> tuple      # "4-19,22-23" -> (4,...,19,22,23); lỗi: ConfigError
def format_floors(floors) -> str     # (4,5,6,9) -> "4-6,9"
def front_angle_deg(p) -> float      # (rotation_deg + 90) % 360

# layout/io.py
def layouts_dir(project_dir) -> Path           # <dự án>/layouts
def layout_path(project_dir, name) -> Path     # kiểm tra NAME_RE (ConfigError), không bao giờ thoát khỏi layouts/
def list_layouts(project_dir) -> list[str]
def read_layout(path) -> Layout                # safe_load, kiểm tra chặt, ConfigError nêu đường dẫn trường
def write_layout(path, layout, backup=True)    # UTF-8, ghi file tạm rồi đổi tên, sao lưu <tên>.yaml.bak nếu đã có

# layout/balconies.py
@dataclass(frozen=True)
class BalconyInfo: balcony_id: str; polygon: object; allowed: bool = True; note: str = ""   # shapely Polygon
def number_balconies(polygons) -> list[tuple[str, object]]    # sắp theo (round(cy,3), round(cx,3)); id B01.. (đủ chữ số theo số lượng, tối thiểu 2)
def write_balconies(project_dir, polygons) -> list[BalconyInfo]  # ghi <dự án>/balconies.yaml, giữ allowed/note của ban công cũ có tâm cách < 0.5 m
def read_balconies(project_dir) -> list[BalconyInfo]            # thiếu file: ConfigError bảo chạy `odu-cfd geometry <dự án>`
def set_allowed(project_dir, allowed_ids=None, denied_ids=None, all_allowed=False) -> list[BalconyInfo]

# layout/validate.py
@dataclass(frozen=True)
class Problem: level: str; odu_id: str | None; message: str      # level: "error" | "warning"
def odu_footprint(p, size) -> shapely Polygon                    # đúng công thức geometry.mesh.box_polygon (w theo x cục bộ, d theo y cục bộ, xoay CCW quanh (x, y))
def validate_layout(layout, balconies, num_floors, sizes) -> list[Problem]   # sizes: {odu_id: (w, d)}

# layout/auto.py
def auto_layout(balconies, body, *, name, floors, size, count=1, pattern="row", wall_gap_m=0.2,
                spacing_m=0.1, facing="outward", min_area_m2=0.0, only_ids=None, description="") -> tuple[Layout, list[str]]

# layout/from_ingest.py
def layout_from_ingest(odus, balconies, *, name, floors, description="") -> tuple[Layout, list[str]]   # odus: list[OduInstance]

# geometry: plan.json (ghi bởi run_geometry), base.glb, balconies.yaml ở <dự án>/
{
 "version": 1, "units": "m", "origin_xy_m": [x, y],
 "num_floors": 40, "floor_height_m": 3.3, "slab_thickness_m": 0.15, "rail_height_m": 1.1,
 "envelope": [{"exterior": [[x,y],...], "holes": [[[x,y],...]]}],
 "balconies": [{"id": "B01", "polygon": [[x,y],...], "area_m2": 12.6, "allowed": true}],
 "rails": [[[x,y],...]]
}

# layout/server.py (Nhóm C)
def make_server(project_dir, layout_name, library_dir=None, port=0) -> tuple[ThreadingHTTPServer, str]   # (server, url có token)
def run_editor(project_dir, layout_name, library_dir=None, port=0, open_browser=True) -> int
```

`geometry.mesh.box_polygon(cx, cy, w, d, rotation_deg)` đã có (xem `geometry/mesh.py`); `validate.odu_footprint` phải gọi lại hàm này để một công thức duy nhất.

---

## Task 1: Mô hình phương án, tầng, IO, kích thước mặc định (Nhóm A)

**Files:** Create `src/odu_cfd/layout/__init__.py` (rỗng), `model.py`, `io.py`; Modify `schema.py` (GeometryConfig thêm `odu_default_width_m=1.0`, `odu_default_depth_m=0.4`, dương hữu hạn, cận trên 5, lỗi nêu `geometry.<khóa>`; `templates/project.yaml` thêm comment hai khóa); Tests `tests/test_layout_model.py`, `tests/test_layout_io.py`, mở rộng `tests/test_schema_geometry.py`.

Hành vi bắt buộc (mỗi ý một test):
- `parse_floors`: `"4-19,22-23"` đúng; `" 1 , 3-4 "` chịu khoảng trắng; `"3-1"`, `"0"`, `"a"`, `""`, `"2,2"` (trùng), số thực `"1.5"` → ConfigError nêu đoạn sai. `format_floors((1,2,3,7))=="1-3,7"`, roundtrip với parse.
- `front_angle_deg`: rotation 0 → 90; 180 → 270; -90 → 0; 270 → 0 (chuẩn hóa [0,360)).
- `layout_path`: tên `"../x"`, `"a/b"`, `""`, 65 ký tự, `"a b"` → ConfigError; `"KT-v1.2"` ok; đường dẫn nằm dưới `<dự án>/layouts/`.
- `write_layout` rồi `read_layout` roundtrip bằng nhau (kể cả tiếng Việt trong description, `size`, `floors` riêng, `model_id`); ghi lần hai tạo `.yaml.bak` chứa bản cũ; không để lại file tạm; ghi thất bại không làm hỏng file cũ.
- `read_layout` từ chối (ConfigError nêu trường): thiếu `name`/`odus`/`floors`, `source` lạ, id sai regex hoặc trùng, x/y/rotation không hữu hạn hoặc bool, `size` không phải 2 số dương ≤ 5, `floors` lỗi, `odus` không phải danh sách, YAML hỏng, không UTF-8, tối đa 5000 dàn nóng; `name` trong file phải khớp tên file.
- `list_layouts`: sắp tăng dần, bỏ `.bak`, bỏ file tên sai regex, thư mục chưa có thì `[]`.
- `GeometryConfig`: mặc định 1.0/0.4; ghi đè; 0, âm, NaN, 6 → lỗi `geometry.odu_default_width_m`...

## Task 2: Ban công có id và `balconies.yaml` (Nhóm A)

**Files:** Create `layout/balconies.py`; Test `tests/test_layout_balconies.py`.

Test (dùng polygon tổng hợp, không cần bản vẽ):
- `number_balconies` ổn định: đảo thứ tự đầu vào cho cùng id; polygon thấp hơn (y nhỏ) có id nhỏ trước, cùng y thì x nhỏ trước; ≥ 100 ban công → id `B001`; 5 ban công → `B01`.
- `write_balconies` ghi file đọc lại bằng `read_balconies` đúng polygon (sai số 1e-9), centroid, area, `allowed=True` mặc định; file có comment đầu giải thích `allowed`.
- Ghi lại (chạy `geometry` lần hai) sau khi đặt `allowed=False` cho B02 và `note` → giữ nguyên cho ban công có tâm cách < 0.5 m dù id đổi (thêm một ban công mới ở giữa danh sách), ban công mới `allowed=True`; ban công cũ biến mất thì thôi.
- `set_allowed(allowed_ids=..., denied_ids=...)`; id lạ → ConfigError liệt kê id hợp lệ; `all_allowed=True` bật hết.
- `read_balconies` thiếu file → ConfigError chứa `odu-cfd geometry`.

## Task 3: Kiểm tra phương án (Nhóm A)

**Files:** Create `layout/validate.py`; Test `tests/test_layout_validate.py`.

Test code mẫu (ban công 4x2 m tại (5,0)-(9,2) id B01 allowed, và B02 (20,0)-(24,2) not allowed):

```python
from shapely.geometry import Polygon
from odu_cfd.layout.balconies import BalconyInfo
from odu_cfd.layout.model import Layout, OduPlacement
from odu_cfd.layout.validate import validate_layout, odu_footprint

B = [BalconyInfo("B01", Polygon([(5,0),(9,0),(9,2),(5,2)]), True),
     BalconyInfo("B02", Polygon([(20,0),(24,0),(24,2),(20,2)]), False)]
SIZE = (0.98, 0.37)

def _layout(odus, floors=(4, 5)):
    return Layout("t", "", "manual", floors, tuple(odus))

def _errors(problems): return [p for p in problems if p.level == "error"]

def test_valid_layout_has_no_problems():
    lay = _layout([OduPlacement("ODU-01", 6.0, 1.0, 0.0), OduPlacement("ODU-02", 7.5, 1.0, 0.0)])
    assert validate_layout(lay, B, 40, {"ODU-01": SIZE, "ODU-02": SIZE}) == []

def test_outside_balcony_is_error():
    lay = _layout([OduPlacement("ODU-01", 15.0, 10.0, 0.0)])
    errs = _errors(validate_layout(lay, B, 40, {"ODU-01": SIZE}))
    assert len(errs) == 1 and errs[0].odu_id == "ODU-01" and "ngoài ban công" in errs[0].message

def test_partly_outside_is_error():
    lay = _layout([OduPlacement("ODU-01", 5.2, 1.0, 0.0)])     # nhô ra khỏi mép trái x=5
    assert _errors(validate_layout(lay, B, 40, {"ODU-01": SIZE}))

def test_rotation_matters_for_fit():
    # ODU 0.98 x 0.37 xoay 90 độ chiếm 0.37 x 0.98: đặt sát mép phải x=9 vừa khít khi xoay 0, hỏng khi xoay 90 ở cùng tâm
    ok = _layout([OduPlacement("ODU-01", 8.4, 1.0, 0.0)])
    bad = _layout([OduPlacement("ODU-01", 8.9, 1.0, 90.0)])
    assert not _errors(validate_layout(ok, B, 40, {"ODU-01": SIZE}))
    assert _errors(validate_layout(bad, B, 40, {"ODU-01": SIZE}))

def test_denied_balcony_is_error():
    lay = _layout([OduPlacement("ODU-01", 22.0, 1.0, 0.0)])
    errs = _errors(validate_layout(lay, B, 40, {"ODU-01": SIZE}))
    assert len(errs) == 1 and "B02" in errs[0].message and "không cho phép" in errs[0].message

def test_overlap_is_error_only_on_shared_floors():
    a = OduPlacement("ODU-01", 6.0, 1.0, 0.0, floors=(4,))
    b = OduPlacement("ODU-02", 6.3, 1.0, 0.0, floors=(5,))
    assert not _errors(validate_layout(_layout([a, b]), B, 40, {"ODU-01": SIZE, "ODU-02": SIZE}))
    c = OduPlacement("ODU-03", 6.3, 1.0, 0.0, floors=(4, 5))
    errs = _errors(validate_layout(_layout([a, c]), B, 40, {"ODU-01": SIZE, "ODU-03": SIZE}))
    assert len(errs) == 1 and "chồng" in errs[0].message

def test_floors_out_of_range_and_empty():
    lay = _layout([OduPlacement("ODU-01", 6.0, 1.0, 0.0)], floors=(4, 41))
    assert any("tầng" in p.message for p in _errors(validate_layout(lay, B, 40, {"ODU-01": SIZE})))
    lay2 = _layout([OduPlacement("ODU-01", 6.0, 1.0, 0.0, floors=(99,))])
    assert _errors(validate_layout(lay2, B, 40, {"ODU-01": SIZE}))

def test_footprint_matches_mesh_box():
    from odu_cfd.geometry.mesh import box_polygon
    p = OduPlacement("O", 10.0, 5.0, 33.0)
    assert odu_footprint(p, SIZE).equals_exact(box_polygon(10.0, 5.0, SIZE[0], SIZE[1], 33.0), 1e-9)

def test_missing_size_is_error():
    lay = _layout([OduPlacement("ODU-01", 6.0, 1.0, 0.0)])
    assert _errors(validate_layout(lay, B, 40, {}))
```

Quy tắc: dung sai nằm trong ban công 1e-3 m (`balcony.buffer(1e-3).contains(footprint)`); dàn nằm trong ban công nào xác định bằng ban công chứa trọn nó (có thể nhiều ban công chạm nhau, lấy cái chứa); không ban công nào chứa trọn → "ngoài ban công (chân đế không nằm trọn trong ban công nào)"; ban công chứa có `allowed=False` → "ban công Bxx không cho phép đặt dàn nóng". Chồng nhau: diện tích giao > 1e-4 và tập tầng giao nhau không rỗng. Thông báo tiếng Việt có id dàn nóng.

## Task 4: Sinh bố trí theo quy tắc (a) (Nhóm A)

**Files:** Create `layout/auto.py`; Test `tests/test_layout_auto.py`.

Thuật toán (đã tính tay để test cố định, bám đúng): với mỗi ban công `allowed` có `area >= min_area_m2` (và id trong `only_ids` nếu có), theo thứ tự id:
1. `wall_pt = shapely.ops.nearest_points(balcony.centroid, body)[1]`; `n_out = normalize(centroid - wall_pt)`. Nếu `body` rỗng hoặc vector ≈ 0: dùng trục ngắn của `minimum_rotated_rectangle` hướng ra xa tâm `body`/gốc (chọn hướng +, ghi cảnh báo).
2. `t = (-n_out.y, n_out.x)`. Chiếu các đỉnh ban công lên `n_out` và `t` được khoảng `[n_min, n_max]`, `[t_min, t_max]`.
3. `facing == "outward"`: hướng thổi = `n_out`; `facing` là số: hướng thổi = góc đó (độ, ngược chiều kim đồng hồ từ +x). `rotation_deg = facing_angle - 90` (chuẩn hóa về (-180, 180]); hàng/ lưới luôn dựa lưng vào tường (phía `n_min`) bất kể hướng thổi.
4. Nửa kích thước hình chiếu của hộp đã xoay: gọi `u = (cos r, sin r)`, `v = (-sin r, cos r)` là trục cục bộ x, y sau xoay (`r = rotation_deg`), `hn = (w*|u·n| + d*|v·n|)/2` (dọc `n_out`), `ht = (w*|u·t| + d*|v·t|)/2` (dọc `t`). Khi mặt thổi hướng ra ngoài thì `hn = d/2`, `ht = w/2`. Mỗi dàn ở hàng `r`, cột `c` của hàng có `k` dàn: `n_center = n_min + wall_gap + hn + r*(2*hn + spacing)`; `t_center = t_mid + (c - (k-1)/2)*(2*ht + spacing)`, `t_mid = (t_min + t_max)/2`; tâm toàn cục = `n_center*n_out + t_center*t` (hệ chiếu trực chuẩn).
5. `row`: một hàng, `k = min(count, floor((t_len + spacing)/(2*ht + spacing)))`; `grid`: số cột tối đa `cols = floor((t_len + spacing)/(2*ht + spacing))`, số hàng tối đa `rows = floor((n_len - wall_gap + spacing)/(2*hn + spacing))`, điền từng hàng từ tường ra cho đến đủ `count`. Không đủ chỗ → đặt tối đa có thể và thêm cảnh báo `"ban công Bxx: chỉ đặt được m/count dàn nóng"`; `cols == 0 or rows == 0` → không đặt, cảnh báo.
6. Mỗi dàn đặt xong phải nằm trọn trong ban công (dung sai 1 mm) nếu không bỏ kèm cảnh báo. Id tuần tự `ODU-01..` toàn phương án. `source="rule"`, `size` ghi vào từng `OduPlacement.size`.
7. Ban công không allowed hoặc nhỏ hơn `min_area` bị bỏ qua (không cảnh báo, trừ khi `only_ids` nêu rõ ban công không allowed → cảnh báo).

Test bắt buộc (ban công B01 (5,0)-(9,2) và B02 (20,0)-(24,2) lõm trong thân nhà 30x20 nên `body = envelope - balconies`; B02 allowed True ở các test trừ khi nói khác):

```python
import math, pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union
from odu_cfd.layout.auto import auto_layout
from odu_cfd.layout.balconies import BalconyInfo
from odu_cfd.layout.validate import odu_footprint, validate_layout

ENV = Polygon([(0,0),(30,0),(30,20),(0,20)])
BALS = [BalconyInfo("B01", Polygon([(5,0),(9,0),(9,2),(5,2)]), True),
        BalconyInfo("B02", Polygon([(20,0),(24,0),(24,2),(20,2)]), True)]
BODY = ENV.difference(unary_union([b.polygon for b in BALS]))
SIZE = (0.98, 0.37)
KW = dict(name="r", floors=(4, 5), size=SIZE)

def test_row_of_two_back_to_wall_facing_out():
    lay, warns = auto_layout(BALS, BODY, count=2, **KW)
    assert warns == [] and [o.odu_id for o in lay.odus] == ["ODU-01","ODU-02","ODU-03","ODU-04"]
    a, b = lay.odus[0], lay.odus[1]
    assert (a.x, a.y) == pytest.approx((6.46, 1.615)) and (b.x, b.y) == pytest.approx((7.54, 1.615))
    assert (a.rotation_deg % 360) == pytest.approx(180.0)       # mặt thổi (rotation+90) = 270 = hướng -y = ra ngoài
    assert lay.source == "rule" and a.size == SIZE and lay.floors == (4, 5)
    assert not [p for p in validate_layout(lay, BALS, 40, {o.odu_id: SIZE for o in lay.odus}) if p.level == "error"]

def test_too_many_for_row_is_reduced_with_warning():
    lay, warns = auto_layout(BALS[:1], BODY, count=6, **KW)
    assert len(lay.odus) == 3 and any("B01" in w and "3/6" in w for w in warns)

def test_grid_fills_rows_from_wall_outwards():
    lay, _ = auto_layout(BALS[:1], BODY, count=4, pattern="grid", **KW)
    assert len(lay.odus) == 4
    rows = {}
    for o in lay.odus:
        rows.setdefault(round(o.y, 3), []).append(o)
    assert sorted(rows) == pytest.approx([1.145, 1.615]) and len(rows[1.615]) == 3 and len(rows[1.145]) == 1
    for o in lay.odus:
        assert BALS[0].polygon.buffer(1e-3).contains(odu_footprint(o, SIZE))

def test_denied_and_small_balconies_are_skipped():
    bals = [BalconyInfo("B01", BALS[0].polygon, False), BALS[1]]
    lay, _ = auto_layout(bals, BODY, count=1, **KW)
    assert [round(o.x, 1) for o in lay.odus] == [22.0]
    lay2, _ = auto_layout(BALS, BODY, count=1, min_area_m2=9.0, **KW)
    assert lay2.odus == ()

def test_only_ids_filter():
    lay, _ = auto_layout(BALS, BODY, count=1, only_ids=["B02"], **KW)
    assert len(lay.odus) == 1 and lay.odus[0].x > 20

def test_numeric_facing_changes_rotation_only():
    lay, _ = auto_layout(BALS[:1], BODY, count=1, facing=0.0, **KW)    # thổi theo +x
    assert lay.odus[0].rotation_deg == pytest.approx(-90.0)
    assert lay.odus[0].y == pytest.approx(2.0 - 0.2 - 0.49)             # dựa lưng tường (y=2), nửa bề sâu theo y là w/2=0.49
    # dàn xoay -90 chiếm 0.37 x 0.98 -> vẫn phải nằm trọn ban công
    fp = odu_footprint(lay.odus[0], SIZE)
    assert BALS[0].polygon.buffer(1e-3).contains(fp)

def test_oversize_unit_is_dropped_with_warning():
    lay, warns = auto_layout(BALS[:1], BODY, count=1, name="r", floors=(4,), size=(5.0, 3.0))
    assert lay.odus == () and warns

def test_deterministic():
    a, _ = auto_layout(BALS, BODY, count=2, **KW)
    b, _ = auto_layout(list(reversed(BALS)), BODY, count=2, **KW)
    assert a == b

def test_works_when_balcony_projects_outside_the_envelope():
    proj = [BalconyInfo("B01", Polygon([(5,-2),(9,-2),(9,0),(5,0)]), True)]
    body = ENV                                                          # ban công nhô ra phía y<0, tường tại y=0
    lay, warns = auto_layout(proj, body, count=1, **KW)
    o = lay.odus[0]
    assert o.y == pytest.approx(-0.2 - 0.185) and (o.rotation_deg % 360) == pytest.approx(180.0)
```


## Task 5: Từ bản vẽ (c) (Nhóm A)

**Files:** Create `layout/from_ingest.py`; Test `tests/test_layout_from_ingest.py`.

`layout_from_ingest(odus, balconies, *, name, floors, description="")`: mỗi `OduInstance` → `OduPlacement(odu_id=inst.odu_id, x, y = inst.center, rotation_deg=inst.rotation_deg, size=None)`, `source="drawing"`. Id đã khớp regex (config đã chặn), nếu không khớp thì làm sạch như `ODU-NN`. Tâm không nằm trong ban công nào → vẫn giữ, thêm cảnh báo `"ODU-xx không rơi vào ban công nào"`. Tâm nằm trong ban công không cho phép → cảnh báo. Test: ca bình thường (4 dàn của bản vẽ tổng hợp nằm trong 2 ban công: ODU tại (5.99,1.035), (7.49,1.035), (20.99,1.035), (22.49,1.035)), không có cảnh báo; dàn ngoài ban công có cảnh báo nhưng vẫn có trong phương án; danh sách rỗng cho phương án rỗng (odus=()).

## Task 6: Dựng 3D theo phương án (Nhóm B)

**Files:** Modify `geometry/build.py`, `geometry/pipeline.py`, `ingest/config.py`, `ingest/pipeline.py`; Tests mở rộng `tests/test_geometry_build.py`, `tests/test_geometry_pipeline.py`, `tests/test_ingest_config.py`, `tests/test_ingest_pipeline.py`; mới `tests/test_geometry_layout.py`. Cần Task 1-3 của nhóm A có mặt (import `odu_cfd.layout`); nếu chưa có thì chờ/ báo BLOCKED.

1. `build_building(..., odu_floors=None)`: `odu_floors: dict[odu_id -> tuple[int]]` chỉ số tầng 0-based mà dàn đó xuất hiện (None = mọi tầng như cũ). Tầng ngoài [0, num_floors) → IngestError. Test: dàn chỉ ở tầng 3-4 (0-based 3,4) ra đúng vùng `ODU-01_f03`, `_f04` và không có vùng khác; z đúng `3*floor_height + slab`.
2. `validate_for_geometry(cfg, require_odus=False)`: ODU không còn bắt buộc (mặc định). Cập nhật test cũ `test_confirm_without_odus_fails` và các test liên quan thành: xác nhận được khi không có dàn nóng nhưng vẫn cần wall_ext hoặc slab. `confirm_ingest` in cảnh báo không có dàn nóng (hướng dẫn `layout`).
3. `run_geometry(project_dir, library_dir=None, layout_name=None)`:
   - Luôn sau `extract_plan`: `write_balconies(project_dir, plan.balconies)` (kết quả dùng id), ghi `input/geometry/plan.json` đúng schema trong phần "Giao diện cố định" (đa giác theo vòng ngoài/lỗ, không đóng lặp điểm đầu cuối? — dùng danh sách điểm không lặp điểm cuối), ghi `input/geometry/base.glb` (nhóm building, balcony, rail của mô hình cơ sở).
   - Không có `layout_name`: giữ hành vi cũ (dàn nóng từ `ingest.yaml`, có thể rỗng: cảnh báo "chưa có dàn nóng: tạo phương án bằng `odu-cfd layout auto/from-ingest` hoặc `odu-cfd edit`"; nhóm `odu` rỗng; STL `odu.stl` rỗng vẫn ghi). Đầu ra vẫn ở `input/geometry/` phẳng như cũ.
   - Có `layout_name`: `read_layout(layout_path(...))`, `read_balconies`, kích thước mỗi dàn: `placement.size` nếu có, else thư viện theo `placement.model_id or project.odu.model_id` (nếu có `library_dir` và tìm thấy: `width_m`/`depth_m`), else `GeometryConfig.odu_default_width_m/depth_m`; chiều cao: thư viện theo model, else `odu_default_height_m`. `validate_layout(...)`: có lỗi → IngestError liệt kê hết (không ghi file), cảnh báo → stderr `Cảnh báo: ...`. Dựng với `odu_floors` = tầng của từng dàn (mức tầng - 1). Đầu ra vào `input/geometry/layouts/<tên>/`: `building.stl`, `balcony.stl`, `rail.stl`, `odu.stl`, `scene.glb`, `geometry.json` (như cũ + `"layout": {"name","source","floors","description","odus":[{id,x,y,rotation_deg,front_angle_deg,model_id,size,size_source,floors}]}`), `viewer.html`.
   - `build_building` nhận chiều cao dàn nóng theo từng dàn: thêm tham số `odu_heights: dict[id->float] | None` (None dùng `odu_height_m`/mặc định như cũ).
   - Test: layout hợp lệ (dựng từ bản vẽ tổng hợp: ingest + confirm + `layout auto`-tương đương tạo YAML tay) → các file tồn tại, số vùng ODU = số dàn × số tầng áp dụng, `geometry.json["layout"]` đúng, mọi phần kín; layout lỗi (ngoài ban công) → mã 2 và không có thư mục `layouts/<tên>/`; layout không tồn tại → lỗi liệt kê `list_layouts`; hai phương án khác nhau cho hai thư mục khác nhau với STL khác nhau; `plan.json` hợp lệ JSON đúng schema (id khớp `balconies.yaml`, số ban công = 2 với bản vẽ tổng hợp); `base.glb` không chứa node nhóm `odu`.
4. CLI `geometry <dự án> [--layout TÊN] [--library DIR]`, `view <dự án> [--layout TÊN] [--no-open]` (mở `layouts/<tên>/viewer.html` nếu có `--layout`, thiếu file → IngestError bảo chạy `geometry --layout`).

## Task 7: Lệnh CLI cho phương án và ban công (Nhóm B)

**Files:** Modify `cli.py`, `PROJECT_SUBDIRS` thêm `"layouts"`; Test `tests/test_cli_layout.py`. Cần Task 1-5.

Lệnh (tất cả đọc `plan.json`/`balconies.yaml`, thiếu thì lỗi hướng dẫn chạy `odu-cfd geometry <dự án>`):
- `layout balconies <dự án> [--allow B01,B02] [--deny B03] [--allow-all]`: đặt cờ rồi in bảng `id, diện tích, allowed, tâm`.
- `layout auto <dự án> --name TÊN --floors "4-19,22-23" [--count N=1] [--pattern row|grid] [--facing outward|ĐỘ] [--wall-gap 0.2] [--spacing 0.1] [--min-area 0] [--balconies B01,B02] [--size W,D] [--library DIR] [--description ...] [--force]`: `size` mặc định lấy từ thư viện (model của dự án) rồi mặc định `geometry`; body = envelope trừ hợp ban công từ `plan.json`; in cảnh báo; từ chối ghi đè phương án đã có trừ `--force`.
- `layout from-ingest <dự án> --name TÊN --floors ... [--force]`.
- `layout validate <dự án> TÊN [--library DIR]`: in từng vấn đề (lỗi/cảnh báo), mã 2 khi có lỗi, 0 khi sạch hoặc chỉ cảnh báo.
- `layout list <dự án>`: tên, nguồn, số dàn nóng, tầng.
- `layout new <dự án> --name TÊN --floors ...`: phương án trống (`source: manual`) để chỉnh bằng `edit`.
- `edit <dự án> [--layout TÊN] [--library DIR] [--port N] [--no-open]`: gọi `layout.server.run_editor` (nhập lười để Nhóm C hoàn thiện sau); `--layout` không tồn tại thì tạo trống với `floors` từ `--floors` (bắt buộc khi tạo mới).
Test từng lệnh bằng `main([...])`, bản vẽ tổng hợp qua `ingest` + `--confirm` + `geometry`; `edit` test bằng monkeypatch `run_editor`.

## Task 8: Server trình chỉnh (Nhóm C)

**Files:** Create `layout/server.py`; Test `tests/test_editor_server.py` (server chạy trong thread, `http.client`, cổng 0). Cần Task 1-3 và fixture dự án có `plan.json`, `base.glb`, `balconies.yaml` (tạo bằng cách chạy `main` trên bản vẽ tổng hợp sau khi Nhóm B xong; trong lúc chờ có thể dựng fixture tay đúng schema).

- `make_server(project_dir, layout_name, library_dir=None, port=0)` trả `(server, url)`; `url = http://127.0.0.1:<port>/?token=<token>`; token `secrets.token_urlsafe(16)`; chỉ bind `127.0.0.1`. `run_editor(...)`: `serve_forever`, in URL, `webbrowser.open(url)` nếu `open_browser`, thoát sạch bằng Ctrl+C (mã 0).
- `GET /`: trả `editor.html` (đọc bằng `editor_page.load_editor_html(token)` thay `__TOKEN__`), `Content-Security-Policy: default-src 'self' 'unsafe-inline' data: blob:`, `Cache-Control: no-store`. `GET /scene.glb`: nội dung `input/geometry/base.glb` (thiếu → 404 JSON tiếng Việt bảo chạy `geometry`). Đường dẫn khác → 404; không phục vụ file tùy ý.
- `GET /api/state`: `{"project", "layout": <dict>, "layout_exists": bool, "layouts": [tên...], "plan": <plan.json>, "balconies": [{id, polygon, allowed, note}], "models": [{model_id, width_m, depth_m, height_m}], "defaults": {"width_m","depth_m","height_m"}, "num_floors", "floor_height_m", "slab_thickness_m", "token_ok": true}`. Layout dạng JSON `{"name","description","source","floors": "4-19,22-23","odus":[{id,x,y,rotation_deg,model_id,size,floors}]}`.
- `POST /api/validate` `{layout}` → `{"problems":[{level,odu_id,message}], "sizes": {id:[w,d]}}` (sizes giải quyết theo quy tắc ở Task 6). `POST /api/save` `{layout, name?}`: kiểm tra, có lỗi → HTTP 422 `{"problems": [...]}`, không ghi; sạch → `write_layout` (sao lưu), trả `{"saved": true, "name": ..., "problems": [cảnh báo]}`. `POST /api/balconies` `{"allowed": [...], "denied": [...]}` → `set_allowed`, trả danh sách ban công mới. `GET /api/layout?name=X` → layout dạng JSON (để chuyển phương án).
- Bảo vệ (mỗi cái một test): `Host` không phải `127.0.0.1:<port>`/`localhost:<port>` → 403 (chống DNS rebinding); có `Origin` mà khác `http://127.0.0.1:<port>`/`http://localhost:<port>` → 403; mọi `POST` thiếu hoặc sai `X-Token` → 403; `Content-Length` > 1 MB hoặc thiếu → 413/411; JSON hỏng → 400 tiếng Việt; tên phương án sai regex → 400 (không ghi file); `..` trong tên → 400; không bao giờ tạo file ngoài `layouts/` và `balconies.yaml` (test: liệt kê thư mục dự án trước/sau). Luồng: lưu hợp lệ rồi `read_layout` ra đúng, lưu lỗi trả 422 và file cũ giữ nguyên, bật/tắt ban công cập nhật `balconies.yaml`.
- Mã hóa UTF-8 mọi phản hồi JSON (`ensure_ascii=False`), `Content-Type` đúng.

## Task 9: Trang chỉnh 3D (Nhóm C)

**Files:** Create `viewer/editor.html`, `viewer/editor_page.py` (`load_editor_html(token) -> str`: đọc template và các file vendor `three.min.js`, `GLTFLoader.js`, `OrbitControls.js` nội tuyến như `geometry_viewer.py`; thay `__TOKEN__` bằng chuỗi JSON an toàn; không dùng `</script` trong dữ liệu); Modify `pyproject.toml` (package-data `viewer/*.html` đã có); Test `tests/test_editor_page.py`.

Yêu cầu giao diện (spec mục 6), chia lớp để kiểm thử được:
- **Lõi không phụ thuộc DOM** trong một đối tượng `window.EditorAPI`: `state` (layout hiện tại, ban công, tầng đang chỉnh, chọn, đã sửa), `addOdu(balconyId)`, `moveOdu(id, x, y)`, `rotateOdu(id, deltaDeg)`, `setOdu(id, {x,y,rotation_deg})`, `deleteOdu(id)`, `duplicateOdu(id)`, `undo()`, `redo()`, `snapPoint(x,y)`, `snapAngle(a)`, `validate()` (gọi `POST /api/validate`, trả Promise), `save(name?)`, `toggleBalcony(id)`. Mọi thao tác chuột/phím chỉ gọi các hàm này.
- **Hiển thị:** nạp `/scene.glb` (khối nhà xám, sàn be, lan can xanh lơ); ban công vẽ phủ đa giác ở mặt sàn tầng đang chỉnh (xanh = cho phép, xám = không) kèm nhãn id; dàn nóng là hộp `w x d x h` (kích thước từ `/api/state` theo `size`/model/mặc định) tại cao độ `(tầng-1)*floor_height + slab`, mũi tên hướng thổi (trục cục bộ +y), màu: thường cam, chọn vàng, vi phạm đỏ; dàn nóng của các tầng khác trong `floors` hiện mờ (instancing đơn giản hoặc nhóm). Hệ trục: mô hình z lên, glTF y lên (đổi `(x,y,z) -> (x, z, -y)` như `export.write_glb`).
- **Camera:** nút "3D" (perspective + OrbitControls) và "Mặt bằng" (OrthographicCamera nhìn xuống, pan/zoom, không xoay).
- **Tương tác:** bấm chọn dàn nóng (raycast); kéo di chuyển trên mặt phẳng ngang của tầng đang chỉnh (chặn OrbitControls khi đang kéo); R / Shift+R xoay ±15°, nút ±90°; ô nhập x, y, góc xoay, hướng thổi (hai ô đồng bộ: hướng thổi = xoay + 90); thêm (ở tâm ban công đang chọn, ban công chọn bằng bấm vào đa giác), nhân bản (lệch 0.3 m), xóa (Delete); bắt dính lưới 0.05 m và góc 15° (checkbox); Undo/Redo (Ctrl+Z/Ctrl+Y); Ctrl+S lưu; "Lưu thành phương án mới" (hỏi tên bằng ô nhập trong trang, không dùng `prompt`); danh sách phương án để chuyển (hỏi nếu có thay đổi chưa lưu); chỉ báo "chưa lưu"; bảng vấn đề (lỗi đỏ, cảnh báo vàng) từ `validate` (debounce 200 ms sau mỗi thay đổi); nút bật/tắt `allowed` của ban công đang chọn (gọi `/api/balconies`).
- **Tự kiểm `?selftest=1`:** khi trang tải xong (GLB đã nạp) chạy tuần tự qua `EditorAPI`: thêm một dàn nóng ở ban công đầu tiên cho phép, di chuyển, xoay 90°, undo, redo, `validate`, `save("selftest")`; ghi kết quả JSON vào `<pre id="selftest">` (các bước, tọa độ, số vấn đề, kết quả lưu) và `document.title = "selftest-done"`. Test Python: khởi động server (`make_server` trong thread, dự án tổng hợp), chạy `msedge --headless=new --disable-gpu --dump-dom <url>?...&selftest=1` (bỏ qua test nếu không có Edge), phân tích JSON trong DOM và kiểm tra file `layouts/selftest.yaml` được ghi đúng. Nếu `--dump-dom` không chờ bất đồng bộ, dùng cờ phù hợp (ví dụ `--virtual-time-budget` nếu không làm hỏng, hoặc `--timeout`); nếu không có cách tin cậy thì nói rõ trong báo cáo và chụp ảnh bằng `--screenshot` làm bằng chứng thay thế.
- Test tĩnh không cần Edge (`tests/test_editor_page.py`): HTML tự đủ (không `src/href` http, không `<script src`), có `EditorAPI`, `__TOKEN__` được thay, token có ký tự đặc biệt không phá HTML/JS, không chứa `</script` trong dữ liệu nhúng.
- Báo cáo chụp ảnh: 3D và mặt bằng với dự án tổng hợp có một phương án, bằng Edge headless, xem bằng công cụ Read và nói thẳng thấy gì và chưa kiểm chứng gì (kéo chuột thật, bàn phím thật).

## Task 10: Nghiệm thu và tài liệu (người điều phối)

- Chạy toàn bộ test. Cross-review độc lập (opus, chỉ đọc) và sửa theo phát hiện.
- Trên `SPRING_PLAN.dxf`: `geometry`, `layout balconies`, `layout auto` (4 dàn nóng/ban công dạng grid), mở trình chỉnh bằng Edge headless chụp ảnh, `geometry --layout`, xem viewer. Ghi `docs/notes/2026-11-27-stage2c-findings.md`.
- Cập nhật `README`/ghi chú sử dụng cho người dùng cuối nếu có.
