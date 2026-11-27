# Giai đoạn 2: ingest + geometry + viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Từ DWG/DXF của dự án, tự động nhận diện mặt bằng, layer, dàn nóng (có bước xác nhận bằng ảnh), dựng mô hình 3D (STL + glTF) và viewer 3D offline.

**Architecture:** `ingest` (DWG→DXF bằng LibreDWG, đọc DXF thành primitive đơn vị mét, gom view, phân vai layer, tìm dàn nóng, ghi `ingest.yaml` + `overlay.png`) → `geometry` (đa giác 2D bằng shapely, lưới tam giác kín bằng numpy tự viết, xuất STL nhiều vùng và GLB) → `viewer` (HTML một file, three.js đặt sẵn). Spec: `docs/specs/2026-11-26-stage2-ingest-geometry-design.md`.

**Tech Stack:** Python 3.12, ezdxf 1.4, shapely 2.1 (`constrained_delaunay_triangles`), numpy, matplotlib (Agg), PyYAML, pytest. Không dùng pyvista/trimesh trong code chạy.

**Quy ước (giống giai đoạn 1):** làm TDD từng task (viết test, thấy FAIL đúng lý do, viết code, thấy PASS). Lỗi người dùng nêu bằng tiếng Việt, kế thừa `ConfigError` để `cli.main` trả mã 2 và in `Lỗi: ...`. **Không commit** (người điều phối commit sau). Đọc code hiện có trong `src/odu_cfd/` (đặc biệt `schema.py`, `cli.py`) và bám cùng phong cách. Chạy toàn bộ `python -m pytest -q` từ `D:\CFD_Tool` sau mỗi task, không được làm hỏng 106 test cũ.

---

## File Structure

```
src/odu_cfd/errors.py              + IngestError(ConfigError)
src/odu_cfd/schema.py              + GeometryConfig, Project.geometry (mặc định, tùy chọn)
src/odu_cfd/templates/project.yaml + phần geometry (comment)
src/odu_cfd/ingest/__init__.py
  dwg.py            locate_dwg2dxf, convert_dwg_to_dxf
  drawing.py        Primitive, Text, Drawing, load_drawing
  layers.py         ROLES, classify_layers
  views.py          View, find_views
  odu_detect.py     OduInstance, detect_odus
  config.py         IngestConfig, write_ingest_config, read_ingest_config
  overlay.py        render_overlay
  pipeline.py       run_ingest, confirm_ingest
src/odu_cfd/geometry/__init__.py
  mesh.py           Mesh, merge, volume, is_closed, extrude_polygon, box
  plan2d.py         Plan2D, extract_plan
  build.py          BuildingModel, build_building
  export.py         write_stl, write_glb
  pipeline.py       run_geometry
src/odu_cfd/viewer/__init__.py
  geometry_viewer.py  write_viewer_html
  vendor/three.min.js, GLTFLoader.js, OrbitControls.js, LICENSE-three.txt, SHA256SUMS
src/odu_cfd/cli.py                 + lệnh ingest, geometry, view
tests/dxf_factory.py               sinh DXF tổng hợp
tests/conftest.py                  + fixture tower_dxf
tests/test_*.py                    theo từng task
pyproject.toml                     + dependencies, package-data
```

## Bản vẽ tổng hợp dùng chung cho test (tạo ở Task 3, dùng ở các task sau)

Đơn vị mm khi `unit_code=4`, mét khi khác 4. Thân nhà 30×20 m (đường bao 4 LINE layer `A-WALL`), hai ban công lõm 4×2 m (LWPOLYLINE kín layer `A-BALC`) tại (5,0)–(9,2) và (20,0)–(24,2), hai đoạn lan can (LINE layer `A-HANDRAIL`) dài 4 m dọc y=0 tại x 5–9 và 20–24, bốn dàn nóng (INSERT block `ODU_TEST` 0,98×0,47 m, góc block ở gốc, layer `M-EQPM`) chèn tại (5,5;0,8), (7,0;0,8), (20,5;0,8), (22,0;0,8), một block `ENCLOSURE` 2,8×3,2 m chèn tại (12,5) cùng layer `M-EQPM`, và một cụm xa ở x = 500…510 m (hình chữ nhật 10×10 m layer `A-WALL` + một LINE `A-HANDRAIL`) để kiểm thử việc tách view.

---

### Task 1: IngestError, GeometryConfig, phụ thuộc

**Files:**
- Modify: `src/odu_cfd/errors.py`, `src/odu_cfd/schema.py`, `src/odu_cfd/templates/project.yaml`, `pyproject.toml`
- Test: `tests/test_schema_geometry.py`

- [ ] **Step 1: Viết test (FAIL)**

```python
import pytest

from odu_cfd.errors import ConfigError, IngestError
from odu_cfd.schema import parse_project


def test_ingest_error_is_config_error():
    assert issubclass(IngestError, ConfigError)


def test_geometry_section_is_optional_with_defaults(valid_dict):
    g = parse_project(valid_dict).geometry
    assert (g.slab_thickness_m, g.rail_height_m, g.rail_thickness_m, g.odu_default_height_m) == (
        0.15,
        1.1,
        0.05,
        1.0,
    )


def test_geometry_overrides_only_given_keys(valid_dict):
    valid_dict["geometry"] = {"rail_height_m": 1.2}
    g = parse_project(valid_dict).geometry
    assert g.rail_height_m == 1.2
    assert g.slab_thickness_m == 0.15


@pytest.mark.parametrize(
    "key,val",
    [
        ("slab_thickness_m", 0),
        ("rail_height_m", -1),
        ("rail_thickness_m", "x"),
        ("odu_default_height_m", float("nan")),
    ],
)
def test_geometry_rejects_bad_values(valid_dict, key, val):
    valid_dict["geometry"] = {key: val}
    with pytest.raises(ConfigError, match=f"geometry.{key}"):
        parse_project(valid_dict)
```

- [ ] **Step 2:** `python -m pytest tests/test_schema_geometry.py -q` → FAIL (thiếu `IngestError`/`geometry`).
- [ ] **Step 3: Code.**
  - `errors.py`: `class IngestError(ConfigError): """Lỗi đọc bản vẽ hoặc dựng hình học."""`.
  - `schema.py`: thêm frozen dataclass `GeometryConfig(slab_thickness_m=0.15, rail_height_m=1.1, rail_thickness_m=0.05, odu_default_height_m=1.0)`; thêm `geometry: GeometryConfig = GeometryConfig()` làm trường **cuối** của `Project` (có mặc định, không đổi thứ tự trường cũ). `parse_project` đọc phần `geometry` tùy chọn bằng các helper có sẵn (`_num` dương hữu hạn), thiếu phần/khóa thì dùng mặc định; thông báo lỗi có đường dẫn `geometry.<khóa>`. Bám cách `schema.py` xử lý phần tùy chọn/khóa lạ hiện có.
  - `templates/project.yaml`: thêm khối comment `# geometry:` liệt kê 4 khóa và giá trị mặc định.
  - `pyproject.toml`: `dependencies = ["PyYAML>=6.0", "ezdxf>=1.1", "numpy>=1.26", "shapely>=2.1", "matplotlib>=3.8"]`; `package-data` thêm `viewer/vendor/*`.
- [ ] **Step 4:** `python -m pytest -q` → toàn bộ PASS (106 cũ + mới).

---

### Task 2: Chuyển DWG sang DXF (`ingest/dwg.py`)

**Files:**
- Create: `src/odu_cfd/ingest/__init__.py` (rỗng), `src/odu_cfd/ingest/dwg.py`
- Test: `tests/test_ingest_dwg.py`

Giao diện: `locate_dwg2dxf() -> Path`; `convert_dwg_to_dxf(dwg: Path, out: Path, exe: Path | None = None) -> Path`; hàm nội bộ `_bundled_candidates() -> list[Path]` (trả `[<repo>/third_party/libredwg/dwg2dxf.exe, .../dwg2dxf]`, `<repo>` = `Path(__file__).parents[3]`).

Quy tắc: tìm theo thứ tự `ODU_CFD_DWG2DXF` (nếu đặt mà không tồn tại thì lỗi nêu đường dẫn đó), bundled, `shutil.which("dwg2dxf")`; không thấy thì `IngestError` có cụm "xuất DXF". File phải bắt đầu bằng `b"AC10"` (header DWG) nếu không lỗi "không phải DWG". Gọi `subprocess.run([str(exe), "-y", "-o", str(out), str(dwg)], capture_output=True, text=True, timeout=900)`. Mã thoát ≥ 128 (lỗi nặng theo LibreDWG) hoặc không có file ra/rỗng → `IngestError`; mã 1–127 là lỗi có thể bỏ qua, vẫn nhận kết quả nếu có file ra. Hết thời gian (`subprocess.TimeoutExpired`) → `IngestError`. Bỏ qua chuyển đổi nếu `out` đã có, không rỗng và mới hơn `dwg` (trả `out`).

- [ ] **Step 1: Viết test (FAIL)**

```python
import os
import subprocess
import time

import pytest

from odu_cfd.errors import IngestError
from odu_cfd.ingest import dwg


def _fake_dwg(path, magic=b"AC1032"):
    path.write_bytes(magic + b"\x00" * 100)
    return path


def test_locate_prefers_env(monkeypatch, tmp_path):
    exe = tmp_path / "dwg2dxf.exe"
    exe.write_text("")
    monkeypatch.setenv("ODU_CFD_DWG2DXF", str(exe))
    assert dwg.locate_dwg2dxf() == exe


def test_locate_env_pointing_nowhere_is_error(monkeypatch, tmp_path):
    monkeypatch.setenv("ODU_CFD_DWG2DXF", str(tmp_path / "none.exe"))
    with pytest.raises(IngestError, match="none.exe"):
        dwg.locate_dwg2dxf()


def test_locate_missing_asks_for_dxf(monkeypatch):
    monkeypatch.delenv("ODU_CFD_DWG2DXF", raising=False)
    monkeypatch.setattr(dwg, "_bundled_candidates", lambda: [])
    monkeypatch.setattr(dwg.shutil, "which", lambda name: None)
    with pytest.raises(IngestError, match="xuất DXF"):
        dwg.locate_dwg2dxf()


def test_rejects_file_that_is_not_dwg(tmp_path):
    f = tmp_path / "a.dwg"
    f.write_bytes(b"hello world")
    with pytest.raises(IngestError, match="không phải DWG"):
        dwg.convert_dwg_to_dxf(f, tmp_path / "a.dxf", exe=tmp_path / "x.exe")


def _stub(monkeypatch, out, code, write=True):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if write:
            out.write_text("0\nEOF\n")
        return subprocess.CompletedProcess(cmd, code, "", "boom")

    monkeypatch.setattr(dwg.subprocess, "run", fake_run)
    return calls


def test_convert_runs_tool(monkeypatch, tmp_path):
    src, out = _fake_dwg(tmp_path / "a.dwg"), tmp_path / "a.dxf"
    exe = tmp_path / "dwg2dxf.exe"
    calls = _stub(monkeypatch, out, 0)
    assert dwg.convert_dwg_to_dxf(src, out, exe=exe) == out
    assert calls[0][0] == str(exe) and str(src) in calls[0] and str(out) in calls[0]


def test_recoverable_exit_code_is_accepted(monkeypatch, tmp_path):
    src, out = _fake_dwg(tmp_path / "a.dwg"), tmp_path / "a.dxf"
    _stub(monkeypatch, out, 1)
    assert dwg.convert_dwg_to_dxf(src, out, exe=tmp_path / "e.exe") == out


def test_critical_exit_code_fails(monkeypatch, tmp_path):
    src, out = _fake_dwg(tmp_path / "a.dwg"), tmp_path / "a.dxf"
    _stub(monkeypatch, out, 128, write=False)
    with pytest.raises(IngestError, match="xuất DXF"):
        dwg.convert_dwg_to_dxf(src, out, exe=tmp_path / "e.exe")


def test_no_output_file_fails(monkeypatch, tmp_path):
    src, out = _fake_dwg(tmp_path / "a.dwg"), tmp_path / "a.dxf"
    _stub(monkeypatch, out, 0, write=False)
    with pytest.raises(IngestError):
        dwg.convert_dwg_to_dxf(src, out, exe=tmp_path / "e.exe")


def test_up_to_date_output_is_reused(monkeypatch, tmp_path):
    src, out = _fake_dwg(tmp_path / "a.dwg"), tmp_path / "a.dxf"
    out.write_text("0\nEOF\n")
    os.utime(src, (time.time() - 100, time.time() - 100))
    calls = _stub(monkeypatch, out, 0)
    assert dwg.convert_dwg_to_dxf(src, out, exe=tmp_path / "e.exe") == out
    assert calls == []
```

- [ ] **Step 2:** chạy → FAIL (module chưa có). **Step 3:** viết `dwg.py` theo quy tắc trên. **Step 4:** `python -m pytest tests/test_ingest_dwg.py -q` PASS, rồi `python -m pytest -q`.

---

### Task 3: Đọc DXF thành primitive (`ingest/drawing.py`) và DXF tổng hợp

**Files:**
- Create: `tests/dxf_factory.py`, `src/odu_cfd/ingest/drawing.py`
- Modify: `tests/conftest.py` (thêm fixture)
- Test: `tests/test_ingest_drawing.py`

Giao diện:

```python
UNIT_SCALE = {"mm": 0.001, "cm": 0.01, "m": 1.0, "in": 0.0254, "ft": 0.3048}
INSUNITS = {1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}

@dataclass(frozen=True)
class Primitive:
    kind: str                       # "path" | "insert"
    layer: str
    points: tuple                   # ((x, y), ...) mét. path: đã làm phẳng; insert: 4 góc chân đế theo thứ tự quanh hình
    closed: bool = False
    name: str = ""                  # tên block (insert)
    rotation_deg: float = 0.0       # insert

@dataclass(frozen=True)
class Text:
    text: str; x: float; y: float; layer: str

@dataclass(frozen=True)
class Drawing:
    primitives: tuple
    texts: tuple
    layers: tuple                   # tên layer có primitive, đã sắp xếp
    units: str
    scale_to_m: float
    skipped: dict                   # {loại đối tượng: số lượng} không đọc được/không hỗ trợ

def load_drawing(path, units_override: str | None = None) -> Drawing
```

Quy tắc:
- Đọc bằng `ezdxf.recover.readfile`. Chỉ modelspace.
- Đơn vị: `units_override` (khóa của `UNIT_SCALE`, khác thì `IngestError`) thắng; nếu không có thì `$INSUNITS` qua `INSUNITS`; `0` hoặc không thuộc bảng → `IngestError` chứa "đơn vị" và gợi ý `--units`.
- LINE, ARC, CIRCLE, LWPOLYLINE, POLYLINE, SPLINE, ELLIPSE → `ezdxf.path.make_path(e).flattening(0.005 / scale_to_m)` (độ lệch tối đa 5 mm), mỗi sub-path thành một Primitive `path`; `closed` = `path.is_closed` hoặc cờ close của polyline. Đối tượng lỗi hoặc loại khác (HATCH, DIMENSION, ...) cộng vào `skipped` theo `dxftype()`.
- INSERT: chân đế = hộp bao (`ezdxf.bbox.extents(block_layout)`, dùng `bbox.Cache` hoặc dict theo tên block) biến đổi bằng `insert.matrix44()` (kiểm tra API này trong ezdxf 1.4.4; nếu không có thì tự dựng từ insert, xscale/yscale, rotation). Block rỗng (không có dữ liệu bao) thì bỏ qua và cộng `skipped["INSERT-empty"]`. `rotation_deg` = `insert.dxf.rotation`.
- TEXT/MTEXT → `Text` (MTEXT dùng `plain_text()`, cắt 80 ký tự).
- Mọi tọa độ nhân `scale_to_m`.

`tests/dxf_factory.py` (tạo đúng nội dung này):

```python
import ezdxf

ODU_W, ODU_D = 0.98, 0.47
ODU_POSITIONS = [(5.5, 0.8), (7.0, 0.8), (20.5, 0.8), (22.0, 0.8)]
BALCONIES = [((5, 0), (9, 2)), ((20, 0), (24, 2))]
FAR_X = 500.0


def make_tower_dxf(path, *, unit_code=4):
    """DXF tổng hợp: thân nhà 30x20 m, 2 ban công lõm, lan can, 4 dàn nóng, 1 lồng che, 1 cụm xa."""
    k = 1000.0 if unit_code == 4 else 1.0
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = unit_code
    for name in ("A-WALL", "A-BALC", "A-HANDRAIL", "M-EQPM", "A-ANNO"):
        doc.layers.add(name)

    def rect_block(name, w, d):
        blk = doc.blocks.new(name)
        pts = [(0, 0), (w * k, 0), (w * k, d * k), (0, d * k)]
        for a, b in zip(pts, pts[1:] + pts[:1]):
            blk.add_line(a, b)

    rect_block("ODU_TEST", ODU_W, ODU_D)
    rect_block("ENCLOSURE", 2.8, 3.2)

    msp = doc.modelspace()

    def line(a, b, layer):
        msp.add_line((a[0] * k, a[1] * k), (b[0] * k, b[1] * k), dxfattribs={"layer": layer})

    def rect(x0, y0, x1, y1, layer, dx=0.0):
        pts = [(x0 + dx, y0), (x1 + dx, y0), (x1 + dx, y1), (x0 + dx, y1)]
        for a, b in zip(pts, pts[1:] + pts[:1]):
            line(a, b, layer)

    rect(0, 0, 30, 20, "A-WALL")
    for (x0, y0), (x1, y1) in BALCONIES:
        msp.add_lwpolyline(
            [(x0 * k, y0 * k), (x1 * k, y0 * k), (x1 * k, y1 * k), (x0 * k, y1 * k)],
            close=True,
            dxfattribs={"layer": "A-BALC"},
        )
    line((5, 0), (9, 0), "A-HANDRAIL")
    line((20, 0), (24, 0), "A-HANDRAIL")
    for x, y in ODU_POSITIONS:
        msp.add_blockref("ODU_TEST", (x * k, y * k), dxfattribs={"layer": "M-EQPM"})
    msp.add_blockref("ENCLOSURE", (12 * k, 5 * k), dxfattribs={"layer": "M-EQPM"})
    rect(0, 0, 10, 10, "A-WALL", dx=FAR_X)
    line((FAR_X, 12), (FAR_X + 5, 12), "A-HANDRAIL")
    msp.add_text("A-101", dxfattribs={"insert": (1 * k, 1 * k), "layer": "A-ANNO", "height": 0.3 * k})
    doc.saveas(path)
```

`tests/conftest.py` thêm:

```python
@pytest.fixture
def tower_dxf(tmp_path):
    from dxf_factory import make_tower_dxf

    p = tmp_path / "tower.dxf"
    make_tower_dxf(p)
    return p
```

- [ ] **Step 1: Viết test (FAIL)**

```python
import math

import ezdxf
import pytest
from dxf_factory import ODU_D, ODU_W, make_tower_dxf

from odu_cfd.errors import IngestError
from odu_cfd.ingest.drawing import load_drawing


def _extent(points):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def test_units_and_metre_coordinates(tower_dxf):
    d = load_drawing(tower_dxf)
    assert (d.units, d.scale_to_m) == ("mm", 0.001)
    walls = [p for p in d.primitives if p.layer == "A-WALL"]
    xs = [x for p in walls for x, _ in p.points]
    assert min(xs) == pytest.approx(0.0) and max(xs) == pytest.approx(510.0)
    assert "A-WALL" in d.layers and "M-EQPM" in d.layers


def test_unitless_drawing_requires_override(tmp_path):
    p = tmp_path / "u.dxf"
    make_tower_dxf(p, unit_code=0)
    with pytest.raises(IngestError, match="đơn vị"):
        load_drawing(p)
    d = load_drawing(p, units_override="m")
    assert d.scale_to_m == 1.0
    assert max(x for q in d.primitives if q.layer == "A-WALL" for x, _ in q.points) == pytest.approx(510.0)


def test_bad_units_override(tower_dxf):
    with pytest.raises(IngestError, match="furlong"):
        load_drawing(tower_dxf, units_override="furlong")


def test_insert_footprint_in_metres(tower_dxf):
    d = load_drawing(tower_dxf)
    ins = [p for p in d.primitives if p.kind == "insert" and p.name == "ODU_TEST"]
    assert len(ins) == 4
    assert ins[0].layer == "M-EQPM" and len(ins[0].points) == 4
    assert _extent(ins[0].points) == pytest.approx((ODU_W, ODU_D))


def test_rotated_insert_swaps_extents(tmp_path):
    p = tmp_path / "r.dxf"
    make_tower_dxf(p)
    doc = ezdxf.readfile(p)
    doc.modelspace().add_blockref(
        "ODU_TEST", (40000, 40000), dxfattribs={"layer": "M-EQPM", "rotation": 90}
    )
    doc.saveas(p)
    d = load_drawing(p)
    rot = [q for q in d.primitives if q.kind == "insert" and q.rotation_deg == pytest.approx(90)]
    assert len(rot) == 1
    assert _extent(rot[0].points) == pytest.approx((ODU_D, ODU_W))


def test_bulge_polyline_is_flattened(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4
    doc.modelspace().add_lwpolyline([(0, 0, 1), (1000, 0, 0)], format="xyb")
    p = tmp_path / "b.dxf"
    doc.saveas(p)
    pts = load_drawing(p).primitives[0].points
    assert len(pts) > 8
    assert all(abs(math.hypot(x - 0.5, y) - 0.5) < 0.006 for x, y in pts)


def test_texts_are_collected(tower_dxf):
    d = load_drawing(tower_dxf)
    t = [t for t in d.texts if t.text == "A-101"]
    assert len(t) == 1 and (t[0].x, t[0].y) == pytest.approx((1.0, 1.0))


def test_unsupported_entities_are_counted_not_fatal(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    msp.add_line((0, 0), (1000, 0))
    h = msp.add_hatch()
    h.paths.add_polyline_path([(0, 0), (10, 0), (10, 10)], is_closed=True)
    p = tmp_path / "h.dxf"
    doc.saveas(p)
    d = load_drawing(p)
    assert len(d.primitives) == 1 and d.skipped.get("HATCH") == 1
```

- [ ] **Step 2:** chạy → FAIL. **Step 3:** viết `drawing.py`. **Step 4:** PASS, rồi toàn bộ test.

---

### Task 4: Vai trò layer và gom view

**Files:**
- Create: `src/odu_cfd/ingest/layers.py`, `src/odu_cfd/ingest/views.py`
- Test: `tests/test_ingest_layers.py`, `tests/test_ingest_views.py`

Giao diện:

```python
ROLES = ("wall_ext", "wall_int", "balcony", "rail", "column", "slab", "odu")
def classify_layers(layer_names) -> dict[str, str | None]      # giữ mọi layer đầu vào, giá trị None nếu không khớp

@dataclass(frozen=True)
class View:
    view_id: str; bbox: tuple; n_primitives: int; layer_counts: dict; labels: tuple
def find_views(drawing, gap_m: float = 20.0, layer_roles: dict | None = None) -> list[View]
```

Luật phân vai: không phân biệt hoa thường, tách tên layer thành token theo `[-_ .]` rồi áp luật **theo thứ tự**, cái đầu tiên khớp thắng: rail (`RAIL`, `HANDRAIL`, `HRAL`, `RAILING`, `BALUSTRADE`) → balcony (`BALC`, `BALCONY`) → odu (`EQPM`, `ODU`, `VRF`, `CONDENS*`, `OUTDOOR`) → column (token `COL`, `COLS`, `COLUMN`) → wall_int (có token `WALL` kèm `INT`, hoặc tên `I-WALL`, hoặc `PARTITION`) → wall pattern/hatch (`WALL` kèm `PAT`) → None → wall_ext (token `WALL`, `FACADE`, `CURT` đi cùng `WALL`) → slab (`FLOR`, `FLOOR`, `SLAB`, trừ khi có token `PATT`) → None. Bảng nghiệm thu bắt buộc (test bên dưới).

`find_views`: bbox của từng primitive (path: min/max điểm; insert: 4 góc) nới `gap_m/2` mỗi phía; lưới ô vuông cạnh `gap_m`; gộp (union-find) các primitive có bbox nới cùng chạm một ô. Mỗi cụm là một View. Sắp xếp theo (số vai trò layer khác nhau giảm dần, số primitive giảm dần), đặt `view_id` = `V1`, `V2`, ... theo thứ tự đó. `bbox` là hộp bao gốc (chưa nới) `(minx, miny, maxx, maxy)`. `layer_counts` đếm primitive theo layer. `labels` là tối đa 5 text rơi trong bbox. Nếu `layer_roles` là None thì mọi layer tính một vai trò khác nhau (chỉ để xếp hạng theo số primitive).

- [ ] **Step 1: Viết test (FAIL)**

```python
# tests/test_ingest_layers.py
import pytest

from odu_cfd.ingest.layers import ROLES, classify_layers

CASES = {
    "A-WALL": "wall_ext",
    "A-200-M_WALL_EXT": "wall_ext",
    "A-214-M_CURT_WALL": "wall_ext",
    "A-200-M_WALL_INT": "wall_int",
    "I-WALL": "wall_int",
    "A-200-M_WALL_PAT": None,
    "A-FLOR-HRAL": "rail",
    "A-HANDRAIL": "rail",
    "A-340-M_RAILING": "rail",
    "A-BALC": "balcony",
    "S-COLS": "column",
    "A-COLS": "column",
    "M-EQPM": "odu",
    "RFR-MVAC-ODU": "odu",
    "A-230-M_FLOOR": "slab",
    "A-FLOR": "slab",
    "A-FLOR-PATT": None,
    "A-215-M_CURT_PANEL": None,
    "A-242-M_STAIR": None,
    "A-010-D_DIM": None,
    "RFR-MVAC-PAD": None,
    "0": None,
}


@pytest.mark.parametrize("name,role", CASES.items())
def test_known_layers(name, role):
    assert classify_layers([name])[name] == role


def test_case_insensitive_and_keeps_all_layers():
    out = classify_layers(["a-wall", "Zzz"])
    assert out == {"a-wall": "wall_ext", "Zzz": None}


def test_roles_are_declared():
    assert set(CASES.values()) - {None} <= set(ROLES)
```

```python
# tests/test_ingest_views.py
import pytest

from odu_cfd.ingest.drawing import load_drawing
from odu_cfd.ingest.layers import classify_layers
from odu_cfd.ingest.views import find_views


def test_far_clusters_become_separate_views_best_first(tower_dxf):
    d = load_drawing(tower_dxf)
    views = find_views(d, layer_roles=classify_layers(d.layers))
    assert [v.view_id for v in views] == ["V1", "V2"]
    v1, v2 = views
    assert v1.bbox[0] == pytest.approx(0.0, abs=0.01) and v1.bbox[2] < 40
    assert v2.bbox[0] > 400
    assert v1.n_primitives > v2.n_primitives
    assert v1.layer_counts["A-BALC"] == 2
    assert "A-101" in v1.labels


def test_large_gap_merges_everything(tower_dxf):
    d = load_drawing(tower_dxf)
    assert len(find_views(d, gap_m=1000.0)) == 1


def test_primitives_inside_gap_stay_together(tower_dxf):
    d = load_drawing(tower_dxf)
    assert find_views(d)[0].n_primitives == 13   # 4 tường + 2 ban công + 2 lan can + 4 ODU + 1 lồng che
```

- [ ] **Step 2:** chạy → FAIL. **Step 3:** viết hai module. **Step 4:** PASS, rồi toàn bộ test.

---

### Task 5: Nhận diện dàn nóng (`ingest/odu_detect.py`)

**Files:**
- Create: `src/odu_cfd/ingest/odu_detect.py`
- Test: `tests/test_ingest_odu_detect.py`

Giao diện:

```python
NAME_PATTERN = r"(?i)(?<![a-z])(odu|vrf|condens\w*|outdoor|dàn nóng|dan nong)(?![a-z])"

@dataclass(frozen=True)
class OduInstance:
    odu_id: str; block: str; layer: str
    center: tuple          # (x, y) mét
    size: tuple            # (w, d) mét: hai cạnh đầu của chân đế, trước khi xoay
    rotation_deg: float

def detect_odus(drawing, view_bbox, layer_roles, area_range_m2=(0.2, 3.0)) -> tuple[list[OduInstance], list[OduInstance]]
```

Trả `(odus, excluded)`. Ứng viên: primitive `insert` có tâm chân đế nằm trong `view_bbox` và (vai trò layer là `odu` hoặc tên block khớp `NAME_PATTERN`). Diện tích chân đế = w·d; ngoài `area_range_m2` thì vào `excluded` (id `X-01`, ...). Gộp trùng: hai ứng viên có tâm cách nhau < 0.05 m và kích thước chênh < 0.01 m chỉ giữ một. Sắp xếp `odus` theo `(round(y, 3), round(x, 3))`, đặt id `ODU-01`, `ODU-02`, ... `size` = độ dài hai cạnh đầu của `points`, `center` = trung bình 4 góc.

- [ ] **Step 1: Viết test (FAIL)**

```python
import ezdxf
import pytest
from dxf_factory import ODU_D, ODU_W, make_tower_dxf

from odu_cfd.ingest.drawing import load_drawing
from odu_cfd.ingest.layers import classify_layers
from odu_cfd.ingest.odu_detect import detect_odus

VIEW = (-1.0, -1.0, 40.0, 30.0)


def _detect(path, view=VIEW, **kw):
    d = load_drawing(path)
    return detect_odus(d, view, classify_layers(d.layers), **kw)


def test_finds_four_units_and_excludes_enclosure(tower_dxf):
    odus, excluded = _detect(tower_dxf)
    assert [o.odu_id for o in odus] == ["ODU-01", "ODU-02", "ODU-03", "ODU-04"]
    assert odus[0].center == pytest.approx((5.99, 1.035))
    assert odus[3].center == pytest.approx((22.49, 1.035))
    assert odus[0].size == pytest.approx((ODU_W, ODU_D))
    assert [e.block for e in excluded] == ["ENCLOSURE"]
    assert excluded[0].odu_id == "X-01"


def test_units_outside_view_are_ignored(tower_dxf):
    odus, _ = _detect(tower_dxf, view=(-1.0, -1.0, 10.0, 30.0))
    assert [o.odu_id for o in odus] == ["ODU-01", "ODU-02"]


def _add(path, mutate):
    doc = ezdxf.readfile(path)
    mutate(doc, doc.modelspace())
    doc.saveas(path)


def test_duplicate_blocks_are_merged(tower_dxf):
    _add(tower_dxf, lambda doc, msp: msp.add_blockref(
        "ODU_TEST", (5500, 800), dxfattribs={"layer": "M-EQPM"}))
    odus, _ = _detect(tower_dxf)
    assert len(odus) == 4


def test_block_name_alone_is_enough(tower_dxf):
    def mutate(doc, msp):
        blk = doc.blocks.new("VRF mini")
        for a, b in [((0, 0), (980, 0)), ((980, 0), (980, 470)), ((980, 470), (0, 470)), ((0, 470), (0, 0))]:
            blk.add_line(a, b)
        msp.add_blockref("VRF mini", (10000, 10000), dxfattribs={"layer": "A-ANNO"})

    _add(tower_dxf, mutate)
    odus, _ = _detect(tower_dxf)
    assert len(odus) == 5
    assert any(o.block == "VRF mini" for o in odus)


def test_rotation_is_kept_and_size_is_unrotated(tower_dxf):
    _add(tower_dxf, lambda doc, msp: msp.add_blockref(
        "ODU_TEST", (30000, 15000), dxfattribs={"layer": "M-EQPM", "rotation": 90}))
    odus, _ = _detect(tower_dxf, view=(-1.0, -1.0, 40.0, 30.0))
    rot = [o for o in odus if o.rotation_deg == pytest.approx(90)]
    assert len(rot) == 1 and rot[0].size == pytest.approx((ODU_W, ODU_D))


def test_area_range_is_configurable(tower_dxf):
    odus, excluded = _detect(tower_dxf, area_range_m2=(0.2, 20.0))
    assert len(odus) == 5 and excluded == []
```

- [ ] **Step 2:** chạy → FAIL. **Step 3:** viết `odu_detect.py`. **Step 4:** PASS, rồi toàn bộ test.

---

### Task 6: `ingest.yaml`, ảnh phủ, pipeline `ingest` và lệnh CLI

**Files:**
- Create: `src/odu_cfd/ingest/config.py`, `src/odu_cfd/ingest/overlay.py`, `src/odu_cfd/ingest/pipeline.py`
- Modify: `src/odu_cfd/cli.py`
- Test: `tests/test_ingest_config.py`, `tests/test_ingest_pipeline.py`

Giao diện:

```python
# config.py
STATUSES = ("proposed", "confirmed")

@dataclass
class IngestConfig:
    status: str
    source_file: str                    # đường dẫn tương đối so với thư mục dự án
    original_file: str | None           # DWG gốc đã chép vào input/, hoặc None
    units: str                          # khóa UNIT_SCALE
    view_id: str
    view_bbox: tuple                    # (minx, miny, maxx, maxy) mét
    layers: dict                        # layer -> vai trò (chỉ layer có vai trò)
    odu_area_range_m2: tuple
    odus: list                          # list[OduInstance]

def write_ingest_config(path, cfg) -> None
def read_ingest_config(path) -> IngestConfig     # kiểm tra, lỗi IngestError nêu đường dẫn trường

# overlay.py
def render_overlay(drawing, cfg, png_path) -> None   # matplotlib Agg; đường theo màu vai trò, ODU hộp đỏ có nhãn id, khung view

# pipeline.py
def run_ingest(project_dir, source, view_id=None, units=None, exe=None) -> IngestConfig
def confirm_ingest(project_dir) -> IngestConfig
```

`run_ingest`: chép `source` vào `<dự án>/input/` (giữ tên); nếu đuôi `.dwg` thì `convert_dwg_to_dxf` ra `input/<tên>.dxf` (tham số `exe` cho test) và `original_file` là DWG; đuôi `.dxf` dùng thẳng; đuôi khác → `IngestError`. Đọc bản vẽ (`units` truyền vào `units_override`), phân vai layer (chỉ giữ layer có vai trò), tìm view, chọn `view_id` (mặc định `V1`, không tồn tại thì `IngestError` liệt kê các view có sẵn kèm bbox), tìm dàn nóng, ghi `input/ingest.yaml` với `status: proposed` và `input/overlay.png`. `confirm_ingest`: đọc file, kiểm tra có ít nhất một layer vai trò `wall_ext` hoặc `slab` và ít nhất một dàn nóng (lỗi tiếng Việt nêu thiếu gì và nhắc sửa `ingest.yaml`), đặt `status: confirmed`, ghi lại, trả cấu hình. Dùng lại thư mục `input/` đã tạo bởi `odu-cfd init`; thiếu thì `IngestError` bảo chạy `init`.

CLI: `odu-cfd ingest <dự án> [nguồn] [--view V2] [--units mm] [--confirm]`. Có `--confirm` thì bỏ qua nguồn và gọi `confirm_ingest`; không có `--confirm` mà thiếu nguồn thì lỗi. In tóm tắt tiếng Việt: view đã chọn, số layer có vai trò, số dàn nóng, số bị loại, đường dẫn `overlay.png` và `ingest.yaml`, nhắc "xem ảnh, sửa file nếu cần, rồi chạy `odu-cfd ingest <dự án> --confirm`". Cảnh báo (in, không dừng) khi `drawing.skipped` khác rỗng.

- [ ] **Step 1: Viết test (FAIL)**

```python
# tests/test_ingest_config.py
import pytest

from odu_cfd.errors import IngestError
from odu_cfd.ingest.config import IngestConfig, read_ingest_config, write_ingest_config
from odu_cfd.ingest.odu_detect import OduInstance


def _cfg():
    return IngestConfig(
        status="proposed",
        source_file="input/tower.dxf",
        original_file="input/tower.dwg",
        units="mm",
        view_id="V1",
        view_bbox=(0.0, 0.0, 30.0, 20.0),
        layers={"A-WALL": "wall_ext", "A-BALC": "balcony"},
        odu_area_range_m2=(0.2, 3.0),
        odus=[OduInstance("ODU-01", "ODU_TEST", "M-EQPM", (5.99, 1.035), (0.98, 0.47), 0.0)],
    )


def test_roundtrip(tmp_path):
    p = tmp_path / "ingest.yaml"
    write_ingest_config(p, _cfg())
    assert read_ingest_config(p) == _cfg()


def test_vietnamese_text_survives(tmp_path):
    cfg = _cfg()
    cfg.layers = {"A-TƯỜNG": "wall_ext"}
    p = tmp_path / "ingest.yaml"
    write_ingest_config(p, cfg)
    assert read_ingest_config(p).layers == {"A-TƯỜNG": "wall_ext"}


@pytest.mark.parametrize(
    "old,new,field",
    [
        ("status: proposed", "status: maybe", "status"),
        ("A-BALC: balcony", "A-BALC: roof", "layers"),
        ("units: mm", "units: furlong", "units"),
    ],
)
def test_invalid_values_name_the_field(tmp_path, old, new, field):
    p = tmp_path / "ingest.yaml"
    write_ingest_config(p, _cfg())
    p.write_text(p.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    with pytest.raises(IngestError, match=field):
        read_ingest_config(p)


def test_bad_bbox_is_rejected(tmp_path):
    p = tmp_path / "ingest.yaml"
    write_ingest_config(p, _cfg())
    text = p.read_text(encoding="utf-8")
    p.write_text(text.replace("30.0", "-5.0"), encoding="utf-8")
    with pytest.raises(IngestError, match="view_bbox"):
        read_ingest_config(p)


def test_missing_file_is_ingest_error(tmp_path):
    with pytest.raises(IngestError, match="ingest.yaml"):
        read_ingest_config(tmp_path / "ingest.yaml")
```

```python
# tests/test_ingest_pipeline.py
import shutil

import pytest

from odu_cfd.cli import main
from odu_cfd.errors import IngestError
from odu_cfd.ingest.config import read_ingest_config
from odu_cfd.ingest.pipeline import confirm_ingest, run_ingest


@pytest.fixture
def project(tmp_path):
    p = tmp_path / "du-an"
    assert main(["init", str(p)]) == 0
    return p


def test_run_ingest_proposes(project, tower_dxf):
    cfg = run_ingest(project, tower_dxf)
    assert cfg.status == "proposed" and cfg.view_id == "V1" and cfg.units == "mm"
    assert cfg.layers["A-WALL"] == "wall_ext" and cfg.layers["M-EQPM"] == "odu"
    assert "A-ANNO" not in cfg.layers
    assert len(cfg.odus) == 4
    assert (project / "input" / "tower.dxf").is_file()
    assert (project / "input" / "overlay.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert read_ingest_config(project / "input" / "ingest.yaml") == cfg


def test_second_view_can_be_chosen_and_unknown_view_lists_options(project, tower_dxf):
    assert run_ingest(project, tower_dxf, view_id="V2").view_bbox[0] > 400
    with pytest.raises(IngestError, match="V1"):
        run_ingest(project, tower_dxf, view_id="V9")


def test_unknown_extension(project, tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF")
    with pytest.raises(IngestError, match=r"\.dwg|\.dxf"):
        run_ingest(project, f)


def test_dwg_goes_through_converter(project, tower_dxf, tmp_path, monkeypatch):
    dwg_file = tmp_path / "tower.dwg"
    dwg_file.write_bytes(b"AC1032" + b"\0" * 64)

    def fake_convert(dwg, out, exe=None):
        shutil.copy(tower_dxf, out)
        return out

    monkeypatch.setattr("odu_cfd.ingest.pipeline.convert_dwg_to_dxf", fake_convert)
    cfg = run_ingest(project, dwg_file)
    assert cfg.original_file == "input/tower.dwg" and cfg.source_file == "input/tower.dxf"


def test_confirm_requires_envelope_and_units(project, tower_dxf):
    run_ingest(project, tower_dxf)
    assert confirm_ingest(project).status == "confirmed"


def test_confirm_without_odus_fails(project, tower_dxf):
    run_ingest(project, tower_dxf)
    ingest_yaml = project / "input" / "ingest.yaml"
    cfg = read_ingest_config(ingest_yaml)
    cfg.odus = []
    from odu_cfd.ingest.config import write_ingest_config

    write_ingest_config(ingest_yaml, cfg)
    with pytest.raises(IngestError, match="dàn nóng"):
        confirm_ingest(project)


def test_cli_flow(project, tower_dxf, capsys):
    assert main(["ingest", str(project), str(tower_dxf)]) == 0
    out = capsys.readouterr().out
    assert "overlay.png" in out and "--confirm" in out
    assert main(["ingest", str(project), "--confirm"]) == 0
    assert read_ingest_config(project / "input" / "ingest.yaml").status == "confirmed"


def test_cli_needs_source_or_confirm(project, capsys):
    assert main(["ingest", str(project)]) == 2
    assert "Lỗi" in capsys.readouterr().err
```

- [ ] **Step 2:** chạy → FAIL. **Step 3:** viết `config.py` (YAML bằng PyYAML, `allow_unicode=True`, `sort_keys=False`, bbox/size dạng danh sách số), `overlay.py`, `pipeline.py`, sửa `cli.py`. **Step 4:** PASS, rồi toàn bộ test.

---

### Task 7: Lưới tam giác kín (`geometry/mesh.py`)

**Files:**
- Create: `src/odu_cfd/geometry/__init__.py` (rỗng), `src/odu_cfd/geometry/mesh.py`
- Test: `tests/test_geometry_mesh.py`

Giao diện:

```python
@dataclass(frozen=True)
class Mesh:
    vertices: np.ndarray    # (n, 3) float64
    faces: np.ndarray       # (m, 3) int64, ngược chiều kim đồng hồ nhìn từ ngoài

def merge(meshes) -> Mesh
def volume(mesh) -> float                       # có dấu, dương khi pháp tuyến hướng ra ngoài
def is_closed(mesh, tol=1e-6) -> bool           # mọi cạnh có hướng (a,b) đều có đúng một cạnh (b,a), không trùng lặp
def bounds(mesh) -> tuple                        # (minx, miny, minz, maxx, maxy, maxz)
def extrude_polygon(poly, z0, z1) -> Mesh       # Polygon hoặc MultiPolygon, có lỗ; z1 > z0 nếu không ValueError
def box(cx, cy, w, d, rotation_deg, z0, z1) -> Mesh   # w dọc trục x cục bộ, d dọc trục y cục bộ, xoay quanh (cx, cy)
```

Cách làm `extrude_polygon` (đã kiểm chứng về hướng pháp tuyến): `poly = shapely.geometry.polygon.orient(poly, 1.0)` (ngoài ngược chiều kim đồng hồ, lỗ thuận chiều); mặt trên = các tam giác của `shapely.constrained_delaunay_triangles(poly)` ở `z1` (sắp lại cho ngược chiều kim đồng hồ), mặt dưới = cùng tam giác đảo thứ tự ở `z0`; với mỗi cạnh `p→q` của mọi vòng (ngoài và lỗ), thêm hai tam giác `(p0,q0,q1)` và `(p0,q1,p1)` (số 0 ở `z0`, số 1 ở `z1`). Hàn đỉnh bằng khóa `(round(x,9), round(y,9), round(z,9))`.

- [ ] **Step 1: Viết test (FAIL)**

```python
import numpy as np
import pytest
from shapely.geometry import Polygon

from odu_cfd.geometry.mesh import box, bounds, extrude_polygon, is_closed, merge, volume


def test_square_prism():
    m = extrude_polygon(Polygon([(0, 0), (3, 0), (3, 2), (0, 2)]), 1.0, 3.0)
    assert is_closed(m)
    assert volume(m) == pytest.approx(12.0)
    assert bounds(m) == pytest.approx((0, 0, 1, 3, 2, 3))


def test_polygon_with_hole():
    outer = [(0, 0), (10, 0), (10, 10), (0, 10)]
    hole = [(4, 4), (4, 6), (6, 6), (6, 4)]
    m = extrude_polygon(Polygon(outer, [hole]), 0.0, 2.0)
    assert is_closed(m)
    assert volume(m) == pytest.approx((100 - 4) * 2.0)


def test_concave_l_shape():
    m = extrude_polygon(Polygon([(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (0, 3)]), 0.0, 1.0)
    assert is_closed(m) and volume(m) == pytest.approx(6.0)


def test_clockwise_input_is_reoriented():
    m = extrude_polygon(Polygon([(0, 0), (0, 2), (2, 2), (2, 0)]), 0.0, 1.0)
    assert volume(m) == pytest.approx(4.0)


def test_multipolygon():
    from shapely.geometry import MultiPolygon

    mp = MultiPolygon([Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), Polygon([(5, 5), (7, 5), (7, 6), (5, 6)])])
    m = extrude_polygon(mp, 0.0, 1.0)
    assert is_closed(m) and volume(m) == pytest.approx(3.0)


def test_bad_height():
    with pytest.raises(ValueError):
        extrude_polygon(Polygon([(0, 0), (1, 0), (1, 1)]), 2.0, 2.0)


def test_box_rotation():
    m = box(10.0, 5.0, 0.98, 0.47, 90.0, 0.0, 1.0)
    lo, hi = bounds(m)[:3], bounds(m)[3:]
    assert (hi[0] - lo[0], hi[1] - lo[1]) == pytest.approx((0.47, 0.98))
    assert ((hi[0] + lo[0]) / 2, (hi[1] + lo[1]) / 2) == pytest.approx((10.0, 5.0))
    assert volume(m) == pytest.approx(0.98 * 0.47)


def test_open_mesh_is_detected():
    m = box(0, 0, 1, 1, 0, 0, 1)
    open_mesh = type(m)(m.vertices, m.faces[:-1])
    assert not is_closed(open_mesh)


def test_merge_keeps_both():
    a, b = box(0, 0, 1, 1, 0, 0, 1), box(5, 5, 1, 1, 0, 0, 2)
    m = merge([a, b])
    assert is_closed(m) and volume(m) == pytest.approx(3.0)
    assert m.faces.max() < len(m.vertices)
```

- [ ] **Step 2:** chạy → FAIL. **Step 3:** viết `mesh.py`. **Step 4:** PASS, rồi toàn bộ test.

---

### Task 8: Đa giác 2D và mô hình tòa nhà (`geometry/plan2d.py`, `geometry/build.py`)

**Files:**
- Create: `src/odu_cfd/geometry/plan2d.py`, `src/odu_cfd/geometry/build.py`
- Test: `tests/test_geometry_plan2d.py`, `tests/test_geometry_build.py`

Giao diện:

```python
# plan2d.py
@dataclass(frozen=True)
class Plan2D:
    envelope: object        # shapely Polygon/MultiPolygon, đã lấp lỗ
    balconies: tuple        # tuple[Polygon]
    rails: tuple            # tuple[LineString]
    columns: tuple          # tuple[Polygon]

def extract_plan(drawing, cfg) -> Plan2D          # cfg: IngestConfig (dùng view_bbox, layers)

# build.py
@dataclass(frozen=True)
class BuildingModel:
    groups: dict            # {"building": {tên: Mesh}, "balcony": {...}, "rail": {...}, "odu": {...}}
    warnings: tuple
    def summary(self) -> dict

def build_building(plan, building_cfg, geometry_cfg, odus, odu_height_m=None) -> BuildingModel
```

`extract_plan`: lấy primitive có tâm trong `view_bbox` (đúng một lần, theo hộp bao của primitive) rồi nhóm theo vai trò layer. Đường bao: các primitive `path` của vai trò `wall_ext` (và `slab` nếu có) → `unary_union` các LineString (path kín thì thêm cả Polygon), `shapely.ops.polygonize`, bỏ mảnh diện tích < 0.5 m², hợp lại, giữ phần ngoài của từng thành phần (lấp lỗ). Rỗng thì `IngestError` nêu các layer đã dùng và gợi ý sửa `ingest.yaml`. Ban công: path kín vai trò `balcony` thành Polygon (đã `buffer(0)` nếu không hợp lệ). Lan can: path vai trò `rail` thành LineString (path kín thì lấy ranh giới). Cột: path kín vai trò `column`. Chân đế cột/lan can giao với đường bao không xử lý ở đây.

`build_building`: `H = num_floors * floor_height_m`; `slab = geometry_cfg.slab_thickness_m`. Khối nhà = `(envelope − hợp ban công)` đùn `[0, H]`, nhóm `building`, tên `building`. Với mỗi tầng `i` (`z0 = i*floor_height_m`): tấm sàn ban công (đa giác ban công) đùn `[z0, z0+slab]` (gộp mọi tấm vào một vùng `balcony_slabs`); lan can = `LineString.buffer(rail_thickness/2, cap_style="flat")` đùn `[z0+slab, z0+slab+rail_height]` (gộp vào vùng `rails`); dàn nóng `box(center, size, rotation, z0+slab, z0+slab+h)` với `h = odu_height_m or geometry_cfg.odu_default_height_m`, vùng tên `<odu_id>_f<tầng 2 chữ số>`. Cảnh báo (chuỗi tiếng Việt, đưa vào `warnings`): dàn nóng có tâm không nằm trong đa giác ban công nào (`"ODU-xx nằm ngoài ban công"`), vùng không kín (`is_closed` sai), đường bao diện tích < 1 m². `summary()` trả: `{"num_floors", "height_m", "bbox": [6 số], "envelope_area_m2", "parts": {nhóm: {"regions": n, "volume_m3": v, "closed": bool}}, "warnings": [...]}`.

- [ ] **Step 1: Viết test (FAIL)**

```python
# tests/test_geometry_plan2d.py
import pytest

from odu_cfd.errors import IngestError
from odu_cfd.geometry.plan2d import extract_plan
from odu_cfd.ingest.config import IngestConfig
from odu_cfd.ingest.drawing import load_drawing
from odu_cfd.ingest.layers import classify_layers


def _cfg(drawing, view=(-1.0, -1.0, 40.0, 30.0), drop=()):
    roles = {k: v for k, v in classify_layers(drawing.layers).items() if v and k not in drop}
    return IngestConfig("confirmed", "x.dxf", None, "mm", "V1", view, roles, (0.2, 3.0), [])


def test_envelope_balconies_rails(tower_dxf):
    d = load_drawing(tower_dxf)
    plan = extract_plan(d, _cfg(d))
    assert plan.envelope.area == pytest.approx(600.0)
    assert sorted(round(b.area, 3) for b in plan.balconies) == [8.0, 8.0]
    assert sorted(round(r.length, 3) for r in plan.rails) == [4.0, 4.0]
    assert plan.columns == ()


def test_far_cluster_is_outside_the_view(tower_dxf):
    d = load_drawing(tower_dxf)
    plan = extract_plan(d, _cfg(d))
    assert plan.envelope.bounds[2] < 40


def test_second_view_gives_its_own_envelope(tower_dxf):
    d = load_drawing(tower_dxf)
    plan = extract_plan(d, _cfg(d, view=(499.0, -1.0, 511.0, 13.0)))
    assert plan.envelope.area == pytest.approx(100.0)
    assert len(plan.balconies) == 0


def test_no_envelope_layer_is_an_error(tower_dxf):
    d = load_drawing(tower_dxf)
    with pytest.raises(IngestError, match="đường bao"):
        extract_plan(d, _cfg(d, drop=("A-WALL",)))
```

```python
# tests/test_geometry_build.py
import pytest
from shapely.geometry import LineString, Polygon

from odu_cfd.geometry.build import build_building
from odu_cfd.geometry.mesh import bounds
from odu_cfd.geometry.plan2d import Plan2D
from odu_cfd.ingest.odu_detect import OduInstance
from odu_cfd.schema import BuildingConfig, GeometryConfig


def _plan():
    return Plan2D(
        envelope=Polygon([(0, 0), (30, 0), (30, 20), (0, 20)]),
        balconies=(
            Polygon([(5, 0), (9, 0), (9, 2), (5, 2)]),
            Polygon([(20, 0), (24, 0), (24, 2), (20, 2)]),
        ),
        rails=(LineString([(5, 0), (9, 0)]), LineString([(20, 0), (24, 0)])),
        columns=(),
    )


def _odu(i, x, y):
    return OduInstance(f"ODU-{i:02d}", "B", "M-EQPM", (x, y), (0.98, 0.47), 0.0)


ODUS = [_odu(1, 5.99, 1.0), _odu(2, 7.49, 1.0), _odu(3, 20.99, 1.0)]


def _build(odus=ODUS, floors=3):
    return build_building(_plan(), BuildingConfig(floors, 3.3), GeometryConfig(), odus)


def test_building_volume_and_bounds():
    m = _build()
    (name, mesh), = m.groups["building"].items()
    from odu_cfd.geometry.mesh import volume

    assert volume(mesh) == pytest.approx((600 - 16) * 9.9)
    assert bounds(mesh)[2] == pytest.approx(0.0) and bounds(mesh)[5] == pytest.approx(9.9)


def test_slabs_and_rails_per_floor():
    from odu_cfd.geometry.mesh import volume

    m = _build()
    assert volume(m.groups["balcony"]["balcony_slabs"]) == pytest.approx(16 * 0.15 * 3)
    assert volume(m.groups["rail"]["rails"]) == pytest.approx(2 * 4 * 0.05 * 1.1 * 3)


def test_odu_regions_per_floor_and_height():
    m = _build()
    names = sorted(m.groups["odu"])
    assert len(names) == 9 and names[0] == "ODU-01_f00" and names[-1] == "ODU-03_f02"
    b = bounds(m.groups["odu"]["ODU-01_f00"])
    assert (b[2], b[5]) == pytest.approx((0.15, 1.15))
    b2 = bounds(m.groups["odu"]["ODU-01_f02"])
    assert (b2[2], b2[5]) == pytest.approx((0.15 + 6.6, 1.15 + 6.6))


def test_odu_height_override():
    m = build_building(_plan(), BuildingConfig(1, 3.3), GeometryConfig(), ODUS, odu_height_m=0.8)
    b = bounds(m.groups["odu"]["ODU-01_f00"])
    assert b[5] - b[2] == pytest.approx(0.8)


def test_summary_and_all_closed():
    s = _build().summary()
    assert s["num_floors"] == 3 and s["height_m"] == pytest.approx(9.9)
    assert s["envelope_area_m2"] == pytest.approx(600.0)
    assert all(p["closed"] for p in s["parts"].values())
    assert s["parts"]["odu"]["regions"] == 9
    assert s["warnings"] == []


def test_odu_outside_balcony_is_warned():
    s = _build(odus=[_odu(1, 15.0, 10.0)]).summary()
    assert any("ODU-01" in w and "ngoài ban công" in w for w in s["warnings"])
```

- [ ] **Step 2:** chạy → FAIL. **Step 3:** viết hai module. **Step 4:** PASS, rồi toàn bộ test.

---

### Task 9: Xuất STL và GLB (`geometry/export.py`)

**Files:**
- Create: `src/odu_cfd/geometry/export.py`
- Test: `tests/test_geometry_export.py`

Giao diện:

```python
def write_stl(path, regions: dict[str, Mesh]) -> None
def write_glb(path, groups: dict[str, dict[str, Mesh]]) -> None
```

`write_stl`: STL ASCII nhiều vùng, mỗi vùng một khối `solid <tên>` … `endsolid <tên>` (snappyHexMesh đọc vùng theo tên), pháp tuyến tính từ tam giác, số in bằng `repr`-đủ chính xác (`%.9g`). Tên vùng chỉ gồm `[A-Za-z0-9_.-]`, ký tự khác thay bằng `_`.

`write_glb`: glTF 2.0 nhị phân (header `glTF`, version 2, chunk JSON 0x4E4F534A đệm khoảng trắng tới bội của 4, chunk BIN 0x004E4942 đệm 0). Một `mesh` cho mỗi vùng (một primitive, không chỉ số: tam giác tách đỉnh để đổ bóng phẳng, có `POSITION` và `NORMAL` float32, `accessor.min/max` cho POSITION), một `node` cho mỗi vùng đặt `name` = tên vùng, và `extras.group` = tên nhóm; mỗi nhóm một `material` (tên nhóm; màu: building xám 0.72, balcony be, rail xanh lơ, odu đỏ cam; nhóm khác xám). Chuyển hệ trục sang y hướng lên: `(x, y, z) → (x, z, −y)` (đổi cả pháp tuyến, giữ thứ tự đỉnh ngược chiều kim đồng hồ nhìn từ ngoài, vì phép quay giữ chiều). Phần mở rộng nhóm đặt trong `extras` của node, không dùng extension.

- [ ] **Step 1: Viết test (FAIL)**

```python
import json
import re
import struct

import numpy as np
import pytest

from odu_cfd.geometry.export import write_glb, write_stl
from odu_cfd.geometry.mesh import box, volume


def _read_stl(path):
    text = path.read_text(encoding="ascii")
    regions = {}
    for name, body in re.findall(r"solid (\S+)\n(.*?)endsolid \1", text, re.S):
        v = np.array(
            [[float(t) for t in m] for m in re.findall(r"vertex (\S+) (\S+) (\S+)", body)]
        ).reshape(-1, 3, 3)
        regions[name] = v
    return regions


def _signed_volume(tris):
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def test_stl_regions_roundtrip(tmp_path):
    a, b = box(0, 0, 1, 2, 0, 0, 3), box(5, 5, 1, 1, 45, 0, 1)
    write_stl(tmp_path / "x.stl", {"ODU-01_f00": a, "b region": b})
    r = _read_stl(tmp_path / "x.stl")
    assert set(r) == {"ODU-01_f00", "b_region"}
    assert _signed_volume(r["ODU-01_f00"]) == pytest.approx(volume(a))
    assert _signed_volume(r["b_region"]) == pytest.approx(volume(b))
    assert len(r["ODU-01_f00"]) == len(a.faces)


def _read_glb(path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    assert (magic, version, length) == (b"glTF", 2, len(data))
    jlen, jtype = struct.unpack_from("<II", data, 12)
    assert jtype == 0x4E4F534A and jlen % 4 == 0
    gltf = json.loads(data[20 : 20 + jlen])
    boff = 20 + jlen
    blen, btype = struct.unpack_from("<II", data, boff)
    assert btype == 0x004E4942 and blen % 4 == 0 and boff + 8 + blen == len(data)
    return gltf, data[boff + 8 :]


def test_glb_structure(tmp_path):
    a = box(0, 0, 1, 1, 0, 0, 2)
    write_glb(tmp_path / "s.glb", {"building": {"building": a}, "odu": {"ODU-01_f00": a, "ODU-02_f00": a}})
    gltf, binary = _read_glb(tmp_path / "s.glb")
    assert gltf["asset"]["version"] == "2.0"
    assert sorted(n["name"] for n in gltf["nodes"]) == ["ODU-01_f00", "ODU-02_f00", "building"]
    assert {n["extras"]["group"] for n in gltf["nodes"]} == {"building", "odu"}
    assert len(gltf["meshes"]) == 3 and len(gltf["materials"]) == 2
    acc = gltf["accessors"][gltf["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    assert acc["count"] == len(a.faces) * 3 and acc["type"] == "VEC3"
    view = gltf["bufferViews"][acc["bufferView"]]
    pos = np.frombuffer(binary, "<f4", count=acc["count"] * 3, offset=view.get("byteOffset", 0)).reshape(-1, 3)
    # y-up: z của mô hình (0..2) thành y của glTF
    assert pos[:, 1].min() == pytest.approx(0.0) and pos[:, 1].max() == pytest.approx(2.0)
    assert acc["min"][1] == pytest.approx(0.0) and acc["max"][1] == pytest.approx(2.0)


def test_glb_normals_are_unit(tmp_path):
    write_glb(tmp_path / "s.glb", {"building": {"building": box(0, 0, 1, 1, 0, 0, 2)}})
    gltf, binary = _read_glb(tmp_path / "s.glb")
    nacc = gltf["accessors"][gltf["meshes"][0]["primitives"][0]["attributes"]["NORMAL"]]
    view = gltf["bufferViews"][nacc["bufferView"]]
    n = np.frombuffer(binary, "<f4", count=nacc["count"] * 3, offset=view.get("byteOffset", 0)).reshape(-1, 3)
    assert np.allclose(np.linalg.norm(n, axis=1), 1.0, atol=1e-5)
```

- [ ] **Step 2:** chạy → FAIL. **Step 3:** viết `export.py`. **Step 4:** PASS, rồi toàn bộ test.

---

### Task 10: Viewer 3D offline (`viewer/`)

**Files:**
- Create: `src/odu_cfd/viewer/__init__.py` (rỗng), `src/odu_cfd/viewer/geometry_viewer.py`, `src/odu_cfd/viewer/template.html`, `src/odu_cfd/viewer/vendor/*`
- Modify: `pyproject.toml` (package-data thêm `viewer/*.html`)
- Test: `tests/test_viewer.py`

- [ ] **Step 1: Tải three.js một lần (cần internet, chỉ lúc phát triển)** vào `src/odu_cfd/viewer/vendor/`:

```bash
cd D:/CFD_Tool/src/odu_cfd/viewer/vendor
B=https://cdn.jsdelivr.net/npm/three@0.147.0
curl -fsSL $B/build/three.min.js -o three.min.js
curl -fsSL $B/examples/js/loaders/GLTFLoader.js -o GLTFLoader.js
curl -fsSL $B/examples/js/controls/OrbitControls.js -o OrbitControls.js
curl -fsSL https://raw.githubusercontent.com/mrdoob/three.js/r147/LICENSE -o LICENSE-three.txt
sha256sum three.min.js GLTFLoader.js OrbitControls.js LICENSE-three.txt > SHA256SUMS
```

Kiểm tra: ba file `.js` không rỗng, `three.min.js` chứa chuỗi `REVISION="147"` (hoặc `REVISION = '147'` tùy bản dựng), không chứa `</script`. Nếu tải lỗi hoặc khác phiên bản thì dừng và báo BLOCKED, không thay phiên bản khác.

- [ ] **Step 2: Viết test (FAIL)**

```python
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
```

- [ ] **Step 3: Code.** `template.html` là một trang UTF-8 gồm: `<title>__TITLE__</title>`; khối `<style>` tối giản (canvas toàn màn hình, bảng điều khiển góc trái trên liệt kê nhóm bằng checkbox trong `<div id="groups">`, nền sáng); ba thẻ `<script>` nội tuyến chứa `__THREE__`, `__GLTF_LOADER__`, `__ORBIT__`; một thẻ `<script>` cuối chứa `const GLB_B64 = "__GLB_B64__";` rồi mã: giải base64 thành `ArrayBuffer`, `new THREE.GLTFLoader().parse(buf, "", gltf => ...)`, thêm `AmbientLight` + `DirectionalLight`, lưới sàn (`GridHelper`) và `AxesHelper`, `OrbitControls`; duyệt `gltf.scene` theo `node.userData.group` (glTF `extras` được loader chép vào `userData`) để gom nhóm; mỗi nhóm một checkbox bật/tắt `visible`; nhóm `odu` tô `MeshStandardMaterial` đỏ cam, các nhóm khác dùng vật liệu của glb; tự đặt camera theo hộp bao (`Box3`) và xoay lên y; vòng `requestAnimationFrame`. `geometry_viewer.write_viewer_html(glb_path, out_html, title)` đọc template và các file vendor bằng `Path(__file__).parent`, thay các chỗ giữ chỗ (escape `html.escape` cho title), kiểm tra không file vendor nào chứa `</script`, ghi UTF-8.
- [ ] **Step 4:** PASS, rồi toàn bộ test. **Step 5 (mắt người):** viết một glb mẫu bằng đoạn Python ngắn rồi mở `viewer.html` trong trình duyệt (nếu có thể chụp ảnh thì xem), báo cáo xem có hiển thị khối nhà và bật/tắt nhóm được không. Nếu không mở được trình duyệt, nói rõ là chưa xem bằng mắt.

---

### Task 11: Pipeline `geometry`, lệnh `geometry` và `view`, kiểm thử đầu-cuối

**Files:**
- Create: `src/odu_cfd/geometry/pipeline.py`
- Modify: `src/odu_cfd/cli.py`
- Test: `tests/test_geometry_pipeline.py`

Giao diện: `run_geometry(project_dir, library_dir=None) -> dict` (trả `summary`). Quy trình: đọc `project.yaml` (`load_project`), đọc `input/ingest.yaml` (`read_ingest_config`), nếu `status != "confirmed"` → `IngestError` chứa "chưa xác nhận" và nhắc `odu-cfd ingest <dự án> --confirm`. Đọc lại bản vẽ `load_drawing(project/source_file, units_override=cfg.units)`, `extract_plan`, chiều cao dàn nóng: nếu có `library_dir` và `get_model(load_odu_library(library_dir), project.odu.model_id)` thì dùng `height_m` của model, ngược lại `None`. `build_building(...)`, ghi vào `input/geometry/`: `building.stl`, `balcony.stl`, `rail.stl`, `odu.stl` (`write_stl` mỗi nhóm), `scene.glb` (`write_glb`), `geometry.json` (`summary()` + `"source"` + danh sách dàn nóng, `ensure_ascii=False`, indent 2), `viewer.html` (`write_viewer_html`). Có cảnh báo thì in ra stderr dòng `Cảnh báo: ...`. CLI: `odu-cfd geometry <dự án> [--library DIR]`; `odu-cfd view <dự án> [--no-open]` in đường dẫn `viewer.html` (thiếu file thì `IngestError` bảo chạy `geometry`) và mở bằng `webbrowser.open(Path.as_uri())` trừ khi `--no-open`.

- [ ] **Step 1: Viết test (FAIL)**

```python
import json
import re

import pytest

from odu_cfd.cli import main


@pytest.fixture
def project(tmp_path, tower_dxf):
    p = tmp_path / "du-an"
    assert main(["init", str(p)]) == 0
    assert main(["ingest", str(p), str(tower_dxf)]) == 0
    return p


def test_geometry_refuses_unconfirmed(project, capsys):
    assert main(["geometry", str(project)]) == 2
    err = capsys.readouterr().err
    assert "chưa xác nhận" in err and "--confirm" in err


def test_end_to_end(project, capsys):
    assert main(["ingest", str(project), "--confirm"]) == 0
    assert main(["geometry", str(project)]) == 0
    g = project / "input" / "geometry"
    for name in ("building.stl", "balcony.stl", "rail.stl", "odu.stl", "scene.glb", "geometry.json", "viewer.html"):
        assert (g / name).is_file(), name
    info = json.loads((g / "geometry.json").read_text(encoding="utf-8"))
    assert info["num_floors"] == 19
    assert info["parts"]["odu"]["regions"] == 4 * 19
    assert info["parts"]["building"]["volume_m3"] == pytest.approx((600 - 16) * 19 * 3.3)
    assert all(p["closed"] for p in info["parts"].values())
    assert info["warnings"] == []
    names = re.findall(r"^solid (\S+)", (g / "odu.stl").read_text(encoding="ascii"), re.M)
    assert "ODU-01_f00" in names and "ODU-04_f18" in names and len(names) == 76


def test_view_prints_path_without_opening(project, capsys):
    main(["ingest", str(project), "--confirm"])
    main(["geometry", str(project)])
    capsys.readouterr()
    assert main(["view", str(project), "--no-open"]) == 0
    assert "viewer.html" in capsys.readouterr().out


def test_view_before_geometry_is_an_error(project, capsys):
    assert main(["view", str(project), "--no-open"]) == 2
    assert "geometry" in capsys.readouterr().err
```

`19` lấy từ mẫu `project.yaml` (19 tầng, cao 3,3 m); nếu mẫu đổi thì sửa số trong test cho khớp mẫu.

- [ ] **Step 2:** chạy → FAIL. **Step 3:** viết `pipeline.py` và sửa `cli.py`. **Step 4:** `python -m pytest -q` PASS toàn bộ. Cập nhật `.gitignore` nếu cần (đã bỏ qua `projects/*/input/`).

---

### Task 12: Nghiệm thu trên bản vẽ thật Spring Light (người điều phối làm, không giao cho subagent)

- [ ] Chạy `ingest` trên `SPRING_PLAN.dxf` và trên DWG thật `04 WIP/01.Spring light/1.Layout/20260731-Typical tower 1 (ODU).dwg` (qua `third_party/libredwg`), trong dự án thử `D:\CFD_Tool\scratch\spring_test`.
- [ ] Xem `overlay.png` (đọc ảnh), đối chiếu view được chọn, vai trò layer, dàn nóng với bản vẽ. Ghi lại điều chưa đúng.
- [ ] Chạy `geometry`, kiểm tra `geometry.json` (kín, cảnh báo, thể tích) và xem `viewer.html`.
- [ ] Với mỗi lỗi heuristic thật: thêm test hồi quy dùng bản vẽ tổng hợp trước, rồi sửa. Không gõ cứng tên layer hay tọa độ của Spring Light.
- [ ] Ghi kết quả vào `docs/notes/2026-11-26-stage2-real-drawing-findings.md` (đã đúng gì, cần người dùng chỉnh gì, các giới hạn).
- [ ] Rà soát độc lập toàn giai đoạn (subagent mới, opus) trước khi commit; commit/push chỉ khi người dùng yêu cầu.

---

## Self-review

- **Phủ spec giai đoạn 2:** DWG→DXF (Task 2), đọc/đơn vị (3), view + layer (4), dàn nóng (5), xác nhận bằng ảnh + `ingest.yaml` + CLI (6), mô hình kín (7), khối nhà/sàn/lan can/dàn nóng + cảnh báo (8), STL nhiều vùng + GLB (9), viewer offline (10), pipeline + `view` + đầu-cuối (11), nghiệm thu bản vẽ thật (12). Excel/PDF đã chủ ý hoãn (spec mục 2).
- **Nhất quán kiểu:** `IngestConfig` (Task 6) dùng bởi Task 8 (`extract_plan`) và 11; `OduInstance` (Task 5) dùng ở 6, 8, 11; `Mesh` (7) dùng ở 8, 9, 10; tên vùng `<odu_id>_f<NN>` thống nhất giữa Task 8 và 11.
- **Điểm cần thận trọng cho người thực hiện:** API `Insert.matrix44()` của ezdxf (Task 3), hành vi `constrained_delaunay_triangles` với đa giác có lỗ (Task 7), tên khóa `REVISION` trong `three.min.js` (Task 10).
