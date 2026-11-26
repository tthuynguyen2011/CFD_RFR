import math
from dataclasses import dataclass
from pathlib import Path

import yaml

from .errors import ConfigError

BACKENDS = ("local", "wsl", "cloud")
CONFIDENCE_LEVELS = ("screening", "official")
TERRAIN_CATEGORIES = ("I", "II", "III", "IV", "V")


@dataclass(frozen=True)
class WindConfig:
    ref_height_m: float
    speeds_ms: tuple
    directions_deg: tuple
    terrain_category: str


@dataclass(frozen=True)
class ClimateConfig:
    design_temp_c: float
    wind: WindConfig


@dataclass(frozen=True)
class BuildingConfig:
    num_floors: int
    floor_height_m: float


@dataclass(frozen=True)
class OduConfig:
    model_id: str
    load_fraction: float
    simultaneity_fraction: float
    louver_open_fraction: float


@dataclass(frozen=True)
class ComputeConfig:
    backend: str
    cores: int
    confidence: str


@dataclass(frozen=True)
class Project:
    name: str
    description: str
    climate: ClimateConfig
    building: BuildingConfig
    odu: OduConfig
    compute: ComputeConfig


def _get(d, key, where):
    if not isinstance(d, dict) or key not in d:
        raise ConfigError(f"thiếu '{where}.{key}'" if where else f"thiếu '{key}'")
    return d[key]


def _section(d, key, where):
    value = _get(d, key, where)
    if not isinstance(value, dict):
        raise ConfigError(f"'{where + '.' if where else ''}{key}' phải là một nhóm khai báo")
    return value


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _num(d, key, where, min_=None, max_=None, min_exclusive=False, integer=False):
    v = _get(d, key, where)
    path = f"{where}.{key}"
    if not _is_number(v):
        raise ConfigError(f"'{path}' phải là số, nhận được {v!r}")
    if integer and isinstance(v, float) and not v.is_integer():
        raise ConfigError(f"'{path}' phải là số nguyên, nhận được {v!r}")
    too_low = min_ is not None and (v < min_ or (min_exclusive and v == min_))
    if too_low or (max_ is not None and v > max_):
        raise ConfigError(f"'{path}' = {v} nằm ngoài khoảng cho phép")
    return int(v) if integer else float(v)


def _numlist(d, key, where, min_, max_, max_exclusive=False, integer=False):
    v = _get(d, key, where)
    path = f"{where}.{key}"
    if not isinstance(v, list) or not v:
        raise ConfigError(f"'{path}' phải là danh sách số không rỗng")
    out = []
    for item in v:
        if not _is_number(item):
            raise ConfigError(f"'{path}' có phần tử không phải số: {item!r}")
        if item < min_ or item > max_ or (max_exclusive and item == max_):
            raise ConfigError(f"'{path}' có giá trị {item} nằm ngoài khoảng cho phép")
        if integer and not float(item).is_integer():
            raise ConfigError(f"'{path}' phải là số độ nguyên, nhận được {item!r}")
        if float(item) in out:
            raise ConfigError(f"'{path}' có giá trị trùng lặp: {item!r}")
        out.append(float(item))
    return tuple(out)


def _choice(d, key, where, choices):
    v = _get(d, key, where)
    if v not in choices:
        raise ConfigError(f"'{where}.{key}' = {v!r}; chỉ nhận {', '.join(choices)}")
    return v


def _text(d, key, where):
    v = _get(d, key, where)
    if not isinstance(v, str) or not v.strip():
        raise ConfigError(f"'{where}.{key}' phải là chuỗi không rỗng")
    return v


def parse_project(data) -> Project:
    proj = _section(data, "project", "")
    climate = _section(data, "climate", "")
    wind = _section(climate, "wind", "climate")
    building = _section(data, "building", "")
    odu = _section(data, "odu", "")
    compute = _section(data, "compute", "")

    description = proj.get("description", "")
    if description is None:
        description = ""
    if not isinstance(description, str):
        raise ConfigError("'project.description' phải là chuỗi")

    return Project(
        name=_text(proj, "name", "project"),
        description=description,
        climate=ClimateConfig(
            design_temp_c=_num(climate, "design_temp_c", "climate", min_=-10, max_=60),
            wind=WindConfig(
                ref_height_m=_num(wind, "ref_height_m", "climate.wind", min_=0, min_exclusive=True),
                speeds_ms=_numlist(wind, "speeds_ms", "climate.wind", 0, 60),
                directions_deg=_numlist(wind, "directions_deg", "climate.wind", 0, 360, max_exclusive=True, integer=True),
                terrain_category=_choice(wind, "terrain_category", "climate.wind", TERRAIN_CATEGORIES),
            ),
        ),
        building=BuildingConfig(
            num_floors=_num(building, "num_floors", "building", min_=1, max_=200, integer=True),
            floor_height_m=_num(building, "floor_height_m", "building", min_=2, max_=6),
        ),
        odu=OduConfig(
            model_id=_text(odu, "model_id", "odu"),
            load_fraction=_num(odu, "load_fraction", "odu", min_=0, max_=1, min_exclusive=True),
            simultaneity_fraction=_num(odu, "simultaneity_fraction", "odu", min_=0, max_=1, min_exclusive=True),
            louver_open_fraction=_num(odu, "louver_open_fraction", "odu", min_=0, max_=1, min_exclusive=True),
        ),
        compute=ComputeConfig(
            backend=_choice(compute, "backend", "compute", BACKENDS),
            cores=_num(compute, "cores", "compute", min_=1, integer=True),
            confidence=_choice(compute, "confidence", "compute", CONFIDENCE_LEVELS),
        ),
    )


def load_project(path) -> Project:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"không tìm thấy file cấu hình: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ConfigError(f"file '{path}' phải được lưu bằng UTF-8: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"file YAML không hợp lệ ({path}): {exc}") from exc
    return parse_project(data)
