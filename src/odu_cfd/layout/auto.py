"""Sinh bố trí dàn nóng theo quy tắc: dựa lưng vào tường, xếp hàng/lưới trong ban công cho phép."""

import math

from shapely.geometry import LineString, Point
from shapely.geometry.polygon import orient

from ..errors import ConfigError
from .model import Layout, OduPlacement
from .validate import CONTAIN_TOL_M, odu_footprint

EPS = 1e-9
OPEN_D_M = 0.06  # bề dày tối đa của vách/dải mỏng bị loại khi 'mở' body
ADJ_TOL_M = 0.1  # cạnh ban công cách body < dung sai này coi là giáp tường
SLIDE_STEP_M = 0.05
ROUND_DIGITS = 6


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _norm_rotation(r):
    r = ((r + 180.0) % 360.0) - 180.0
    return 180.0 if r == -180.0 else r


def _round_rotation(r):
    r = round(_norm_rotation(r), ROUND_DIGITS) + 0.0
    return 180.0 if r == -180.0 else r


def _short_axis_dir(poly, body):
    """Hướng trục ngắn của hình chữ nhật bao nhỏ nhất, chiều ra xa tâm body (hoặc gốc tọa độ)."""
    pts = list(poly.minimum_rotated_rectangle.exterior.coords)
    e1 = (pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
    e2 = (pts[2][0] - pts[1][0], pts[2][1] - pts[1][1])
    e = e1 if math.hypot(*e1) <= math.hypot(*e2) else e2
    ln = math.hypot(*e)
    if ln < EPS:
        return (0.0, 1.0)
    n = (e[0] / ln, e[1] / ln)
    c = poly.centroid
    ref = body.centroid if body is not None and not body.is_empty else Point(0.0, 0.0)
    dot = (c.x - ref.x) * n[0] + (c.y - ref.y) * n[1]
    if abs(dot) < EPS:
        dot = n[0] if abs(n[0]) > EPS else n[1]
    return n if dot > 0 else (-n[0], -n[1])


def _open_body(body):
    """Bỏ vách/dải mỏng (< 2*OPEN_D_M) của body bằng mở hình thái, mitre để không bo góc."""
    if body is None or body.is_empty:
        return None
    opened = body.buffer(-OPEN_D_M, join_style=2).buffer(OPEN_D_M, join_style=2)
    return body if opened.is_empty else opened


def _out_direction(bal, body):
    """(n_out, warning|None). n_out = trung bình theo chiều dài pháp tuyến ngoài của các cạnh hở."""
    ob = _open_body(body)
    if ob is not None:
        near = ob.buffer(ADJ_TOL_M)
        pts = list(orient(bal.polygon, 1.0).exterior.coords)
        vx = vy = total = 0.0
        longest = (0.0, None)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            seg = LineString([(x0, y0), (x1, y1)])
            ln = seg.length
            if ln < 1e-9:
                continue
            free = seg.difference(near).length
            if free < 1e-6:
                continue
            nx, ny = (y1 - y0) / ln, -(x1 - x0) / ln  # pháp tuyến ngoài của chu vi ngược chiều kim đồng hồ
            vx += nx * free
            vy += ny * free
            total += free
            if free > longest[0] + 1e-12:
                longest = (free, (nx, ny))
        if total > 0.05:
            mag = math.hypot(vx, vy)
            if mag > 1e-3 * total:
                return (vx / mag, vy / mag), None
            return longest[1], None
    n = _short_axis_dir(bal.polygon, body)
    return n, f"ban công {bal.balcony_id}: không xác định được cạnh hở/tường gần nhất, dùng trục ngắn của ban công"


def _fit_row(poly_tol, k, n_center, t_mid, pitch_t, t_len, n_len, nx, ny, tx, ty, rot, w, d, taken):
    """Tìm vị trí vừa cho k dàn: ưu tiên sát lưng (n_center), trượt dọc t (tăng dần |độ lệch|); chỉ khi không
    được mới dịch dần ra ngoài theo n. Trả danh sách OduPlacement hoặc None. `taken`: footprint đã đặt."""
    t_steps = int(math.floor(t_len / 2.0 / SLIDE_STEP_M + EPS))
    t_offsets = [0.0]
    for i in range(1, t_steps + 1):
        t_offsets += [i * SLIDE_STEP_M, -i * SLIDE_STEP_M]
    n_steps = int(math.floor(n_len / SLIDE_STEP_M + EPS))
    for ni in range(n_steps + 1):
        nc = n_center + ni * SLIDE_STEP_M
        for off in t_offsets:
            cands, fps = [], []
            for ci in range(k):
                t_center = t_mid + off + (ci - (k - 1) / 2.0) * pitch_t
                c = OduPlacement("", nc * nx + t_center * tx, nc * ny + t_center * ty, rot, None, (w, d), None)
                cands.append(c)
                fps.append(odu_footprint(c, (w, d)))
            if all(poly_tol.contains(f) for f in fps) and not any(
                f.intersection(t).area > 1e-9 for f in fps for t in taken
            ):
                taken.extend(fps)
                return cands
    return None


def _check_params(floors, size, count, pattern, wall_gap_m, spacing_m, facing):
    if not isinstance(floors, (list, tuple)) or not floors or not all(
        isinstance(f, int) and not isinstance(f, bool) and f >= 1 for f in floors
    ):
        raise ConfigError(f"'floors' phải là danh sách mức tầng nguyên dương không rỗng, nhận được {floors!r}")
    if not (isinstance(size, (list, tuple)) and len(size) == 2 and all(_is_num(s) and s > 0 for s in size)):
        raise ConfigError(f"'size' phải là (rộng, sâu) dương hữu hạn, nhận được {size!r}")
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ConfigError(f"'count' phải là số nguyên >= 1, nhận được {count!r}")
    if pattern not in ("row", "grid"):
        raise ConfigError(f"'pattern' = {pattern!r}; chỉ nhận row, grid")
    for key, v in (("wall_gap_m", wall_gap_m), ("spacing_m", spacing_m)):
        if not _is_num(v) or v < 0:
            raise ConfigError(f"'{key}' phải là số hữu hạn >= 0, nhận được {v!r}")
    if facing != "outward" and not _is_num(facing):
        raise ConfigError(f"'facing' phải là 'outward' hoặc số độ, nhận được {facing!r}")


def auto_layout(
    balconies,
    body,
    *,
    name,
    floors,
    size,
    count=1,
    pattern="row",
    wall_gap_m=0.2,
    spacing_m=0.1,
    facing="outward",
    min_area_m2=0.0,
    only_ids=None,
    description="",
    size_explicit=False,
):
    _check_params(floors, size, count, pattern, wall_gap_m, spacing_m, facing)
    w, d = float(size[0]), float(size[1])
    warnings = []
    wanted = None if only_ids is None else list(only_ids)
    by_id = {b.balcony_id: b for b in balconies}
    if wanted is not None:
        for i in wanted:
            if i not in by_id:
                warnings.append(f"không có ban công {i}")
            elif not by_id[i].allowed:
                warnings.append(f"ban công {i} không cho phép đặt dàn nóng, bỏ qua")

    placements = []
    for bal in sorted(balconies, key=lambda b: b.balcony_id):
        if wanted is not None and bal.balcony_id not in wanted:
            continue
        if not bal.allowed or bal.polygon.area < min_area_m2:
            continue
        bid = bal.balcony_id
        n_out, warn = _out_direction(bal, body)
        if warn:
            warnings.append(warn)
        nx, ny = n_out
        tx, ty = -ny, nx
        verts = list(bal.polygon.exterior.coords)[:-1]
        ns = [x * nx + y * ny for x, y in verts]
        ts = [x * tx + y * ty for x, y in verts]
        n_min, n_max, t_min, t_max = min(ns), max(ns), min(ts), max(ts)
        n_len, t_len = n_max - n_min, t_max - t_min
        t_mid = (t_min + t_max) / 2.0

        blow = math.degrees(math.atan2(ny, nx)) if facing == "outward" else float(facing)
        rot = _norm_rotation(blow - 90.0)
        r = math.radians(rot)
        ux, uy = math.cos(r), math.sin(r)
        vx, vy = -math.sin(r), math.cos(r)
        hn = (w * abs(ux * nx + uy * ny) + d * abs(vx * nx + vy * ny)) / 2.0
        ht = (w * abs(ux * tx + uy * ty) + d * abs(vx * tx + vy * ty)) / 2.0
        pitch_t = 2 * ht + spacing_m
        pitch_n = 2 * hn + spacing_m
        cols = int(math.floor((t_len + spacing_m) / pitch_t + EPS))
        rows = int(math.floor((n_len - wall_gap_m + spacing_m) / pitch_n + EPS))
        if cols < 1 or rows < 1:
            warnings.append(f"ban công {bid}: không đủ chỗ đặt dàn nóng (chỉ đặt được 0/{count} dàn nóng)")
            continue
        if pattern == "row":
            capacity = min(count, cols)
            max_rows = 1
        else:
            capacity = min(count, cols * rows)
            max_rows = rows
        poly_tol = bal.polygon.buffer(CONTAIN_TOL_M)
        left = capacity
        taken = []
        placed = 0
        for ri in range(max_rows):
            if left <= 0:
                break
            n_center = n_min + wall_gap_m + hn + ri * pitch_n
            for kk in range(min(cols, left), 0, -1):
                got = _fit_row(poly_tol, kk, n_center, t_mid, pitch_t, t_len, n_len, nx, ny, tx, ty, rot, w, d, taken)
                if got:
                    placements.extend(got)
                    placed += kk
                    left -= kk
                    break
        if placed == 0:
            warnings.append(f"ban công {bid}: không đủ chỗ đặt dàn nóng (chỉ đặt được 0/{count} dàn nóng)")
        elif placed < count:
            warnings.append(f"ban công {bid}: chỉ đặt được {placed}/{count} dàn nóng")

    if not placements:
        warnings.append("CẢNH BÁO: không đặt được dàn nóng nào theo tham số đã chọn (layout rỗng)")
    width = max(2, len(str(len(placements))))
    out_size = (w, d) if size_explicit else None
    odus = tuple(
        OduPlacement(
            f"ODU-{i:0{width}d}",
            round(p.x, ROUND_DIGITS) + 0.0,
            round(p.y, ROUND_DIGITS) + 0.0,
            _round_rotation(p.rotation_deg),
            None,
            out_size,
            None,
        )
        for i, p in enumerate(placements, 1)
    )
    layout = Layout(name, description, "rule", tuple(floors), odus)
    return layout, warnings
