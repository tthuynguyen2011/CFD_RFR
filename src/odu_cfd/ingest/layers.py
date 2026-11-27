import re

ROLES = ("wall_ext", "wall_int", "balcony", "rail", "column", "slab", "odu")

_SPLIT = re.compile(r"[-_ .]+")

_RAIL = {"RAIL", "HANDRAIL", "HRAL", "RAILING", "BALUSTRADE"}
_BALCONY = {"BALC", "BALCONY"}
_ODU = {"EQPM", "ODU", "VRF", "OUTDOOR"}
_COLUMN = {"COL", "COLS", "COLUMN"}
_SLAB = {"FLOR", "FLOOR", "SLAB"}


def _role(name: str):
    tokens = [t for t in _SPLIT.split(name.upper()) if t]
    tset = set(tokens)
    if tset & _RAIL:
        return "rail"
    if tset & _BALCONY:
        return "balcony"
    if tset & _ODU or any(t.startswith("CONDENS") for t in tokens):
        return "odu"
    if tset & _COLUMN:
        return "column"
    if "WALL" in tset and "INT" in tset:
        return "wall_int"
    if "PARTITION" in tset:
        return "wall_int"
    if tokens == ["I", "WALL"]:
        return "wall_int"
    if "WALL" in tset and any(t.startswith("PAT") for t in tokens):
        return None
    if "WALL" in tset or "FACADE" in tset:
        return "wall_ext"
    if tset & _SLAB and not any(t.startswith("PATT") for t in tokens):
        return "slab"
    return None


def classify_layers(layer_names) -> dict:
    """Gán vai trò cho từng layer theo từ khóa trong tên; giữ mọi layer, None nếu không khớp."""
    return {name: _role(name) for name in layer_names}
