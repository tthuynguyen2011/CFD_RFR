from dataclasses import dataclass, field

from shapely.geometry import Point
from shapely.ops import unary_union

from ..errors import IngestError
from .mesh import box, box_polygon, bounds, extrude_polygon, is_closed, merge, volume
from .plan2d import polygons_of

MIN_ENVELOPE_AREA_M2 = 1.0
MIN_OVERLAP_M2 = 0.01
MAX_FILLED_HOLES_M2 = 5.0
OPEN_DIST_M = 0.06  # mở hình thái: bỏ chi tiết tường mỏng hơn 2 * OPEN_DIST_M = 12 cm
MIN_DROPPED_WARN_M2 = 0.01
MITRE_LIMIT = 20.0
COORDINATE_NOTE = (
    "Tọa độ giữ nguyên như bản vẽ (mét), không dời về gốc; origin_xy_m là tâm hộp bao đường bao "
    "để tham khảo khi cần đặt miền tính quanh tòa nhà."
)


@dataclass(frozen=True)
class BuildingModel:
    groups: dict  # {"building": {tên: Mesh}, "balcony": {...}, "rail": {...}, "odu": {...}}
    warnings: tuple
    num_floors: int = 0
    height_m: float = 0.0
    envelope_area_m2: float = 0.0
    odu_sizes: dict = field(default_factory=dict)  # {id: {"size": (w, d), "size_source": ...}}
    origin_xy_m: tuple = (0.0, 0.0)

    def summary(self) -> dict:
        all_meshes = [m for regions in self.groups.values() for m in regions.values() if len(m.faces)]
        box6 = [float(v) for v in bounds(merge(all_meshes))] if all_meshes else [0.0] * 6
        parts = {
            g: {
                "regions": len(regions),
                "volume_m3": float(sum(volume(m) for m in regions.values())),
                "closed": all(is_closed(m) for m in regions.values()),
            }
            for g, regions in self.groups.items()
        }
        return {
            "num_floors": self.num_floors,
            "height_m": self.height_m,
            "bbox": box6,
            "envelope_area_m2": self.envelope_area_m2,
            "origin_xy_m": [float(v) for v in self.origin_xy_m],
            "coordinate_note": COORDINATE_NOTE,
            "parts": parts,
            "warnings": list(self.warnings),
        }


def _clean(geom):
    if not geom.is_valid:
        geom = geom.buffer(0)
    return unary_union(polygons_of(geom))


def open_body(envelope, balcony_union):
    """Khối nhà = đường bao trừ ban công, rồi "mở" bỏ dải mỏng < 12 cm (do đường bao và ban công lệch vài mm).

    Mitre với giới hạn cao để không bo tròn góc lồi. Trả (khối nhà, diện tích đã bỏ m², số mảnh đã bỏ)."""
    body = envelope
    if balcony_union is not None and not balcony_union.is_empty:
        body = _clean(envelope.difference(balcony_union))
    if body.is_empty:
        return body, 0.0, 0
    d = OPEN_DIST_M
    opened = body.buffer(-d, join_style="mitre", mitre_limit=MITRE_LIMIT)
    opened = opened.buffer(d, join_style="mitre", mitre_limit=MITRE_LIMIT) if not opened.is_empty else opened
    opened = _clean(opened.intersection(body))  # mở chỉ được bỏ bớt, không thêm
    lost = [g for g in polygons_of(body.difference(opened)) if g.area > 1e-9]
    return opened, float(sum(g.area for g in lost)), len(lost)


def _odu_floor_indices(odu_id, odu_floors, floors):
    """Chỉ số tầng 0-based của một dàn nóng: mọi tầng nếu không khai báo, ngược lại kiểm tra phạm vi."""
    if odu_floors is None or odu_id not in odu_floors:
        return range(floors)
    idx = tuple(odu_floors[odu_id])
    bad = [i for i in idx if not isinstance(i, int) or isinstance(i, bool) or i < 0 or i >= floors]
    if bad:
        raise IngestError(
            f"{odu_id}: tầng (chỉ số 0-based) {', '.join(map(str, bad))} ngoài phạm vi 0..{floors - 1} "
            f"của công trình {floors} tầng"
        )
    return idx


def build_building(
    plan,
    building_cfg,
    geometry_cfg,
    odus,
    odu_height_m=None,
    odu_size_override=None,
    odu_floors=None,
    odu_heights=None,
    odu_size_sources=None,
) -> BuildingModel:
    """odu_floors: {id: tuple[int] chỉ số tầng 0-based} (None hoặc thiếu id = mọi tầng);
    odu_heights: {id: chiều cao m} (thiếu id = odu_height_m hoặc mặc định hình học);
    odu_size_sources: {id: nhãn nguồn kích thước} (thiếu id = "library"/"drawing" như cũ)."""
    floors = building_cfg.num_floors
    fh = building_cfg.floor_height_m
    height = floors * fh
    slab = geometry_cfg.slab_thickness_m
    warnings = []

    envelope = _clean(plan.envelope)
    env_area = float(envelope.area)
    if env_area < MIN_ENVELOPE_AREA_M2:
        warnings.append(f"đường bao tòa nhà quá nhỏ ({env_area:.2f} m²), hãy kiểm tra bản vẽ")
    if plan.filled_holes_m2 > MAX_FILLED_HOLES_M2:
        warnings.append(
            f"sân trong/giếng trời (tổng {plan.filled_holes_m2:.0f} m²) bị lấp thành khối đặc, "
            "ảnh hưởng CFD; hãy kiểm tra bản vẽ"
        )
    minx, miny, maxx, maxy = envelope.bounds if not envelope.is_empty else (0.0, 0.0, 0.0, 0.0)
    origin = ((minx + maxx) / 2.0, (miny + maxy) / 2.0)

    balcony_union = _clean(unary_union(list(plan.balconies))) if plan.balconies else None
    body, dropped, dropped_count = open_body(envelope, balcony_union)
    if dropped > MIN_DROPPED_WARN_M2:
        warnings.append(f"bỏ {dropped_count} mảnh tường mỏng < 12 cm, tổng {dropped:.2f} m²")
    if body.is_empty:
        raise IngestError("khối nhà rỗng sau khi trừ ban công; hãy kiểm tra layer ban công và đường bao")

    groups = {"building": {"building": extrude_polygon(body, 0.0, height)}, "balcony": {}, "rail": {}, "odu": {}}

    h_default = odu_height_m or geometry_cfg.odu_default_height_m
    heights = {o.odu_id: float((odu_heights or {}).get(o.odu_id, h_default)) for o in odus}
    for oid, h in heights.items():
        if slab + h >= fh:
            who = f"dàn nóng {oid}" if odu_heights is not None else "dàn nóng"
            raise IngestError(
                f"{who} cao {h:g} m cộng sàn {slab:g} m không thấp hơn chiều cao tầng {fh:g} m, "
                "sẽ xuyên sàn tầng trên; hãy kiểm tra chiều cao dàn nóng (thư viện hoặc geometry.odu_default_height_m) "
                "và building.floor_height_m"
            )

    rail_area = None
    if plan.rails:
        if slab + geometry_cfg.rail_height_m >= fh:
            raise IngestError(
                f"lan can cao {geometry_cfg.rail_height_m:g} m cộng sàn {slab:g} m không thấp hơn chiều cao tầng "
                f"{fh:g} m, sẽ xuyên sàn tầng trên; hãy kiểm tra geometry.rail_height_m và building.floor_height_m"
            )
        full = _clean(
            unary_union([ln.buffer(geometry_cfg.rail_thickness_m / 2.0, cap_style="flat") for ln in plan.rails])
        )
        rail_area = _clean(full.difference(body))  # trừ phần giao với khối nhà
        if rail_area.is_empty:
            warnings.append("lan can nằm trọn trong khối nhà nên không được dựng; hãy kiểm tra layer lan can")
            rail_area = None
    slab_meshes, rail_meshes = [], []
    for i in range(floors):
        z0 = i * fh
        if balcony_union is not None and not balcony_union.is_empty:
            slab_meshes.append(extrude_polygon(balcony_union, z0, z0 + slab))
        if rail_area is not None and not rail_area.is_empty:
            rail_meshes.append(extrude_polygon(rail_area, z0 + slab, z0 + slab + geometry_cfg.rail_height_m))
    if slab_meshes:
        groups["balcony"]["balcony_slabs"] = merge(slab_meshes)
    if rail_meshes:
        groups["rail"]["rails"] = merge(rail_meshes)

    odu_sizes = {}
    for o in odus:
        if odu_size_override is not None:
            size, source = (float(odu_size_override[0]), float(odu_size_override[1])), "library"
        else:
            size, source = (float(o.size[0]), float(o.size[1])), "drawing"
        if odu_size_sources is not None and o.odu_id in odu_size_sources:
            source = odu_size_sources[o.odu_id]
        odu_sizes[o.odu_id] = {"size": size, "size_source": source}
        pt = Point(o.center)
        if not any(b.covers(pt) for b in plan.balconies):
            warnings.append(f"{o.odu_id} nằm ngoài ban công")
        footprint = box_polygon(o.center[0], o.center[1], size[0], size[1], o.rotation_deg)
        hit = footprint.intersection(body).area
        if hit > MIN_OVERLAP_M2:
            warnings.append(f"{o.odu_id} giao khối nhà {hit:.2f} m², hãy kiểm tra vị trí hoặc kích thước dàn nóng")
        if rail_area is not None:
            hit = footprint.intersection(rail_area).area
            if hit > MIN_OVERLAP_M2:
                warnings.append(f"{o.odu_id} giao lan can {hit:.2f} m², hãy kiểm tra vị trí dàn nóng")
        for i in _odu_floor_indices(o.odu_id, odu_floors, floors):
            z0 = i * fh + slab
            groups["odu"][f"{o.odu_id}_f{i:02d}"] = box(
                o.center[0], o.center[1], size[0], size[1], o.rotation_deg, z0, z0 + heights[o.odu_id]
            )

    unclosed = [f"{g}/{name}" for g, regions in groups.items() for name, m in regions.items() if not is_closed(m)]
    if unclosed:
        shown = ", ".join(unclosed[:5]) + (" ..." if len(unclosed) > 5 else "")
        raise IngestError(
            f"lưới 3D không kín ở {len(unclosed)} vùng ({shown}); không ghi STL. "
            "Hãy kiểm tra đường bao, ban công và lan can trong bản vẽ"
        )

    return BuildingModel(groups, tuple(warnings), floors, height, env_area, odu_sizes, origin)
