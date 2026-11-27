import math
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

import yaml

from ..errors import IngestError
from .drawing import UNIT_SCALE
from .layers import ROLES
from .odu_detect import OduInstance

STATUSES = ("proposed", "confirmed")
ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
MAX_ODU_SIZE_M = 5.0
MAX_VIEW_SPAN_M = 1e5
MAX_VIEW_COORD_M = 1e8
MAX_ODUS = 5000


@dataclass
class IngestConfig:
    status: str
    source_file: str  # đường dẫn tương đối so với thư mục dự án
    original_file: str | None  # DWG gốc đã chép vào input/, hoặc None
    units: str  # khóa UNIT_SCALE
    view_id: str
    view_bbox: tuple  # (minx, miny, maxx, maxy) mét
    layers: dict  # layer -> vai trò (chỉ layer có vai trò)
    odu_area_range_m2: tuple
    odus: list  # list[OduInstance]


class _Flow(list):
    """Danh sách ghi theo kiểu một dòng [a, b, c] cho dễ đọc."""


yaml.SafeDumper.add_representer(
    _Flow, lambda dumper, data: dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)
)

_HEADER = (
    "# Kết quả nhận diện bản vẽ. Xem input/overlay.png, sửa file này nếu cần,\n"
    "# rồi chạy: odu-cfd ingest <dự án> --confirm\n"
    "# status: proposed (chờ xác nhận) | confirmed (đã xác nhận)\n"
)


def write_ingest_config(path, cfg) -> None:
    data = {
        "status": cfg.status,
        "source_file": cfg.source_file,
        "original_file": cfg.original_file,
        "units": cfg.units,
        "view_id": cfg.view_id,
        "view_bbox": _Flow(float(v) for v in cfg.view_bbox),
        "layers": dict(cfg.layers),
        "odu_area_range_m2": _Flow(float(v) for v in cfg.odu_area_range_m2),
        "odus": [
            {
                "id": o.odu_id,
                "block": o.block,
                "layer": o.layer,
                "center": _Flow(float(v) for v in o.center),
                "size": _Flow(float(v) for v in o.size),
                "rotation_deg": float(o.rotation_deg),
            }
            for o in cfg.odus
        ],
    }
    text = _HEADER + yaml.dump(data, Dumper=yaml.SafeDumper, allow_unicode=True, sort_keys=False)
    Path(path).write_text(text, encoding="utf-8")


def _fail(msg):
    raise IngestError(msg)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _nums(v, n, path, positive=False):
    if not isinstance(v, (list, tuple)) or len(v) != n or not all(_is_num(x) for x in v):
        _fail(f"'{path}' phải là danh sách {n} số, nhận được {v!r}")
    out = tuple(float(x) for x in v)
    if positive and not all(x > 0 for x in out):
        _fail(f"'{path}' phải gồm các số dương, nhận được {v!r}")
    return out


def _str(v, path):
    if not isinstance(v, str) or not v.strip():
        _fail(f"'{path}' phải là chuỗi không rỗng, nhận được {v!r}")
    return v


def _rel_input_path(v, path):
    """Đường dẫn tương đối nằm trong thư mục input/ của dự án (không tuyệt đối, không '..', không ổ đĩa)."""
    _str(v, path)
    p = PureWindowsPath(v)  # hiểu cả '/' lẫn '\\'
    if p.is_absolute() or p.drive or p.root or v.startswith(("/", "\\")):
        _fail(f"'{path}' = {v!r} phải là đường dẫn tương đối nằm trong thư mục input/")
    parts = p.parts
    if ".." in parts or len(parts) < 2 or parts[0].lower() != "input":
        _fail(f"'{path}' = {v!r} phải là đường dẫn tương đối nằm trong thư mục input/ (không dùng '..')")
    return v


def validate_for_geometry(cfg, require_odus=False) -> None:
    """Kiểm tra tối thiểu để dựng hình học; dùng chung cho `ingest --confirm` và `geometry`.
    Dàn nóng là biến thiết kế (phương án bố trí) nên mặc định không còn bắt buộc có trong ingest.yaml."""
    problems = []
    if not any(role in ("wall_ext", "slab") for role in cfg.layers.values()):
        problems.append("chưa có layer nào vai trò wall_ext (tường ngoài) hoặc slab (sàn) để dựng đường bao")
    if require_odus and not cfg.odus:
        problems.append("chưa có dàn nóng nào trong danh sách odus")
    if problems:
        raise IngestError("input/ingest.yaml chưa đủ để dựng hình học: " + "; ".join(problems))


def read_ingest_config(path) -> IngestConfig:
    path = Path(path)
    if not path.is_file():
        _fail(f"không tìm thấy {path.name} ({path}); hãy chạy 'odu-cfd ingest <dự án> <bản vẽ>' trước")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise IngestError(f"file '{path}' phải được lưu bằng UTF-8: {exc}") from exc
    except yaml.YAMLError as exc:
        raise IngestError(f"file YAML không hợp lệ ({path}): {exc}") from exc
    if not isinstance(data, dict):
        _fail(f"'{path.name}' phải là một nhóm khai báo")

    def need(key):
        if key not in data:
            _fail(f"thiếu '{key}' trong {path.name}")
        return data[key]

    status = need("status")
    if status not in STATUSES:
        _fail(f"'status' = {status!r}; chỉ nhận {', '.join(STATUSES)}")
    units = need("units")
    if units not in UNIT_SCALE:
        _fail(f"'units' = {units!r}; chỉ nhận {', '.join(UNIT_SCALE)}")
    original = data.get("original_file")
    if original is not None:
        original = _rel_input_path(original, "original_file")

    bbox = _nums(need("view_bbox"), 4, "view_bbox")
    if not (bbox[2] > bbox[0] and bbox[3] > bbox[1]):
        _fail(f"'view_bbox' phải có dạng [minx, miny, maxx, maxy] với max > min, nhận được {list(bbox)}")
    if (
        bbox[2] - bbox[0] > MAX_VIEW_SPAN_M
        or bbox[3] - bbox[1] > MAX_VIEW_SPAN_M
        or max(abs(v) for v in bbox) > MAX_VIEW_COORD_M
    ):
        _fail(
            f"'view_bbox' = {list(bbox)} không hợp lý: mỗi cạnh phải <= {MAX_VIEW_SPAN_M:g} m "
            f"và tọa độ <= {MAX_VIEW_COORD_M:g} m"
        )

    layers = need("layers")
    if layers is None:
        layers = {}
    if not isinstance(layers, dict):
        _fail("'layers' phải là danh sách layer: vai trò")
    for name, role in layers.items():
        if role not in ROLES:
            _fail(f"'layers.{name}' = {role!r}; vai trò chỉ nhận {', '.join(ROLES)}")

    area = _nums(need("odu_area_range_m2"), 2, "odu_area_range_m2")
    if not (0 <= area[0] < area[1]):
        _fail(f"'odu_area_range_m2' phải có dạng [nhỏ, lớn] với 0 <= nhỏ < lớn, nhận được {list(area)}")

    raw_odus = need("odus")
    if raw_odus is None:
        raw_odus = []
    if not isinstance(raw_odus, list):
        _fail("'odus' phải là danh sách")
    if len(raw_odus) > MAX_ODUS:
        _fail(f"'odus' có {len(raw_odus)} dàn nóng, nhiều hơn mức cho phép {MAX_ODUS}")
    odus = []
    seen_ids = set()
    for i, o in enumerate(raw_odus):
        where = f"odus[{i}]"
        if not isinstance(o, dict):
            _fail(f"'{where}' phải là một nhóm khai báo")
        for key in ("id", "block", "layer", "center", "size", "rotation_deg"):
            if key not in o:
                _fail(f"thiếu '{where}.{key}'")
        rot = o["rotation_deg"]
        if not _is_num(rot):
            _fail(f"'{where}.rotation_deg' phải là số, nhận được {rot!r}")
        oid = _str(o["id"], f"{where}.id")
        if not ID_RE.fullmatch(oid):
            _fail(f"'{where}.id' = {oid!r} chỉ được gồm chữ cái không dấu, chữ số, '_', '.', '-'")
        if oid in seen_ids:
            _fail(f"'{where}.id' = {oid!r} trùng với dàn nóng khác; id dàn nóng phải duy nhất")
        seen_ids.add(oid)
        size = _nums(o["size"], 2, f"{where}.size", positive=True)
        if any(x > MAX_ODU_SIZE_M for x in size):
            _fail(f"'{where}.size' = {list(size)} vượt {MAX_ODU_SIZE_M:g} m ở một cạnh")
        odus.append(
            OduInstance(
                oid,
                _str(o["block"], f"{where}.block"),
                _str(o["layer"], f"{where}.layer"),
                _nums(o["center"], 2, f"{where}.center"),
                size,
                float(rot),
            )
        )

    return IngestConfig(
        status=status,
        source_file=_rel_input_path(need("source_file"), "source_file"),
        original_file=original,
        units=units,
        view_id=_str(need("view_id"), "view_id"),
        view_bbox=bbox,
        layers=dict(layers),
        odu_area_range_m2=area,
        odus=odus,
    )
