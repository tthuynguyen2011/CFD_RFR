"""Chuyển các dàn nóng nhận diện từ bản vẽ (ingest.yaml) thành một phương án bố trí."""

import math
import re

from shapely.geometry import Point

from ..errors import ConfigError
from .model import ID_RE, Layout, OduPlacement
from .validate import CONTAIN_TOL_M


def _unique_id(raw, used, counter):
    if isinstance(raw, str) and re.fullmatch(ID_RE, raw) is not None and raw not in used:
        return raw, counter
    while True:
        counter += 1
        cand = f"ODU-{counter:02d}"
        if cand not in used:
            return cand, counter


def layout_from_ingest(odus, balconies, *, name, floors, description=""):
    if not isinstance(floors, (list, tuple)) or not floors or not all(
        isinstance(f, int) and not isinstance(f, bool) and f >= 1 for f in floors
    ):
        raise ConfigError(f"'floors' phải là danh sách mức tầng nguyên dương không rỗng, nhận được {floors!r}")
    warnings = []
    placements = []
    used = set()
    counter = 0
    bufs = [(b, b.polygon.buffer(CONTAIN_TOL_M)) for b in balconies]
    for inst in odus:
        oid, counter = _unique_id(inst.odu_id, used, counter)
        used.add(oid)
        x, y = inst.center
        rot = inst.rotation_deg
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (x, y, rot)):
            raise ConfigError(f"dàn nóng {inst.odu_id!r} có tâm hoặc góc xoay không hữu hạn")
        placements.append(OduPlacement(oid, float(x), float(y), float(rot), None, None, None))
        pt = Point(x, y)
        containing = [b for b, buf in bufs if buf.contains(pt)]
        if not containing:
            warnings.append(f"{oid} không rơi vào ban công nào")
        elif not any(b.allowed for b in containing):
            warnings.append(
                f"{oid} nằm trong ban công {sorted(b.balcony_id for b in containing)[0]} không cho phép đặt dàn nóng"
            )
    return Layout(name, description, "drawing", tuple(floors), tuple(placements)), warnings
