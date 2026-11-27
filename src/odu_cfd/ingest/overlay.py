import math
from pathlib import Path

from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.patches import Rectangle

ROLE_COLORS = {
    "wall_ext": "#1f2937",
    "wall_int": "#9ca3af",
    "balcony": "#2563eb",
    "rail": "#16a34a",
    "column": "#7c3aed",
    "slab": "#0891b2",
    "odu": "#d97706",
}
CONTEXT_COLOR = "#d1d5db"
ODU_COLOR = "#dc2626"


def _box_corners(odu):
    cx, cy = odu.center
    w, d = odu.size
    a = math.radians(odu.rotation_deg)
    ca, sa = math.cos(a), math.sin(a)
    out = []
    for lx, ly in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)):
        out.append((cx + lx * ca - ly * sa, cy + lx * sa + ly * ca))
    return out


def _segments(prim):
    pts = prim.points
    segs = list(zip(pts[:-1], pts[1:]))
    if prim.closed and len(pts) > 2:
        segs.append((pts[-1], pts[0]))
    return segs


def render_overlay(drawing, cfg, png_path, excluded=()) -> None:
    """Vẽ view đã chọn: đường theo màu vai trò layer, dàn nóng hộp đỏ có nhãn, khung view."""
    minx, miny, maxx, maxy = cfg.view_bbox
    w, h = maxx - minx, maxy - miny
    width_in = 12.0
    height_in = max(4.0, min(20.0, width_in * h / w)) if w > 0 else 8.0

    fig = Figure(figsize=(width_in, height_in), dpi=150)
    ax = fig.add_subplot(111)

    by_color = {}
    for prim in drawing.primitives:
        xs = [p[0] for p in prim.points]
        ys = [p[1] for p in prim.points]
        if max(xs) < minx or min(xs) > maxx or max(ys) < miny or min(ys) > maxy:
            continue
        role = cfg.layers.get(prim.layer)
        color = ROLE_COLORS.get(role, CONTEXT_COLOR)
        by_color.setdefault((role, color), []).extend(_segments(prim))
    # vẽ phần chưa phân vai trước (nền), vai trò đè lên sau
    for (role, color), segs in sorted(by_color.items(), key=lambda kv: kv[0][0] is not None):
        ax.add_collection(
            LineCollection(segs, colors=color, linewidths=0.9 if role else 0.4, label=role or "chưa phân vai")
        )

    for o in excluded:
        ax.add_patch(MplPolygon(_box_corners(o), closed=True, fill=False, ec="#f59e0b", ls="--", lw=1.2))
        ax.annotate(o.odu_id, o.center, color="#b45309", fontsize=7, ha="center", va="bottom",
                    xytext=(0, 3), textcoords="offset points")
    for o in cfg.odus:
        ax.add_patch(MplPolygon(_box_corners(o), closed=True, fc="#fecaca", ec=ODU_COLOR, lw=1.5))
        ax.annotate(o.odu_id, o.center, color=ODU_COLOR, fontsize=7, ha="center", va="bottom",
                    xytext=(0, 3), textcoords="offset points")

    ax.add_patch(Rectangle((minx, miny), w, h, fill=False, ec="#111827", ls=":", lw=1.0))
    pad = 0.03 * max(w, h)
    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad, maxy + pad)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title(
        f"{cfg.view_id}: {len(cfg.odus)} dàn nóng (đỏ), {len(excluded)} bị loại (cam nét đứt)",
        fontsize=10,
    )
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(handles, labels, loc="upper right", fontsize=7, framealpha=0.85)
    fig.tight_layout()
    Path(png_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(png_path), format="png")
