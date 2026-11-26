import math
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
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise ConfigError(f"{where}: '{key}' phải là số dương, nhận được {v!r}")
        values[key] = float(v)

    return OduModel(model_id=model_id, vendor=entry["vendor"], source=entry["source"], **values)


def load_odu_library(directory) -> dict:
    directory = Path(directory)
    if not directory.is_dir():
        raise ConfigError(f"không tìm thấy thư viện dàn nóng: {directory}")

    library = {}
    for path in sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")]):
        if path.name.startswith("_"):
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError as exc:
            raise ConfigError(f"file '{path}' phải được lưu bằng UTF-8: {exc}") from exc
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
