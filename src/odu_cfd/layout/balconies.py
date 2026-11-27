"""Ban công có id và file `<dự án>/balconies.yaml` (người dùng sửa cờ `allowed`)."""

import math
import re
from dataclasses import dataclass, replace
from pathlib import Path

import yaml
from shapely.geometry import Polygon

from ..errors import ConfigError
from .io import atomic_write_text
from .model import ID_RE

FILE_NAME = "balconies.yaml"
KEEP_DIST_M = 0.5

HEADER = """\
# Danh sách ban công do `odu-cfd geometry` trích từ bản vẽ (id đánh số theo tâm: y rồi x).
# Sửa cờ `allowed`: false nghĩa là kiến trúc KHÔNG cho phép đặt dàn nóng ở ban công đó.
# `note` là ghi chú tự do. Chạy lại `geometry` giữ nguyên allowed/note cho ban công có tâm cách < 0,5 m.
# polygon: các đỉnh (x, y) mét theo hệ tọa độ bản vẽ, không lặp lại điểm đầu ở cuối.
"""


@dataclass(frozen=True)
class BalconyInfo:
    balcony_id: str
    polygon: object  # shapely Polygon
    allowed: bool = True
    note: str = ""


def _key(poly):
    c = poly.centroid
    return (round(c.y, 3), round(c.x, 3), poly.bounds)


def number_balconies(polygons) -> list:
    ordered = sorted(polygons, key=_key)
    width = max(2, len(str(len(ordered))))
    return [(f"B{i:0{width}d}", p) for i, p in enumerate(ordered, 1)]


def _path(project_dir) -> Path:
    return Path(project_dir) / FILE_NAME


def _ring(poly):
    pts = list(poly.exterior.coords)[:-1]
    return [[float(x), float(y)] for x, y in pts]


def _to_text(infos) -> str:
    items = []
    for b in infos:
        c = b.polygon.centroid
        items.append(
            {
                "id": b.balcony_id,
                "centroid": [float(c.x), float(c.y)],
                "area_m2": float(b.polygon.area),
                "polygon": _ring(b.polygon),
                "allowed": bool(b.allowed),
                "note": b.note,
            }
        )
    body = yaml.safe_dump({"balconies": items}, allow_unicode=True, sort_keys=False, default_flow_style=None)
    return HEADER + body


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _parse_item(item, i, seen):
    where = f"balconies[{i}]"
    if not isinstance(item, dict):
        raise ConfigError(f"'{where}' phải là một nhóm khai báo")
    bid = item.get("id")
    if not isinstance(bid, str) or re.fullmatch(ID_RE, bid) is None:
        raise ConfigError(f"'{where}.id' = {bid!r} không hợp lệ")
    if bid in seen:
        raise ConfigError(f"'{where}.id' = {bid!r} bị trùng")
    seen.add(bid)
    pts = item.get("polygon")
    if (
        not isinstance(pts, list)
        or len(pts) < 3
        or not all(isinstance(p, (list, tuple)) and len(p) == 2 and all(_is_number(v) for v in p) for p in pts)
    ):
        raise ConfigError(f"'{where}.polygon' phải là danh sách từ 3 đỉnh [x, y] hữu hạn")
    poly = Polygon([(float(x), float(y)) for x, y in pts])
    if poly.is_empty or not poly.is_valid or poly.area <= 0:
        raise ConfigError(f"'{where}.polygon' không phải đa giác hợp lệ (tự cắt hoặc diện tích 0)")
    allowed = item.get("allowed", True)
    if not isinstance(allowed, bool):
        raise ConfigError(f"'{where}.allowed' phải là true/false, nhận được {allowed!r}")
    note = item.get("note", "")
    if note is None:
        note = ""
    if not isinstance(note, str):
        raise ConfigError(f"'{where}.note' phải là chuỗi, nhận được {note!r}")
    return BalconyInfo(bid, poly, allowed, note)


def read_balconies(project_dir) -> list:
    path = _path(project_dir)
    if not path.is_file():
        raise ConfigError(
            f"chưa có '{path}': chạy `odu-cfd geometry <dự án>` để trích ban công từ bản vẽ"
        )
    try:
        data = yaml.safe_load(path.read_bytes().decode("utf-8"))
    except UnicodeDecodeError:
        raise ConfigError(f"'{path}' không phải UTF-8") from None
    except yaml.YAMLError as e:
        raise ConfigError(f"'{path}' không phải YAML hợp lệ: {e}") from None
    try:
        if not isinstance(data, dict) or not isinstance(data.get("balconies"), list):
            raise ConfigError("thiếu danh sách 'balconies'")
        seen = set()
        return [_parse_item(it, i, seen) for i, it in enumerate(data["balconies"])]
    except ConfigError as e:
        raise ConfigError(f"'{path}': {e}") from None


def _carry_over(old, new_items):
    """Ghép một-một ban công mới với cũ theo tâm gần nhất (< 0,5 m), trả {id mới: BalconyInfo cũ}."""
    pairs = []
    for nid, npoly in new_items:
        nc = npoly.centroid
        for o in old:
            oc = o.polygon.centroid
            d = math.hypot(nc.x - oc.x, nc.y - oc.y)
            if d < KEEP_DIST_M:
                pairs.append((d, nid, o.balcony_id))
    pairs.sort()
    used_new, used_old, out = set(), set(), {}
    by_old = {o.balcony_id: o for o in old}
    for _, nid, oid in pairs:
        if nid in used_new or oid in used_old:
            continue
        used_new.add(nid)
        used_old.add(oid)
        out[nid] = by_old[oid]
    return out


def write_balconies(project_dir, polygons, warnings=None) -> list:
    for p in polygons:
        if p is None or p.is_empty or p.geom_type != "Polygon":
            raise ConfigError("ban công phải là đa giác (Polygon) không rỗng")
    path = _path(project_dir)
    old = read_balconies(project_dir) if path.exists() else []
    numbered = number_balconies(polygons)
    keep = _carry_over(old, numbered)
    if warnings is not None:
        kept_old = {o.balcony_id for o in keep.values()}
        for o in old:
            if o.balcony_id in kept_old or (o.allowed and not o.note):
                continue
            c = o.polygon.centroid
            what = " và ".join(x for x in ("cờ không cho phép (allowed: false)" if not o.allowed else "", "ghi chú" if o.note else "") if x)
            warnings.append(
                f"ban công cũ {o.balcony_id} (tâm {c.x:.3f}, {c.y:.3f}) không ghép được với ban công mới nào "
                f"(tâm lệch >= {KEEP_DIST_M} m): bị mất {what}"
                + (f" '{o.note}'" if o.note else "")
                + " (bị mất cờ không cho phép/ghi chú)"
            )
    infos = []
    for bid, poly in numbered:
        prev = keep.get(bid)
        infos.append(BalconyInfo(bid, poly, prev.allowed if prev else True, prev.note if prev else ""))
    atomic_write_text(path, _to_text(infos))
    return infos


def set_allowed(project_dir, allowed_ids=None, denied_ids=None, all_allowed=False) -> list:
    infos = read_balconies(project_dir)
    valid = [b.balcony_id for b in infos]
    allow = list(allowed_ids or [])
    deny = list(denied_ids or [])
    unknown = [i for i in allow + deny if i not in valid]
    if unknown:
        raise ConfigError(
            f"không có ban công {', '.join(map(str, unknown))}; id hợp lệ: {', '.join(valid) if valid else '(không có)'}"
        )
    both = sorted(set(allow) & set(deny))
    if both:
        raise ConfigError(f"ban công {', '.join(both)} vừa cho phép vừa cấm")
    out = []
    for b in infos:
        if all_allowed or b.balcony_id in allow:
            b = replace(b, allowed=True)
        if b.balcony_id in deny:
            b = replace(b, allowed=False)
        out.append(b)
    atomic_write_text(_path(project_dir), _to_text(out))
    return out
