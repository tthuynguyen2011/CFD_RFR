"""Dự án tổng hợp cho test trình chỉnh: dựng bằng đường dẫn thật, không phụ thuộc `run_geometry` mới."""

import atexit
import json
import shutil
import tempfile
from pathlib import Path

import yaml

from odu_cfd.cli import main
from odu_cfd.geometry.build import build_building
from odu_cfd.geometry.export import write_glb
from odu_cfd.geometry.plan2d import extract_plan
from odu_cfd.ingest.config import read_ingest_config
from odu_cfd.ingest.drawing import load_drawing
from odu_cfd.layout.balconies import write_balconies
from odu_cfd.layout.io import layout_path, write_layout
from odu_cfd.layout.model import Layout, OduPlacement
from odu_cfd.schema import load_project


def _ring(coords):
    return [[float(x), float(y)] for x, y in list(coords)[:-1]]


_TEMPLATES = {}  # (layout_name, odus, model_id) -> thư mục mẫu đã dựng một lần cho cả phiên test


def _cleanup_templates():
    for d in _TEMPLATES.values():
        shutil.rmtree(d, ignore_errors=True)


atexit.register(_cleanup_templates)


def make_editor_project(tmp_path, tower_dxf, layout_name="KT-v1", odus="b02", model_id=None):
    """Dựng dự án mẫu một lần (init/ingest/geometry mất ~0,5 s) rồi sao chép vào tmp_path/du-an cho mỗi test."""
    key = (layout_name, odus if isinstance(odus, str) else repr(tuple(odus)), model_id)
    if key not in _TEMPLATES:
        root = Path(tempfile.mkdtemp(prefix="odu-editor-tpl-"))
        _TEMPLATES[key] = root
        _build_editor_project(root, tower_dxf, layout_name, odus, model_id)
    dest = Path(tmp_path) / "du-an"
    shutil.copytree(_TEMPLATES[key] / "du-an", dest)
    return dest


def _build_editor_project(tmp_path, tower_dxf, layout_name="KT-v1", odus="b02", model_id=None):
    """init + ingest + confirm + plan2d + balconies.yaml + plan.json + base.glb (+ một phương án).

    odus: "b02" (hai dàn ở ban công B02), "none" (không ghi phương án), hoặc danh sách OduPlacement.
    """
    p = Path(tmp_path) / "du-an"
    assert main(["init", str(p)]) == 0
    assert main(["ingest", str(p), str(tower_dxf)]) == 0
    assert main(["ingest", str(p), "--confirm"]) == 0
    if model_id:
        data = yaml.safe_load((p / "project.yaml").read_text(encoding="utf-8"))
        data["odu"]["model_id"] = model_id
        (p / "project.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    project = load_project(p / "project.yaml")
    cfg = read_ingest_config(p / "input" / "ingest.yaml")
    drawing = load_drawing((p / cfg.source_file).resolve(), units_override=cfg.units, layer_roles=cfg.layers)
    plan = extract_plan(drawing, cfg)
    infos = write_balconies(p, plan.balconies)

    envelope = []
    geoms = list(plan.envelope.geoms) if hasattr(plan.envelope, "geoms") else [plan.envelope]
    for g in geoms:
        envelope.append({"exterior": _ring(g.exterior.coords), "holes": [_ring(h.coords) for h in g.interiors]})
    minx, miny, maxx, maxy = plan.envelope.bounds
    plan_json = {
        "version": 1,
        "units": "m",
        "origin_xy_m": [(minx + maxx) / 2.0, (miny + maxy) / 2.0],
        "num_floors": project.building.num_floors,
        "floor_height_m": project.building.floor_height_m,
        "slab_thickness_m": project.geometry.slab_thickness_m,
        "rail_height_m": project.geometry.rail_height_m,
        "envelope": envelope,
        "balconies": [
            {"id": b.balcony_id, "polygon": _ring(b.polygon.exterior.coords), "area_m2": b.polygon.area, "allowed": b.allowed}
            for b in infos
        ],
        "rails": [[[float(x), float(y)] for x, y in ln.coords] for ln in plan.rails],
    }
    geo = p / "input" / "geometry"
    geo.mkdir(parents=True, exist_ok=True)
    (geo / "plan.json").write_text(json.dumps(plan_json, ensure_ascii=False, indent=1), encoding="utf-8")
    model = build_building(plan, project.building, project.geometry, [])
    write_glb(geo / "base.glb", {g: r for g, r in model.groups.items() if g != "odu"})

    if odus == "b02":
        placements = (OduPlacement("ODU-01", 21.0, 1.0, 180.0), OduPlacement("ODU-02", 22.4, 1.0, 180.0))
    elif odus == "none":
        placements = None
    else:
        placements = tuple(odus)
    if placements is not None:
        lay = Layout(layout_name, "Phương án thử nghiệm tiếng Việt", "architect", tuple(range(4, 20)), placements)
        write_layout(layout_path(p, layout_name), lay)
    return p


def write_library(tmp_path, width=0.9, depth=0.35, height=0.8):
    lib = Path(tmp_path) / "lib"
    lib.mkdir(exist_ok=True)
    entry = {
        "model_id": "test-odu", "vendor": "TestCo", "width_m": width, "depth_m": depth, "height_m": height,
        "airflow_m3_h": 6000, "cooling_kw": 10, "compressor_kw": 3, "intake_limit_c": 46, "source": "dữ liệu thử",
    }
    (lib / "a.yaml").write_text(yaml.safe_dump({"models": [entry]}, allow_unicode=True), encoding="utf-8")
    return lib
