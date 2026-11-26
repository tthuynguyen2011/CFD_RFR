# ODU-CFD Giai đoạn 1: Nền tảng — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Quy tắc git của dự án này:** KHÔNG chạy `git commit` hay `git push` trừ khi người dùng yêu cầu rõ. Cuối mỗi task chỉ chạy `git status --short` làm điểm kiểm tra. Remote `origin` đã cấu hình sẵn.

**Goal:** Dựng khung package `odu_cfd` gồm schema `project.yaml` có kiểm tra, mô hình dàn nóng (ODU) + thư viện, mô hình gió/khí hậu + bộ kịch bản, và CLI (`init`, `validate`, `scenarios`), tất cả có test tự động.

**Architecture:** Package Python thuần (dataclass + PyYAML, không phụ thuộc web/pydantic) trong `D:\CFD_Tool\src\odu_cfd\`. Mỗi module một trách nhiệm: `schema` (đọc và kiểm tra cấu hình), `odu` (model và vật lý dàn nóng), `climate` (profile gió, kịch bản), `cli`. Mọi lỗi cấu hình ném `ConfigError` với thông báo chỉ rõ trường sai; CLI chuyển thành thông báo và mã thoát 2.

**Tech Stack:** Python 3.12, PyYAML 6, pytest 9. Chạy không cần cài package: pytest dùng `pythonpath = ["src"]`; CLI chạy bằng `python -m odu_cfd`.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `pyproject.toml` | metadata, cấu hình pytest, entry point `odu-cfd` |
| `.gitignore` | bỏ cache, dữ liệu case/kết quả của dự án |
| `src/odu_cfd/__init__.py` | `__version__` |
| `src/odu_cfd/__main__.py` | cho phép `python -m odu_cfd` |
| `src/odu_cfd/errors.py` | `ConfigError` |
| `src/odu_cfd/schema.py` | dataclass cấu hình + `load_project` + kiểm tra |
| `src/odu_cfd/odu/__init__.py` | export của gói `odu` |
| `src/odu_cfd/odu/model.py` | `OduModel`, nhiệt thải, nhiệt độ thổi |
| `src/odu_cfd/odu/library.py` | đọc thư viện YAML, `get_model` |
| `src/odu_cfd/climate/__init__.py` | export của gói `climate` |
| `src/odu_cfd/climate/profile.py` | profile gió lớp biên khí quyển |
| `src/odu_cfd/climate/scenarios.py` | `Scenario`, `build_scenarios` |
| `src/odu_cfd/templates/project.yaml` | mẫu dự án cho `init` |
| `src/odu_cfd/cli.py` | `main(argv)` với `init`, `validate`, `scenarios` |
| `library/odu/_template.yaml` | mẫu khai báo model ODU (không được nạp) |
| `tests/conftest.py` | fixture dict cấu hình hợp lệ |
| `tests/test_schema.py`, `tests/test_odu_model.py`, `tests/test_odu_library.py`, `tests/test_wind_profile.py`, `tests/test_scenarios.py`, `tests/test_cli.py` | test từng module |

**Về dữ liệu dàn nóng thật:** giai đoạn này KHÔNG đưa số liệu model hãng vào `library/` vì chưa có datasheet đã kiểm chứng. Thư viện bắt buộc mỗi model có trường `source` (nguồn). Số liệu thật được nhập ở giai đoạn 2 và 5 từ datasheet/báo cáo hãng. Test dùng dữ liệu tự lập trong `tests/`.

**Về hệ số mũ gió:** bảng hệ số mũ I–V (0,10; 0,15; 0,20; 0,27; 0,35) là giá trị tham chiếu theo AIJ. Việc ánh xạ sang cấp địa hình TCVN 2737 cần kiểm chứng ở giai đoạn 3; bảng được tách riêng một hằng số để dễ thay.

---

### Task 1: Khung dự án

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/odu_cfd/__init__.py`, `src/odu_cfd/__main__.py`, `src/odu_cfd/errors.py`, `tests/test_smoke.py`

- [ ] **Step 1: Tạo `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "odu-cfd"
version = "0.1.0"
description = "Tự động đánh giá nhiệt độ ban công đặt dàn nóng bằng CFD"
requires-python = ">=3.10"
dependencies = ["PyYAML>=6.0"]

[project.scripts]
odu-cfd = "odu_cfd.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
odu_cfd = ["templates/*.yaml"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Tạo `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
projects/*/cases/
projects/*/results/
```

- [ ] **Step 3: Tạo các file package**

`src/odu_cfd/__init__.py`:

```python
__version__ = "0.1.0"
```

`src/odu_cfd/errors.py`:

```python
class ConfigError(Exception):
    """Cấu hình hoặc dữ liệu đầu vào không hợp lệ; thông báo chỉ rõ trường sai."""
```

`src/odu_cfd/__main__.py`:

```python
from .cli import main

raise SystemExit(main())
```

- [ ] **Step 4: Viết test khói (failing)**

`tests/test_smoke.py`:

```python
import odu_cfd
from odu_cfd.errors import ConfigError


def test_version_is_string():
    assert isinstance(odu_cfd.__version__, str)


def test_config_error_is_exception():
    assert issubclass(ConfigError, Exception)
```

- [ ] **Step 5: Chạy test**

Run: `cd /d/CFD_Tool && python -m pytest tests/test_smoke.py -v`
Expected: 2 passed

- [ ] **Step 6: Điểm kiểm tra**

Run: `cd /d/CFD_Tool && git status --short`
Expected: liệt kê các file mới (không commit).

---

### Task 2: Schema `project.yaml`

**Files:**
- Create: `src/odu_cfd/schema.py`, `tests/conftest.py`, `tests/test_schema.py`

- [ ] **Step 1: Tạo fixture dùng chung**

`tests/conftest.py`:

```python
import copy

import pytest

VALID = {
    "project": {"name": "demo", "description": "dự án thử"},
    "climate": {
        "design_temp_c": 36.8,
        "wind": {
            "ref_height_m": 10.0,
            "speeds_ms": [0, 2.6],
            "directions_deg": [0, 90, 180, 270],
            "terrain_category": "III",
        },
    },
    "building": {"num_floors": 19, "floor_height_m": 3.3},
    "odu": {
        "model_id": "test-odu",
        "load_fraction": 0.8,
        "simultaneity_fraction": 0.8,
        "louver_open_fraction": 0.8,
    },
    "compute": {"backend": "local", "cores": 4, "confidence": "screening"},
}


@pytest.fixture
def valid_dict():
    return copy.deepcopy(VALID)
```

- [ ] **Step 2: Viết test schema (failing)**

`tests/test_schema.py`:

```python
import pytest
import yaml

from odu_cfd.errors import ConfigError
from odu_cfd.schema import load_project, parse_project


def test_parse_valid_project(valid_dict):
    p = parse_project(valid_dict)
    assert p.name == "demo"
    assert p.climate.design_temp_c == 36.8
    assert p.climate.wind.speeds_ms == (0.0, 2.6)
    assert p.climate.wind.directions_deg == (0.0, 90.0, 180.0, 270.0)
    assert p.climate.wind.terrain_category == "III"
    assert p.building.num_floors == 19
    assert p.odu.model_id == "test-odu"
    assert p.odu.simultaneity_fraction == 0.8
    assert p.compute.backend == "local"
    assert p.compute.confidence == "screening"


def test_load_project_from_file(tmp_path, valid_dict):
    f = tmp_path / "project.yaml"
    f.write_text(yaml.safe_dump(valid_dict, allow_unicode=True), encoding="utf-8")
    assert load_project(f).name == "demo"


def test_load_project_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="không tìm thấy"):
        load_project(tmp_path / "nope.yaml")


def test_load_project_bad_yaml(tmp_path):
    f = tmp_path / "project.yaml"
    f.write_text("a: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="YAML"):
        load_project(f)


def _set(d, path, value):
    for key in path[:-1]:
        d = d[key]
    d[path[-1]] = value


def _del(d, path):
    for key in path[:-1]:
        d = d[key]
    del d[path[-1]]


@pytest.mark.parametrize(
    "path,value,fragment",
    [
        (("climate", "design_temp_c"), 90, "climate.design_temp_c"),
        (("climate", "design_temp_c"), "nóng", "climate.design_temp_c"),
        (("climate", "wind", "speeds_ms"), [], "climate.wind.speeds_ms"),
        (("climate", "wind", "speeds_ms"), [-1], "climate.wind.speeds_ms"),
        (("climate", "wind", "directions_deg"), [360], "climate.wind.directions_deg"),
        (("climate", "wind", "terrain_category"), "IX", "climate.wind.terrain_category"),
        (("building", "num_floors"), 0, "building.num_floors"),
        (("building", "num_floors"), 2.5, "building.num_floors"),
        (("building", "floor_height_m"), 10, "building.floor_height_m"),
        (("odu", "load_fraction"), 0, "odu.load_fraction"),
        (("odu", "simultaneity_fraction"), 1.2, "odu.simultaneity_fraction"),
        (("odu", "louver_open_fraction"), True, "odu.louver_open_fraction"),
        (("compute", "backend"), "gpu", "compute.backend"),
        (("compute", "cores"), 0, "compute.cores"),
        (("compute", "confidence"), "maybe", "compute.confidence"),
    ],
)
def test_invalid_value_names_the_field(valid_dict, path, value, fragment):
    _set(valid_dict, path, value)
    with pytest.raises(ConfigError, match=fragment):
        parse_project(valid_dict)


@pytest.mark.parametrize(
    "path",
    [
        ("project", "name"),
        ("climate", "design_temp_c"),
        ("climate", "wind", "terrain_category"),
        ("building", "floor_height_m"),
        ("odu", "model_id"),
        ("compute", "backend"),
    ],
)
def test_missing_field_is_reported(valid_dict, path):
    _del(valid_dict, path)
    with pytest.raises(ConfigError, match="thiếu") as exc:
        parse_project(valid_dict)
    assert ".".join(path) in str(exc.value)


def test_top_level_must_be_mapping():
    with pytest.raises(ConfigError, match="thiếu"):
        parse_project([1, 2, 3])
```

- [ ] **Step 3: Chạy test để thấy fail**

Run: `cd /d/CFD_Tool && python -m pytest tests/test_schema.py -v`
Expected: FAIL/ERROR với `ModuleNotFoundError: No module named 'odu_cfd.schema'`

- [ ] **Step 4: Cài đặt `schema.py`**

`src/odu_cfd/schema.py`:

```python
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
    return isinstance(v, (int, float)) and not isinstance(v, bool)


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


def _numlist(d, key, where, min_, max_, max_exclusive=False):
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
                directions_deg=_numlist(wind, "directions_deg", "climate.wind", 0, 360, max_exclusive=True),
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
    except yaml.YAMLError as exc:
        raise ConfigError(f"file YAML không hợp lệ ({path}): {exc}") from exc
    return parse_project(data)
```

- [ ] **Step 5: Chạy test để thấy pass**

Run: `cd /d/CFD_Tool && python -m pytest tests/test_schema.py -v`
Expected: tất cả PASS (khoảng 30 test)

- [ ] **Step 6: Điểm kiểm tra**

Run: `cd /d/CFD_Tool && git status --short`

---

### Task 3: Mô hình dàn nóng (vật lý)

**Files:**
- Create: `src/odu_cfd/odu/__init__.py`, `src/odu_cfd/odu/model.py`, `tests/test_odu_model.py`

Quy ước: nhiệt thải Q = (công suất lạnh + công suất nén) × tỷ lệ tải (đúng cách Panasonic định nghĩa tải trong báo cáo Spring Light). Lưu lượng gió coi là không đổi theo tải (giả định bảo thủ, ghi rõ trong docstring).

- [ ] **Step 1: Viết test (failing)**

`tests/test_odu_model.py`:

```python
import pytest

from odu_cfd.odu.model import OduModel

MODEL = OduModel(
    model_id="test-odu",
    vendor="TestCo",
    width_m=0.9,
    depth_m=0.35,
    height_m=0.8,
    airflow_m3_h=6000.0,
    cooling_kw=10.0,
    compressor_kw=3.0,
    intake_limit_c=46.0,
    source="dữ liệu thử trong tests",
)


def test_heat_rejection_is_cooling_plus_compressor_times_load():
    assert MODEL.heat_rejection_kw(1.0) == pytest.approx(13.0)
    assert MODEL.heat_rejection_kw(0.8) == pytest.approx(10.4)


def test_discharge_temperature_matches_energy_balance():
    # rho = 101325/(287.05*308.15) = 1.1455 kg/m3; mdot = rho*6000/3600 = 1.9092 kg/s
    # dT = 13000 W / (1.9092 kg/s * 1005 J/kg/K) = 6.775 K
    t_out = MODEL.discharge_temperature_c(35.0, 1.0)
    assert t_out == pytest.approx(35.0 + 6.775, abs=0.02)


def test_hotter_intake_gives_lower_dT_because_air_is_thinner():
    dt_cool = MODEL.discharge_temperature_c(25.0, 1.0) - 25.0
    dt_hot = MODEL.discharge_temperature_c(45.0, 1.0) - 45.0
    assert dt_hot > dt_cool


def test_zero_load_gives_no_temperature_rise():
    assert MODEL.discharge_temperature_c(35.0, 0.0) == pytest.approx(35.0)


def test_load_outside_range_rejected():
    with pytest.raises(ValueError):
        MODEL.heat_rejection_kw(1.5)
    with pytest.raises(ValueError):
        MODEL.heat_rejection_kw(-0.1)
```

- [ ] **Step 2: Chạy test để thấy fail**

Run: `cd /d/CFD_Tool && python -m pytest tests/test_odu_model.py -v`
Expected: FAIL/ERROR `ModuleNotFoundError: odu_cfd.odu`

- [ ] **Step 3: Cài đặt**

`src/odu_cfd/odu/model.py`:

```python
from dataclasses import dataclass

CP_AIR = 1005.0  # J/(kg.K)
R_AIR = 287.05  # J/(kg.K)
P_ATM = 101325.0  # Pa


@dataclass(frozen=True)
class OduModel:
    model_id: str
    vendor: str
    width_m: float
    depth_m: float
    height_m: float
    airflow_m3_h: float
    cooling_kw: float
    compressor_kw: float
    intake_limit_c: float
    source: str

    def heat_rejection_kw(self, load_fraction: float) -> float:
        """Nhiệt thải ra dàn ngưng = (công suất lạnh + công suất nén) x tải.

        Lưu lượng gió được coi là không đổi theo tải (giả định bảo thủ).
        """
        if not 0.0 <= load_fraction <= 1.0:
            raise ValueError(f"load_fraction phải trong [0, 1], nhận được {load_fraction}")
        return (self.cooling_kw + self.compressor_kw) * load_fraction

    def discharge_temperature_c(self, intake_c: float, load_fraction: float) -> float:
        """Nhiệt độ thổi theo cân bằng năng lượng tại nhiệt độ hút thực tế."""
        rho = P_ATM / (R_AIR * (intake_c + 273.15))
        mdot = rho * self.airflow_m3_h / 3600.0
        delta_t = self.heat_rejection_kw(load_fraction) * 1000.0 / (mdot * CP_AIR)
        return intake_c + delta_t
```

`src/odu_cfd/odu/__init__.py`:

```python
from .library import get_model, load_odu_library
from .model import OduModel

__all__ = ["OduModel", "get_model", "load_odu_library"]
```

- [ ] **Step 4: Tạo `library.py` rỗng tạm để import không lỗi**

`src/odu_cfd/odu/library.py`:

```python
def load_odu_library(directory):
    raise NotImplementedError


def get_model(library, model_id):
    raise NotImplementedError
```

(Task 4 thay thế file này bằng bản đầy đủ.)

- [ ] **Step 5: Chạy test để thấy pass**

Run: `cd /d/CFD_Tool && python -m pytest tests/test_odu_model.py -v`
Expected: 5 passed

- [ ] **Step 6: Điểm kiểm tra**

Run: `cd /d/CFD_Tool && git status --short`

---

### Task 4: Thư viện dàn nóng

**Files:**
- Modify: `src/odu_cfd/odu/library.py` (thay toàn bộ)
- Create: `library/odu/_template.yaml`, `tests/test_odu_library.py`

Định dạng file: `models:` là danh sách; mỗi model đủ các trường của `OduModel`; `source` bắt buộc khác rỗng. File bắt đầu bằng `_` bị bỏ qua.

- [ ] **Step 1: Viết test (failing)**

`tests/test_odu_library.py`:

```python
import pytest
import yaml

from odu_cfd.errors import ConfigError
from odu_cfd.odu import get_model, load_odu_library

ENTRY = {
    "model_id": "test-odu",
    "vendor": "TestCo",
    "width_m": 0.9,
    "depth_m": 0.35,
    "height_m": 0.8,
    "airflow_m3_h": 6000,
    "cooling_kw": 10.0,
    "compressor_kw": 3.0,
    "intake_limit_c": 46.0,
    "source": "dữ liệu thử",
}


def _write(path, entries):
    path.write_text(yaml.safe_dump({"models": entries}, allow_unicode=True), encoding="utf-8")


def test_loads_models_from_all_yaml_files(tmp_path):
    _write(tmp_path / "a.yaml", [ENTRY])
    other = dict(ENTRY, model_id="other-odu")
    _write(tmp_path / "b.yaml", [other])
    lib = load_odu_library(tmp_path)
    assert set(lib) == {"test-odu", "other-odu"}
    assert lib["test-odu"].airflow_m3_h == 6000.0


def test_underscore_files_are_ignored(tmp_path):
    _write(tmp_path / "_template.yaml", [ENTRY])
    assert load_odu_library(tmp_path) == {}


def test_missing_directory_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="thư viện"):
        load_odu_library(tmp_path / "khong_co")


def test_source_is_mandatory(tmp_path):
    bad = dict(ENTRY)
    bad["source"] = ""
    _write(tmp_path / "a.yaml", [bad])
    with pytest.raises(ConfigError, match="source"):
        load_odu_library(tmp_path)


def test_missing_field_names_the_model(tmp_path):
    bad = dict(ENTRY)
    del bad["airflow_m3_h"]
    _write(tmp_path / "a.yaml", [bad])
    with pytest.raises(ConfigError, match="airflow_m3_h"):
        load_odu_library(tmp_path)


def test_non_positive_value_rejected(tmp_path):
    bad = dict(ENTRY, width_m=0)
    _write(tmp_path / "a.yaml", [bad])
    with pytest.raises(ConfigError, match="width_m"):
        load_odu_library(tmp_path)


def test_duplicate_model_id_rejected(tmp_path):
    _write(tmp_path / "a.yaml", [ENTRY, ENTRY])
    with pytest.raises(ConfigError, match="trùng"):
        load_odu_library(tmp_path)


def test_get_model_unknown_lists_available(tmp_path):
    _write(tmp_path / "a.yaml", [ENTRY])
    lib = load_odu_library(tmp_path)
    assert get_model(lib, "test-odu").vendor == "TestCo"
    with pytest.raises(ConfigError, match="test-odu"):
        get_model(lib, "khong-co")
```

- [ ] **Step 2: Chạy test để thấy fail**

Run: `cd /d/CFD_Tool && python -m pytest tests/test_odu_library.py -v`
Expected: FAIL (`NotImplementedError`)

- [ ] **Step 3: Cài đặt `library.py` đầy đủ**

`src/odu_cfd/odu/library.py`:

```python
from pathlib import Path

import yaml

from ..errors import ConfigError
from .model import OduModel

_NUMERIC = (
    "width_m",
    "depth_m",
    "height_m",
    "airflow_m3_h",
    "cooling_kw",
    "compressor_kw",
    "intake_limit_c",
)


def _parse_entry(entry, origin):
    if not isinstance(entry, dict):
        raise ConfigError(f"{origin}: mỗi model phải là một nhóm khai báo")
    model_id = entry.get("model_id")
    if not isinstance(model_id, str) or not model_id.strip():
        raise ConfigError(f"{origin}: thiếu 'model_id'")
    where = f"{origin} [{model_id}]"

    for key in ("vendor", "source"):
        value = entry.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"{where}: thiếu hoặc rỗng '{key}'")

    values = {}
    for key in _NUMERIC:
        if key not in entry:
            raise ConfigError(f"{where}: thiếu '{key}'")
        v = entry[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            raise ConfigError(f"{where}: '{key}' phải là số dương, nhận được {v!r}")
        values[key] = float(v)

    return OduModel(model_id=model_id, vendor=entry["vendor"], source=entry["source"], **values)


def load_odu_library(directory) -> dict:
    directory = Path(directory)
    if not directory.is_dir():
        raise ConfigError(f"không tìm thấy thư viện dàn nóng: {directory}")

    library = {}
    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ConfigError(f"file YAML không hợp lệ ({path}): {exc}") from exc
        entries = data.get("models") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise ConfigError(f"{path.name}: cần khóa 'models' là một danh sách")
        for entry in entries:
            model = _parse_entry(entry, path.name)
            if model.model_id in library:
                raise ConfigError(f"model_id trùng: {model.model_id}")
            library[model.model_id] = model
    return library


def get_model(library: dict, model_id: str) -> OduModel:
    if model_id not in library:
        available = ", ".join(sorted(library)) or "(thư viện trống)"
        raise ConfigError(f"không có model '{model_id}' trong thư viện; hiện có: {available}")
    return library[model_id]
```

- [ ] **Step 4: Tạo mẫu khai báo (không được nạp vì bắt đầu bằng `_`)**

`library/odu/_template.yaml`:

```yaml
# Mẫu khai báo model dàn nóng. File bắt đầu bằng "_" KHÔNG được nạp.
# Sao chép sang file mới (ví dụ daikin.yaml), điền số liệu THẬT từ datasheet.
# 'source' bắt buộc: ghi rõ datasheet/tài liệu và trang nào.
models:
  - model_id: "TÊN-MODEL"
    vendor: "Hãng"
    width_m: 0.0        # m, mặt rộng
    depth_m: 0.0        # m, bề dày theo hướng hút-thổi
    height_m: 0.0       # m
    airflow_m3_h: 0     # m3/h, lưu lượng gió qua dàn
    cooling_kw: 0.0     # kW, công suất lạnh danh định
    compressor_kw: 0.0  # kW, công suất điện máy nén
    intake_limit_c: 0.0 # °C, giới hạn nhiệt độ hút cho phép của hãng
    source: "Datasheet XYZ, trang N"
```

- [ ] **Step 5: Chạy test để thấy pass**

Run: `cd /d/CFD_Tool && python -m pytest tests/test_odu_library.py tests/test_odu_model.py -v`
Expected: tất cả PASS

- [ ] **Step 6: Điểm kiểm tra**

Run: `cd /d/CFD_Tool && git status --short`

---

### Task 5: Profile gió

**Files:**
- Create: `src/odu_cfd/climate/__init__.py`, `src/odu_cfd/climate/profile.py`, `tests/test_wind_profile.py`

- [ ] **Step 1: Viết test (failing)**

`tests/test_wind_profile.py`:

```python
import pytest

from odu_cfd.climate.profile import TERRAIN_ALPHA, wind_speed_at


def test_speed_at_reference_height_equals_reference_speed():
    assert wind_speed_at(10.0, 2.6, 10.0, "III") == pytest.approx(2.6)


def test_power_law_above_reference():
    expected = 2.6 * (40.0 / 10.0) ** TERRAIN_ALPHA["III"]
    assert wind_speed_at(40.0, 2.6, 10.0, "III") == pytest.approx(expected)


def test_rougher_terrain_has_steeper_profile():
    smooth = wind_speed_at(60.0, 2.0, 10.0, "I")
    rough = wind_speed_at(60.0, 2.0, 10.0, "V")
    assert rough > smooth


def test_speed_increases_with_height():
    assert wind_speed_at(60.0, 2.0, 10.0, "III") > wind_speed_at(20.0, 2.0, 10.0, "III")


def test_calm_stays_calm():
    assert wind_speed_at(60.0, 0.0, 10.0, "III") == 0.0


@pytest.mark.parametrize("z", [0.0, -5.0])
def test_non_positive_height_rejected(z):
    with pytest.raises(ValueError):
        wind_speed_at(z, 2.0, 10.0, "III")


def test_unknown_category_rejected():
    with pytest.raises(ValueError):
        wind_speed_at(10.0, 2.0, 10.0, "IX")
```

- [ ] **Step 2: Chạy test để thấy fail**

Run: `cd /d/CFD_Tool && python -m pytest tests/test_wind_profile.py -v`
Expected: FAIL/ERROR `ModuleNotFoundError: odu_cfd.climate`

- [ ] **Step 3: Cài đặt**

`src/odu_cfd/climate/profile.py`:

```python
# Hệ số mũ profile gió theo cấp địa hình (tham chiếu AIJ).
# Cần đối chiếu với cấp địa hình TCVN 2737 trước khi dùng cho kết quả chính thức.
TERRAIN_ALPHA = {"I": 0.10, "II": 0.15, "III": 0.20, "IV": 0.27, "V": 0.35}


def wind_speed_at(z_m, ref_speed_ms, ref_height_m, category) -> float:
    """Vận tốc gió ở độ cao z theo luật mũ: u(z) = u_ref * (z / z_ref) ** alpha."""
    if z_m <= 0 or ref_height_m <= 0:
        raise ValueError("độ cao phải dương")
    if category not in TERRAIN_ALPHA:
        raise ValueError(f"cấp địa hình không hợp lệ: {category!r}")
    return ref_speed_ms * (z_m / ref_height_m) ** TERRAIN_ALPHA[category]
```

`src/odu_cfd/climate/__init__.py`:

```python
from .profile import TERRAIN_ALPHA, wind_speed_at
from .scenarios import Scenario, build_scenarios

__all__ = ["TERRAIN_ALPHA", "wind_speed_at", "Scenario", "build_scenarios"]
```

- [ ] **Step 4: Tạo `scenarios.py` tạm để import không lỗi**

`src/odu_cfd/climate/scenarios.py`:

```python
class Scenario:
    pass


def build_scenarios(wind):
    raise NotImplementedError
```

(Task 6 thay thế bằng bản đầy đủ.)

- [ ] **Step 5: Chạy test để thấy pass**

Run: `cd /d/CFD_Tool && python -m pytest tests/test_wind_profile.py -v`
Expected: 8 passed

- [ ] **Step 6: Điểm kiểm tra**

Run: `cd /d/CFD_Tool && git status --short`

---

### Task 6: Bộ kịch bản

**Files:**
- Modify: `src/odu_cfd/climate/scenarios.py` (thay toàn bộ)
- Create: `tests/test_scenarios.py`

Quy tắc: tốc độ gió bằng 0 cho đúng một kịch bản `calm` (không phụ thuộc hướng), bắt buộc `transient=True` (steady RANS không đáng tin khi lặng gió). Các tốc độ khác tạo một kịch bản cho mỗi hướng, `transient=False`.

- [ ] **Step 1: Viết test (failing)**

`tests/test_scenarios.py`:

```python
from odu_cfd.climate import build_scenarios
from odu_cfd.schema import WindConfig


def _wind(speeds, dirs):
    return WindConfig(
        ref_height_m=10.0,
        speeds_ms=tuple(float(s) for s in speeds),
        directions_deg=tuple(float(d) for d in dirs),
        terrain_category="III",
    )


def test_calm_is_a_single_transient_scenario():
    scenarios = build_scenarios(_wind([0, 2.6], [0, 90]))
    calm = [s for s in scenarios if s.wind_speed_ms == 0]
    assert len(calm) == 1
    assert calm[0].scenario_id == "calm"
    assert calm[0].transient is True


def test_wind_scenarios_cover_every_direction_and_are_steady():
    scenarios = build_scenarios(_wind([0, 2.6], [0, 90]))
    ids = [s.scenario_id for s in scenarios]
    assert ids == ["calm", "w2.6_d000", "w2.6_d090"]
    assert all(not s.transient for s in scenarios if s.wind_speed_ms > 0)


def test_count_is_calm_plus_speeds_times_directions():
    scenarios = build_scenarios(_wind([0, 1, 2.6], [0, 90, 180, 270]))
    assert len(scenarios) == 1 + 2 * 4


def test_without_calm_speed_no_calm_scenario():
    scenarios = build_scenarios(_wind([1.8], [45]))
    assert [s.scenario_id for s in scenarios] == ["w1.8_d045"]


def test_ids_are_unique():
    scenarios = build_scenarios(_wind([0, 1, 2], [0, 45, 90, 135]))
    ids = [s.scenario_id for s in scenarios]
    assert len(ids) == len(set(ids))
```

- [ ] **Step 2: Chạy test để thấy fail**

Run: `cd /d/CFD_Tool && python -m pytest tests/test_scenarios.py -v`
Expected: FAIL (`NotImplementedError`)

- [ ] **Step 3: Cài đặt**

`src/odu_cfd/climate/scenarios.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    wind_speed_ms: float
    wind_from_deg: float
    transient: bool


def build_scenarios(wind) -> list:
    """Tạo danh sách kịch bản từ cấu hình gió (WindConfig).

    Lặng gió (0 m/s) -> một kịch bản 'calm' transient (steady RANS không đáng tin).
    Mỗi tốc độ > 0 -> một kịch bản steady cho mỗi hướng.
    """
    scenarios = []
    for speed in wind.speeds_ms:
        if speed == 0:
            scenarios.append(Scenario("calm", 0.0, 0.0, True))
            continue
        for direction in wind.directions_deg:
            scenario_id = f"w{speed:g}_d{int(direction):03d}"
            scenarios.append(Scenario(scenario_id, speed, direction, False))
    return scenarios
```

- [ ] **Step 4: Chạy test để thấy pass**

Run: `cd /d/CFD_Tool && python -m pytest tests/test_scenarios.py -v`
Expected: 5 passed

- [ ] **Step 5: Điểm kiểm tra**

Run: `cd /d/CFD_Tool && git status --short`

---

### Task 7: Mẫu dự án và CLI

**Files:**
- Create: `src/odu_cfd/templates/project.yaml`, `src/odu_cfd/cli.py`, `tests/test_cli.py`

Lệnh: `init <dir>` tạo dự án mới; `validate <dir> [--library DIR]` kiểm tra cấu hình (và model có trong thư viện nếu có `--library`); `scenarios <dir>` ghi `scenarios.json`. Lỗi cấu hình: in `Lỗi: ...` ra stderr, mã thoát 2.

- [ ] **Step 1: Tạo mẫu dự án**

`src/odu_cfd/templates/project.yaml`:

```yaml
# Cấu hình dự án ODU-CFD. Sửa các giá trị theo dự án rồi chạy: odu-cfd validate <thư-mục-dự-án>
project:
  name: __NAME__
  description: ""

climate:
  design_temp_c: 35.0      # °C, nhiệt độ thiết kế (theo TCVN 5687 / QCVN 02 hoặc yêu cầu hãng)
  wind:
    ref_height_m: 10.0     # m, độ cao đo vận tốc gió tham chiếu
    speeds_ms: [0, 2.6]    # m/s; 0 = lặng gió (chạy transient)
    directions_deg: [0, 90, 180, 270]   # hướng gió thổi TỪ, 0 = Bắc, 90 = Đông
    terrain_category: III  # I..V

building:
  num_floors: 19
  floor_height_m: 3.3

odu:
  model_id: TÊN-MODEL-TRONG-THƯ-VIỆN
  load_fraction: 0.8            # tải vận hành
  simultaneity_fraction: 0.8    # tỷ lệ dàn hoạt động đồng thời
  louver_open_fraction: 0.8     # độ hở louver

compute:
  backend: local         # local | wsl | cloud
  cores: 4
  confidence: screening  # screening | official
```

- [ ] **Step 2: Viết test CLI (failing)**

`tests/test_cli.py`:

```python
import json

import pytest
import yaml

from odu_cfd.cli import main


def test_init_creates_project_structure(tmp_path, capsys):
    target = tmp_path / "du_an_a"
    assert main(["init", str(target)]) == 0
    assert (target / "project.yaml").is_file()
    for sub in ("input", "cases", "results"):
        assert (target / sub).is_dir()
    assert "name: du_an_a" in (target / "project.yaml").read_text(encoding="utf-8")


def test_init_refuses_to_overwrite(tmp_path, capsys):
    target = tmp_path / "du_an_a"
    assert main(["init", str(target)]) == 0
    assert main(["init", str(target)]) == 2
    assert "đã tồn tại" in capsys.readouterr().err


def test_validate_accepts_template_project(tmp_path, capsys):
    target = tmp_path / "du_an_a"
    main(["init", str(target)])
    assert main(["validate", str(target)]) == 0
    out = capsys.readouterr().out
    assert "OK" in out
    assert "du_an_a" in out


def test_validate_reports_bad_field(tmp_path, capsys):
    target = tmp_path / "du_an_a"
    main(["init", str(target)])
    data = yaml.safe_load((target / "project.yaml").read_text(encoding="utf-8"))
    data["compute"]["backend"] = "gpu"
    (target / "project.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert main(["validate", str(target)]) == 2
    assert "compute.backend" in capsys.readouterr().err


def test_validate_with_library_checks_model(tmp_path, capsys):
    target = tmp_path / "du_an_a"
    main(["init", str(target)])
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "a.yaml").write_text(yaml.safe_dump({"models": []}), encoding="utf-8")
    assert main(["validate", str(target), "--library", str(lib)]) == 2
    assert "TÊN-MODEL-TRONG-THƯ-VIỆN" in capsys.readouterr().err


def test_validate_with_library_accepts_known_model(tmp_path, capsys):
    target = tmp_path / "du_an_a"
    main(["init", str(target)])
    data = yaml.safe_load((target / "project.yaml").read_text(encoding="utf-8"))
    data["odu"]["model_id"] = "test-odu"
    (target / "project.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    lib = tmp_path / "lib"
    lib.mkdir()
    entry = {
        "model_id": "test-odu", "vendor": "TestCo", "width_m": 0.9, "depth_m": 0.35,
        "height_m": 0.8, "airflow_m3_h": 6000, "cooling_kw": 10, "compressor_kw": 3,
        "intake_limit_c": 46, "source": "dữ liệu thử",
    }
    (lib / "a.yaml").write_text(yaml.safe_dump({"models": [entry]}, allow_unicode=True), encoding="utf-8")
    assert main(["validate", str(target), "--library", str(lib)]) == 0


def test_scenarios_writes_json(tmp_path, capsys):
    target = tmp_path / "du_an_a"
    main(["init", str(target)])
    assert main(["scenarios", str(target)]) == 0
    items = json.loads((target / "scenarios.json").read_text(encoding="utf-8"))
    # speeds [0, 2.6] x 4 hướng: 1 calm + 4
    assert [i["scenario_id"] for i in items][0] == "calm"
    assert len(items) == 5
    assert set(items[0]) == {"scenario_id", "wind_speed_ms", "wind_from_deg", "transient"}


def test_missing_project_dir(tmp_path, capsys):
    assert main(["validate", str(tmp_path / "khong_co")]) == 2
    assert "không tìm thấy" in capsys.readouterr().err


def test_command_is_required():
    with pytest.raises(SystemExit):
        main([])
```

- [ ] **Step 3: Chạy test để thấy fail**

Run: `cd /d/CFD_Tool && python -m pytest tests/test_cli.py -v`
Expected: FAIL/ERROR `ModuleNotFoundError: odu_cfd.cli`

- [ ] **Step 4: Cài đặt `cli.py`**

`src/odu_cfd/cli.py`:

```python
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .climate import build_scenarios
from .errors import ConfigError
from .odu import get_model, load_odu_library
from .schema import load_project

TEMPLATE = Path(__file__).parent / "templates" / "project.yaml"
PROJECT_SUBDIRS = ("input", "cases", "results")


def _project_file(project_dir) -> Path:
    return Path(project_dir) / "project.yaml"


def _cmd_init(args) -> int:
    target = Path(args.project_dir)
    if _project_file(target).exists():
        raise ConfigError(f"dự án đã tồn tại: {_project_file(target)}")
    target.mkdir(parents=True, exist_ok=True)
    for sub in PROJECT_SUBDIRS:
        (target / sub).mkdir(exist_ok=True)
    text = TEMPLATE.read_text(encoding="utf-8").replace("__NAME__", target.name)
    _project_file(target).write_text(text, encoding="utf-8")
    print(f"Đã tạo dự án: {target}")
    return 0


def _cmd_validate(args) -> int:
    project = load_project(_project_file(args.project_dir))
    if args.library:
        get_model(load_odu_library(args.library), project.odu.model_id)
    scenarios = build_scenarios(project.climate.wind)
    print(
        f"OK: {project.name} - {len(scenarios)} kịch bản, "
        f"backend={project.compute.backend}, mức tin cậy={project.compute.confidence}"
    )
    return 0


def _cmd_scenarios(args) -> int:
    project = load_project(_project_file(args.project_dir))
    scenarios = build_scenarios(project.climate.wind)
    out = Path(args.project_dir) / "scenarios.json"
    out.write_text(
        json.dumps([asdict(s) for s in scenarios], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Đã ghi {len(scenarios)} kịch bản vào {out}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="odu-cfd", description="Đánh giá nhiệt độ ban công đặt dàn nóng bằng CFD")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="tạo dự án mới")
    p.add_argument("project_dir")
    p.set_defaults(func=_cmd_init)

    p = sub.add_parser("validate", help="kiểm tra project.yaml")
    p.add_argument("project_dir")
    p.add_argument("--library", help="thư mục thư viện ODU để kiểm tra model_id")
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("scenarios", help="sinh danh sách kịch bản")
    p.add_argument("project_dir")
    p.set_defaults(func=_cmd_scenarios)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2
```

- [ ] **Step 5: Chạy test để thấy pass**

Run: `cd /d/CFD_Tool && python -m pytest tests/test_cli.py -v`
Expected: 9 passed

- [ ] **Step 6: Điểm kiểm tra**

Run: `cd /d/CFD_Tool && git status --short`

---

### Task 8: Kiểm tra toàn bộ và chạy thử thực tế

**Files:** (không tạo file mới ngoài dự án thử bị xóa sau)

- [ ] **Step 1: Chạy toàn bộ test**

Run: `cd /d/CFD_Tool && python -m pytest -v`
Expected: tất cả PASS, không có test bị skip hoặc lỗi

- [ ] **Step 2: Chạy CLI thật qua `python -m`**

Run:
```bash
cd /d/CFD_Tool/src && python -m odu_cfd init /tmp/odu_smoke/da_thu && python -m odu_cfd validate /tmp/odu_smoke/da_thu && python -m odu_cfd scenarios /tmp/odu_smoke/da_thu && python -c "import json;print(len(json.load(open('/tmp/odu_smoke/da_thu/scenarios.json',encoding='utf-8'))),'kịch bản')"
```
Expected: `Đã tạo dự án: ...`, `OK: da_thu - 5 kịch bản, backend=local, mức tin cậy=screening`, `Đã ghi 5 kịch bản vào ...`, `5 kịch bản`

- [ ] **Step 3: Kiểm tra lỗi hiển thị đúng**

Run:
```bash
cd /d/CFD_Tool/src && python -m odu_cfd validate /tmp/odu_smoke/khong_co; echo "exit=$?"
```
Expected: dòng `Lỗi: không tìm thấy file cấu hình: ...` và `exit=2`

- [ ] **Step 4: Dọn dự án thử**

Run: `rm -rf /tmp/odu_smoke`

- [ ] **Step 5: Điểm kiểm tra cuối giai đoạn 1**

Run: `cd /d/CFD_Tool && git status --short`
Expected: các file của giai đoạn 1 chưa commit; báo người dùng và chờ yêu cầu commit/push.

---

## Self-Review (đối chiếu spec)

| Mục spec | Task |
|---|---|
| Giai đoạn 1: khung dự án, `project.yaml` + schema có kiểm tra | Task 1, 2, 7 |
| Thư viện ODU (nguồn bắt buộc, không số liệu bịa) | Task 4 |
| Vật lý ODU: Q_thải = (lạnh + nén) × tải; T_thổi theo T_hút thực | Task 3 |
| Khí hậu: profile gió ABL theo cấp địa hình | Task 5 |
| Bộ kịch bản; lặng gió dùng transient | Task 6 |
| CLI `odu-cfd` từng bước, lỗi báo rõ nguyên nhân | Task 7 |
| Offline, không phụ thuộc ngoài PyYAML | Toàn bộ (chạy được không cần mạng) |
| Mức tin cậy `screening`/`official` trong cấu hình | Task 2 |

Chưa thuộc giai đoạn 1 (có kế hoạch riêng sau): ingest CAD/PDF/Excel, dựng 3D, sinh case OpenFOAM, runner, post, viewer, validate, mitigate, giao diện, đóng gói.

Kiểm tra nhất quán tên: `parse_project`/`load_project`, `WindConfig` (Task 2) được dùng ở Task 6, 7; `OduModel`, `load_odu_library`, `get_model` (Task 3, 4) được dùng ở Task 7; `Scenario`/`build_scenarios` (Task 6) dùng ở Task 7; `ConfigError` (Task 1) dùng xuyên suốt. Không có placeholder.
