"""Đọc/ghi phương án bố trí `<dự án>/layouts/<tên>.yaml` (kiểm tra chặt, ghi nguyên tử)."""

import math
import os
import re
import shutil
import tempfile
from pathlib import Path

import yaml

from ..errors import ConfigError
from .model import ID_RE, NAME_RE, SOURCES, Layout, OduPlacement, format_floors, parse_floors

MAX_ODUS = 5000
SIZE_MAX_M = 5.0
SUFFIX = ".yaml"
WIN_RESERVED = frozenset({"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)})


def layouts_dir(project_dir) -> Path:
    return Path(project_dir) / "layouts"


def _check_name(name):
    if not isinstance(name, str) or re.fullmatch(NAME_RE, name) is None:
        raise ConfigError(
            f"tên phương án {name!r} không hợp lệ: chỉ dùng chữ cái không dấu, số, '_', '.', '-' (tối đa 64 ký tự)"
        )
    if name in (".", ".."):
        raise ConfigError(f"tên phương án {name!r} không hợp lệ")
    if name.startswith("-"):
        raise ConfigError(f"tên phương án {name!r} không hợp lệ: không được bắt đầu bằng '-'")
    if name.endswith("."):
        raise ConfigError(f"tên phương án {name!r} không hợp lệ: không được kết thúc bằng dấu '.' (Windows bỏ dấu chấm cuối)")
    if name.split(".")[0].upper() in WIN_RESERVED:
        raise ConfigError(f"tên phương án {name!r} không hợp lệ: trùng tên thiết bị đặc biệt của Windows (CON, PRN, AUX, NUL, COM1-9, LPT1-9)")


def layout_path(project_dir, name) -> Path:
    _check_name(name)
    base = layouts_dir(project_dir)
    path = base / f"{name}{SUFFIX}"
    # phòng thủ thêm: kết quả phải nằm trực tiếp trong layouts/
    if path.parent != base or Path(os.path.normpath(path)).parent != Path(os.path.normpath(base)):
        raise ConfigError(f"tên phương án {name!r} không hợp lệ")
    return path


def list_layouts(project_dir) -> list:
    d = layouts_dir(project_dir)
    if not d.is_dir():
        return []
    names = []
    for f in d.iterdir():
        if not f.is_file() or f.suffix != SUFFIX:
            continue
        stem = f.name[: -len(SUFFIX)]
        try:
            _check_name(stem)
        except ConfigError:
            continue
        names.append(stem)
    return sorted(names)


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _parse_size(v, where):
    if (
        not isinstance(v, (list, tuple))
        or len(v) != 2
        or not all(_is_number(s) and 0 < s <= SIZE_MAX_M for s in v)
    ):
        raise ConfigError(f"'{where}' phải là danh sách 2 số dương không quá {SIZE_MAX_M:g} (rộng, sâu), nhận được {v!r}")
    return (float(v[0]), float(v[1]))


def _parse_floors_field(v, where):
    if not isinstance(v, str):
        raise ConfigError(f"'{where}' phải là chuỗi như '4-19,22-23', nhận được {v!r}")
    try:
        return parse_floors(v)
    except ConfigError as e:
        raise ConfigError(f"'{where}': {e}") from None


def _parse_odu(item, i, seen):
    where = f"odus[{i}]"
    if not isinstance(item, dict):
        raise ConfigError(f"'{where}' phải là một nhóm khai báo (id, x, y, rotation_deg)")
    oid = item.get("id")
    if not isinstance(oid, str) or re.fullmatch(ID_RE, oid) is None:
        raise ConfigError(f"'{where}.id' = {oid!r} không hợp lệ (chỉ chữ cái không dấu, số, '_', '.', '-')")
    if oid in seen:
        raise ConfigError(f"'{where}.id' = {oid!r} bị trùng")
    seen.add(oid)
    nums = {}
    for key in ("x", "y", "rotation_deg"):
        v = item.get(key)
        if not _is_number(v):
            raise ConfigError(f"'{where}.{key}' phải là số hữu hạn, nhận được {v!r}")
        nums[key] = float(v)
    model_id = item.get("model_id")
    if model_id is not None and not isinstance(model_id, str):
        raise ConfigError(f"'{where}.model_id' phải là chuỗi hoặc null, nhận được {model_id!r}")
    size = item.get("size")
    size = None if size is None else _parse_size(size, f"{where}.size")
    floors = item.get("floors")
    floors = None if floors is None else _parse_floors_field(floors, f"{where}.floors")
    return OduPlacement(oid, nums["x"], nums["y"], nums["rotation_deg"], model_id, size, floors)


def _parse_layout(data, expected_name) -> Layout:
    if not isinstance(data, dict):
        raise ConfigError("nội dung phương án phải là một nhóm khai báo (name, source, floors, odus)")
    name = data.get("name")
    if not isinstance(name, str) or re.fullmatch(NAME_RE, name) is None:
        raise ConfigError(f"'name' = {name!r} thiếu hoặc không hợp lệ")
    _check_name(name)
    if expected_name is not None and name != expected_name:
        raise ConfigError(f"'name' = {name!r} không khớp tên file '{expected_name}'")
    description = data.get("description", "")
    if description is None:
        description = ""
    if not isinstance(description, str):
        raise ConfigError(f"'description' phải là chuỗi, nhận được {description!r}")
    source = data.get("source")
    if source not in SOURCES:
        raise ConfigError(f"'source' = {source!r}; chỉ nhận {', '.join(SOURCES)}")
    if "floors" not in data:
        raise ConfigError("thiếu 'floors'")
    floors = _parse_floors_field(data["floors"], "floors")
    if "odus" not in data:
        raise ConfigError("thiếu 'odus'")
    items = data["odus"]
    if items is None:
        items = []
    if not isinstance(items, list):
        raise ConfigError("'odus' phải là danh sách")
    if len(items) > MAX_ODUS:
        raise ConfigError(f"'odus' có {len(items)} dàn nóng, vượt giới hạn {MAX_ODUS}")
    seen = set()
    odus = tuple(_parse_odu(it, i, seen) for i, it in enumerate(items))
    return Layout(name, description, source, floors, odus)


def read_layout(path) -> Layout:
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise ConfigError(f"không đọc được phương án '{path}': {e}") from None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ConfigError(f"phương án '{path}' không phải UTF-8") from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ConfigError(f"phương án '{path}' không phải YAML hợp lệ: {e}") from None
    try:
        return _parse_layout(data, path.name[: -len(SUFFIX)] if path.name.endswith(SUFFIX) else path.stem)
    except ConfigError as e:
        raise ConfigError(f"phương án '{path}': {e}") from None


def _to_dict(layout: Layout) -> dict:
    odus = []
    for o in layout.odus:
        odus.append(
            {
                "id": o.odu_id,
                "x": float(o.x),
                "y": float(o.y),
                "rotation_deg": float(o.rotation_deg),
                "model_id": o.model_id,
                "size": None if o.size is None else [float(o.size[0]), float(o.size[1])],
                "floors": None if o.floors is None else format_floors(o.floors),
            }
        )
    return {
        "name": layout.name,
        "description": layout.description,
        "source": layout.source,
        "floors": format_floors(layout.floors),
        "odus": odus,
    }


def atomic_write_text(path, text, backup=False) -> None:
    """Ghi UTF-8 vào file tạm cùng thư mục rồi os.replace; lỗi thì xóa file tạm, file cũ giữ nguyên."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if backup and path.exists():
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def check_layout(layout: Layout) -> None:
    """Áp đúng bộ kiểm tra của read_layout cho một Layout đã dựng (source, size, floors, id, số lượng, tên).
    Server dùng để /api/validate và /api/save nhất quán. ConfigError tiếng Việt."""
    _parse_layout(_to_dict(layout), layout.name)


def write_layout(path, layout: Layout, backup=True) -> None:
    path = Path(path)
    data = _to_dict(layout)
    stem = path.name[: -len(SUFFIX)] if path.name.endswith(SUFFIX) else path.stem
    try:
        _parse_layout(data, stem)  # không bao giờ ghi phương án mà read_layout sẽ từ chối
    except ConfigError as e:
        raise ConfigError(f"không ghi phương án '{path}': {e}") from None
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    atomic_write_text(path, text, backup=backup)
