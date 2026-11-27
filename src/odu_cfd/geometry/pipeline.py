import json
import shutil
import sys
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

from ..errors import ConfigError, IngestError
from ..ingest.config import read_ingest_config, validate_for_geometry
from ..ingest.drawing import load_drawing
from ..ingest.odu_detect import OduInstance
from ..layout.balconies import write_balconies
from ..layout.io import layout_path, list_layouts, read_layout
from ..layout.model import front_angle_deg, format_floors
from ..layout.validate import validate_layout
from ..odu import get_model, load_odu_library
from ..schema import load_project
from ..viewer.geometry_viewer import write_viewer_html
from .build import build_building, open_body
from .export import check_region_names, write_glb, write_stl
from .plan2d import extract_plan, polygons_of

PLAN_JSON = "plan.json"
BASE_GLB = "base.glb"
BASE_GROUPS = ("building", "balcony", "rail")  # base.glb không có dàn nóng: dàn nóng là biến thiết kế


def _ring(ring) -> list:
    return [[float(x), float(y)] for x, y in list(ring.coords)[:-1]]  # không lặp điểm đầu ở cuối


def plan_to_dict(plan, building_cfg, geometry_cfg, balcony_infos) -> dict:
    """Nội dung plan.json (xem kế hoạch 2c, mục "Giao diện cố định")."""
    envelope = unary_union(polygons_of(plan.envelope)) if not plan.envelope.is_empty else plan.envelope
    polys = polygons_of(envelope)
    if polys:
        minx, miny, maxx, maxy = envelope.bounds
        origin = [(minx + maxx) / 2.0, (miny + maxy) / 2.0]
    else:
        origin = [0.0, 0.0]
    return {
        "version": 1,
        "units": "m",
        "origin_xy_m": [float(v) for v in origin],
        "num_floors": int(building_cfg.num_floors),
        "floor_height_m": float(building_cfg.floor_height_m),
        "slab_thickness_m": float(geometry_cfg.slab_thickness_m),
        "rail_height_m": float(geometry_cfg.rail_height_m),
        "envelope": [{"exterior": _ring(p.exterior), "holes": [_ring(h) for h in p.interiors]} for p in polys],
        "balconies": [
            {
                "id": b.balcony_id,
                "polygon": _ring(b.polygon.exterior),
                "area_m2": float(b.polygon.area),
                "allowed": bool(b.allowed),
            }
            for b in balcony_infos
        ],
        "rails": [[[float(x), float(y)] for x, y in ln.coords] for ln in plan.rails],
    }


def read_plan_json(project_dir) -> dict:
    path = Path(project_dir) / "input" / "geometry" / PLAN_JSON
    if not path.is_file():
        raise IngestError(f"chưa có {path}; hãy chạy `odu-cfd geometry {project_dir}` trước")
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IngestError(f"'{path}' hỏng ({exc}); hãy chạy lại `odu-cfd geometry {project_dir}`") from None
    if not isinstance(data, dict) or "envelope" not in data or "num_floors" not in data:
        raise IngestError(f"'{path}' sai định dạng; hãy chạy lại `odu-cfd geometry {project_dir}`")
    return data


def body_from_plan(plan_data):
    """Khối nhà = đường bao trừ hợp ban công (cùng cách `build_building` dựng khối nhà)."""
    env = unary_union([Polygon(e["exterior"], e.get("holes", [])) for e in plan_data["envelope"]])
    bals = [Polygon(b["polygon"]) for b in plan_data.get("balconies", [])]
    return open_body(env, unary_union(bals) if bals else None)[0]


def resolve_odu_specs(project, layout, library_dir=None):
    """Kích thước chân đế và chiều cao theo từng dàn nóng của một phương án.

    Trả (sizes {id: (w, d)}, size_sources {id: "layout"|"library"|"default"}, heights {id: m}, warnings).
    Kích thước: placement.size, ngược lại thư viện theo `placement.model_id or project.odu.model_id`, ngược lại
    mặc định `geometry.odu_default_width_m/depth_m`. Chiều cao: thư viện theo model, ngược lại
    `geometry.odu_default_height_m`."""
    geo = project.geometry
    warnings = []
    library = None
    if library_dir:
        try:
            library = load_odu_library(library_dir)
        except ConfigError as exc:
            warnings.append(f"không đọc được thư viện dàn nóng, dùng kích thước/chiều cao mặc định: {exc}")
    models = {}

    def model_of(model_id):
        if library is None:
            return None
        if model_id not in models:
            try:
                models[model_id] = get_model(library, model_id)
            except ConfigError as exc:
                models[model_id] = None
                warnings.append(f"không lấy được model '{model_id}' từ thư viện, dùng kích thước/chiều cao mặc định: {exc}")
        return models[model_id]

    sizes, sources, heights = {}, {}, {}
    for p in layout.odus:
        m = model_of(p.model_id or project.odu.model_id)
        if p.size is not None:
            sizes[p.odu_id], sources[p.odu_id] = (float(p.size[0]), float(p.size[1])), "layout"
        elif m is not None:
            sizes[p.odu_id], sources[p.odu_id] = (float(m.width_m), float(m.depth_m)), "library"
        else:
            sizes[p.odu_id] = (float(geo.odu_default_width_m), float(geo.odu_default_depth_m))
            sources[p.odu_id] = "default"
        heights[p.odu_id] = float(m.height_m) if m is not None else float(geo.odu_default_height_m)
    return sizes, sources, heights, warnings


def _load_layout_for_build(project_dir, layout_name):
    path = layout_path(project_dir, layout_name)
    if not path.is_file():
        existing = list_layouts(project_dir)
        raise IngestError(
            f"không có phương án '{layout_name}' ({path}); phương án hiện có: "
            f"{', '.join(existing) if existing else '(chưa có phương án nào)'}. "
            f"Tạo bằng `odu-cfd layout auto|from-ingest|new {project_dir} --name TÊN ...`"
        )
    return read_layout(path)


def _layout_info(layout, sizes, sources):
    odus = []
    for p in layout.odus:
        odus.append(
            {
                "id": p.odu_id,
                "x": p.x,
                "y": p.y,
                "rotation_deg": p.rotation_deg,
                "front_angle_deg": front_angle_deg(p),
                "model_id": p.model_id,
                "size": list(sizes[p.odu_id]),
                "size_source": sources[p.odu_id],
                "floors": list(layout.floors_of(p)),
            }
        )
    return {
        "name": layout.name,
        "source": layout.source,
        "floors": format_floors(layout.floors),
        "description": layout.description,
        "odus": odus,
    }


def _plan_balconies(project_dir, polygons, warnings):
    """Như write_balconies nhưng chưa ghi: trả (infos, nội dung balconies.yaml mới). Cảnh báo ghép lại thêm vào `warnings`."""
    import inspect
    import tempfile

    from ..layout.balconies import FILE_NAME

    real = Path(project_dir) / FILE_NAME
    with tempfile.TemporaryDirectory() as tmp:
        if real.is_file():
            shutil.copyfile(real, Path(tmp) / FILE_NAME)
        kwargs = {}
        if "warnings" in inspect.signature(write_balconies).parameters:
            kwargs["warnings"] = warnings
        infos = write_balconies(tmp, polygons, **kwargs)
        return infos, (Path(tmp) / FILE_NAME).read_text(encoding="utf-8")


def _commit_balconies(project_dir, text):
    from ..layout.balconies import FILE_NAME
    from ..layout.io import atomic_write_text

    atomic_write_text(Path(project_dir) / FILE_NAME, text)


def run_geometry(project_dir, library_dir=None, layout_name=None) -> dict:
    project_dir = Path(project_dir)
    project = load_project(project_dir / "project.yaml")
    cfg = read_ingest_config(project_dir / "input" / "ingest.yaml")
    if cfg.status != "confirmed":
        raise IngestError(
            f"kết quả nhận diện bản vẽ chưa xác nhận (status: {cfg.status}); "
            f"hãy xem input/overlay.png rồi chạy `odu-cfd ingest {project_dir} --confirm`"
        )

    validate_for_geometry(cfg)
    source = (project_dir / cfg.source_file).resolve()
    if not source.is_relative_to((project_dir / "input").resolve()):
        raise IngestError(f"'source_file' = {cfg.source_file!r} trỏ ra ngoài thư mục input/ của dự án")

    layout = _load_layout_for_build(project_dir, layout_name) if layout_name is not None else None

    drawing = load_drawing(source, units_override=cfg.units, layer_roles=cfg.layers)
    plan = extract_plan(drawing, cfg)
    extra_warnings = []
    # id ban công dùng chung với plan.json; tính trong thư mục tạm, chỉ ghi balconies.yaml thật khi mọi thứ thành công
    balcony_infos, balcony_text = _plan_balconies(project_dir, plan.balconies, extra_warnings)
    if layout is None:
        _commit_balconies(project_dir, balcony_text)

    odu_floors = odu_heights = odu_size_sources = None
    odu_height = size_override = None
    layout_info = None
    if layout is not None:
        sizes, sources, heights, spec_warnings = resolve_odu_specs(project, layout, library_dir)
        extra_warnings += spec_warnings
        problems = validate_layout(layout, balcony_infos, project.building.num_floors, sizes)
        errors = [p for p in problems if p.level == "error"]
        if errors:
            raise IngestError(
                f"phương án '{layout.name}' có {len(errors)} lỗi, chưa dựng 3D:\n"
                + "\n".join(f"  - {p.message}" for p in errors)
            )
        extra_warnings += [p.message for p in problems if p.level == "warning"]
        odus = [
            OduInstance(p.odu_id, "layout", "layout", (p.x, p.y), sizes[p.odu_id], p.rotation_deg) for p in layout.odus
        ]
        odu_floors = {p.odu_id: tuple(f - 1 for f in layout.floors_of(p)) for p in layout.odus}  # mức 1-based -> chỉ số
        odu_heights, odu_size_sources = heights, sources
        layout_info = _layout_info(layout, sizes, sources)
    else:
        odus = cfg.odus
        if not odus:
            extra_warnings.append(
                "chưa có dàn nóng: tạo phương án bằng `odu-cfd layout auto/from-ingest` hoặc `odu-cfd edit`"
            )
        if library_dir:
            try:
                model_lib = get_model(load_odu_library(library_dir), project.odu.model_id)
                odu_height = model_lib.height_m
                size_override = (model_lib.width_m, model_lib.depth_m)
            except ConfigError as exc:
                extra_warnings.append(f"không lấy được chiều cao dàn nóng từ thư viện, dùng mặc định: {exc}")

    model = build_building(
        plan,
        project.building,
        project.geometry,
        odus,
        odu_height_m=odu_height,
        odu_size_override=size_override,
        odu_floors=odu_floors,
        odu_heights=odu_heights,
        odu_size_sources=odu_size_sources,
    )

    for regions in model.groups.values():
        check_region_names(regions)  # lỗi trước khi ghi bất kỳ file nào
    _commit_balconies(project_dir, balcony_text)
    geo_dir = project_dir / "input" / "geometry"
    geo_dir.mkdir(parents=True, exist_ok=True)
    (geo_dir / PLAN_JSON).write_text(
        json.dumps(plan_to_dict(plan, project.building, project.geometry, balcony_infos), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_glb(geo_dir / BASE_GLB, {g: model.groups.get(g, {}) for g in BASE_GROUPS})

    out = geo_dir / "layouts" / layout.name if layout is not None else geo_dir
    out.mkdir(parents=True, exist_ok=True)
    for group in ("building", "balcony", "rail", "odu"):
        write_stl(out / f"{group}.stl", model.groups.get(group, {}))
    write_glb(out / "scene.glb", model.groups)

    summary = model.summary()
    summary["warnings"] = extra_warnings + summary["warnings"]
    info = dict(summary)
    info["source"] = cfg.source_file
    if layout is not None:
        info["layout"] = layout_info
    else:
        info["odus"] = [
            {
                "id": o.odu_id,
                "block": o.block,
                "layer": o.layer,
                "center": list(o.center),
                "size": list(model.odu_sizes[o.odu_id]["size"]),
                "size_source": model.odu_sizes[o.odu_id]["size_source"],
                "size_drawing": list(o.size),
                "rotation_deg": o.rotation_deg,
            }
            for o in cfg.odus
        ]
    (out / "geometry.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    title = f"{project.name} - {layout.name}" if layout is not None else project.name
    write_viewer_html(out / "scene.glb", out / "viewer.html", title)

    for w in summary["warnings"]:
        print(f"Cảnh báo: {w}", file=sys.stderr)
    return summary
