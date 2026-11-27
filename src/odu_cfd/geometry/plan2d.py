from dataclasses import dataclass

from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import polygonize, unary_union

from ..errors import IngestError

MIN_PIECE_AREA_M2 = 0.5
ENVELOPE_ROLES = ("wall_ext", "slab")


@dataclass(frozen=True)
class Plan2D:
    envelope: object  # shapely Polygon/MultiPolygon, đã lấp lỗ
    balconies: tuple  # tuple[Polygon]
    rails: tuple  # tuple[LineString]
    columns: tuple  # tuple[Polygon]
    filled_holes_m2: float = 0.0  # tổng diện tích lỗ (sân trong, giếng trời) bị lấp


def _center_in(prim, bbox):
    xs = [p[0] for p in prim.points]
    ys = [p[1] for p in prim.points]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    return bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]


def polygons_of(geom) -> list:
    """Mọi Polygon có diện tích dương trong một hình học bất kỳ (bỏ điểm, đường)."""
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom] if geom.area > 0 else []
    if hasattr(geom, "geoms"):
        out = []
        for g in geom.geoms:
            out.extend(polygons_of(g))
        return out
    return []


def _valid_polygons(points) -> list:
    if len(points) < 3:
        return []
    poly = Polygon(points)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return polygons_of(poly)


def _line_of(prim):
    pts = list(prim.points)
    if prim.closed and len(pts) > 2 and pts[0] != pts[-1]:
        pts.append(pts[0])
    if len(pts) < 2 or len(set(pts)) < 2:
        return None
    return LineString(pts)


def _envelope(prims, cfg):
    """Trả (đường bao đã lấp lỗ, tổng diện tích lỗ bị lấp)."""
    lines = []
    for p in prims:
        ln = _line_of(p)
        if ln is not None:
            lines.append(ln)
    pieces = []
    if lines:
        pieces = [g for g in polygonize(unary_union(lines)) if g.area >= MIN_PIECE_AREA_M2]
    if not pieces:
        used = sorted({p.layer for p in prims}) or sorted(
            n for n, r in cfg.layers.items() if r in ENVELOPE_ROLES
        )
        raise IngestError(
            "không dựng được đường bao tòa nhà từ các layer "
            f"{', '.join(used) if used else '(chưa có layer nào vai trò wall_ext hoặc slab)'}; "
            "hãy kiểm tra input/ingest.yaml: gán vai trò wall_ext hoặc slab cho layer chứa đường bao "
            "kín, và xem lại view_bbox"
        )
    merged = unary_union(pieces)
    filled = [Polygon(g.exterior) for g in polygons_of(merged)]  # lấp lỗ
    result = unary_union(filled)
    if not result.is_valid:
        result = result.buffer(0)
    holes = max(0.0, float(result.area) - float(merged.area))
    return result, holes


def extract_plan(drawing, cfg) -> Plan2D:
    inside = [p for p in drawing.primitives if p.kind == "path" and _center_in(p, cfg.view_bbox)]
    by_role = {}
    for p in inside:
        role = cfg.layers.get(p.layer)
        if role:
            by_role.setdefault(role, []).append(p)

    env_prims = [p for r in ENVELOPE_ROLES for p in by_role.get(r, [])]
    envelope, filled_holes = _envelope(env_prims, cfg)

    balconies = [g for p in by_role.get("balcony", []) if p.closed for g in _valid_polygons(p.points)]
    columns = [g for p in by_role.get("column", []) if p.closed for g in _valid_polygons(p.points)]
    rails = [ln for p in by_role.get("rail", []) for ln in [_line_of(p)] if ln is not None]
    return Plan2D(envelope, tuple(balconies), tuple(rails), tuple(columns), filled_holes)
