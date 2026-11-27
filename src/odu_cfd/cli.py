import argparse
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

from .climate import build_scenarios
from .errors import ConfigError, IngestError
from .odu import get_model, load_odu_library
from .schema import load_project

TEMPLATE = Path(__file__).parent / "templates" / "project.yaml"
PROJECT_SUBDIRS = ("input", "layouts", "cases", "results", "report")


def _project_file(project_dir) -> Path:
    return Path(project_dir) / "project.yaml"


def _cmd_init(args) -> int:
    target = Path(args.project_dir)
    if _project_file(target).exists():
        raise ConfigError(f"dự án đã tồn tại: {_project_file(target)}")
    name = target.resolve().name
    if not name:
        raise ConfigError(f"không xác định được tên dự án từ đường dẫn: {args.project_dir}")
    target.mkdir(parents=True, exist_ok=True)
    for sub in PROJECT_SUBDIRS:
        (target / sub).mkdir(exist_ok=True)
    text = TEMPLATE.read_text(encoding="utf-8").replace("__NAME__", json.dumps(name, ensure_ascii=False))
    _project_file(target).write_text(text, encoding="utf-8")
    print(f"Đã tạo dự án: {target}")
    return 0


def _cmd_validate(args) -> int:
    project = load_project(_project_file(args.project_dir))
    if args.library:
        get_model(load_odu_library(args.library), project.odu.model_id)
    scenarios = build_scenarios(project.climate.wind)
    print(
        f"OK: {project.name} - {len(scenarios)} kịch bản, "
        f"backend={project.compute.backend}, mức tin cậy={project.compute.confidence}"
    )
    return 0


def _cmd_scenarios(args) -> int:
    project = load_project(_project_file(args.project_dir))
    scenarios = build_scenarios(project.climate.wind)
    out = Path(args.project_dir) / "scenarios.json"
    out.write_text(
        json.dumps([asdict(s) for s in scenarios], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Đã ghi {len(scenarios)} kịch bản vào {out}")
    return 0


def _cmd_ingest(args) -> int:
    from .ingest.pipeline import confirm_ingest, run_ingest_full

    inp = Path(args.project_dir) / "input"
    if args.confirm:
        cfg = confirm_ingest(args.project_dir)
        print(f"Đã xác nhận nhận diện bản vẽ: {len(cfg.odus)} dàn nóng, {len(cfg.layers)} layer có vai trò.")
        return 0
    if not args.source:
        raise ConfigError("thiếu bản vẽ nguồn (.dwg/.dxf); hoặc dùng --confirm để xác nhận kết quả đã có")
    cfg, excluded, skipped = run_ingest_full(
        args.project_dir, args.source, view_id=args.view, units=args.units, force=args.force
    )
    if skipped:
        detail = ", ".join(f"{k}: {v}" for k, v in sorted(skipped.items()))
        print(f"Cảnh báo: bỏ qua đối tượng không đọc được/không hỗ trợ ({detail})")
    print(f"View đã chọn: {cfg.view_id} (đơn vị bản vẽ: {cfg.units})")
    print(f"Số layer có vai trò: {len(cfg.layers)}")
    print(f"Số dàn nóng: {len(cfg.odus)}; số bị loại theo diện tích chân đế: {len(excluded)}")
    print(f"Ảnh kiểm tra: {inp / 'overlay.png'}")
    print(f"Kết quả nhận diện: {inp / 'ingest.yaml'}")
    print(
        "Hãy xem ảnh, sửa file nếu cần, rồi chạy "
        f"`odu-cfd ingest {args.project_dir} --confirm`"
    )
    return 0


def _cmd_geometry(args) -> int:
    from .geometry.pipeline import run_geometry

    summary = run_geometry(args.project_dir, library_dir=args.library, layout_name=args.layout)
    out = Path(args.project_dir) / "input" / "geometry"
    if args.layout:
        out = out / "layouts" / args.layout
    parts = ", ".join(f"{g}: {p['regions']}" for g, p in summary["parts"].items())
    print(f"Đã dựng hình học {summary['num_floors']} tầng, cao {summary['height_m']:.1f} m ({parts})")
    print(f"Kết quả: {out}")
    layout_opt = f" --layout {args.layout}" if args.layout else ""
    print(f"Xem 3D: odu-cfd view {args.project_dir}{layout_opt}")
    return 0


def _cmd_view(args) -> int:
    geo = Path(args.project_dir) / "input" / "geometry"
    if args.layout:
        from .layout.io import layout_path

        layout_path(args.project_dir, args.layout)  # kiểm tra tên hợp lệ
        html = geo / "layouts" / args.layout / "viewer.html"
        hint = f"`odu-cfd geometry {args.project_dir} --layout {args.layout}`"
    else:
        html = geo / "viewer.html"
        hint = f"`odu-cfd geometry {args.project_dir}`"
    if not html.is_file():
        raise IngestError(f"chưa có {html}; hãy chạy {hint} trước")
    print(html)
    if not args.no_open:
        import webbrowser

        webbrowser.open(html.resolve().as_uri())
    return 0


# ---- phương án bố trí và ban công ----
def _csv(text) -> list:
    return [t.strip() for t in str(text).split(",") if t.strip()]


def _parse_size(text):
    try:
        vals = [float(v) for v in _csv(text)]
    except ValueError:
        vals = []
    if len(vals) != 2 or not all(math.isfinite(v) and 0 < v <= 5.0 for v in vals):
        raise ConfigError(f"--size = {text!r}: cần hai số dương không quá 5 m dạng RỘNG,SÂU (ví dụ 0.98,0.37)")
    return (vals[0], vals[1])


def _parse_facing(text):
    if text == "outward":
        return "outward"
    try:
        v = float(text)
    except ValueError:
        v = None
    if v is None or not math.isfinite(v):
        raise ConfigError(f"--facing = {text!r}: chỉ nhận 'outward' hoặc một góc theo độ")
    return v


def _check_floors_in_building(floors, num_floors):
    if max(floors) > num_floors:
        raise ConfigError(f"tầng {max(floors)} vượt số tầng của công trình ({num_floors} tầng)")


def _need_new(path, name, force):
    if path.exists() and not force:
        raise ConfigError(
            f"phương án '{name}' đã có ({path}); dùng --force để ghi đè (bản cũ được lưu thành {path.name}.bak)"
        )


def _print_table_balconies(infos) -> None:
    print(f"{'id':<6}{'diện tích m²':>14}  {'allowed':<8}tâm (x, y)")
    for b in infos:
        c = b.polygon.centroid
        print(
            f"{b.balcony_id:<6}{b.polygon.area:>14.1f}  {str(bool(b.allowed)).lower():<8}({c.x:.2f}, {c.y:.2f})"
            + (f"  # {b.note}" if b.note else "")
        )


def _cmd_layout_balconies(args) -> int:
    from .layout.balconies import read_balconies, set_allowed

    if args.allow or args.deny or args.allow_all:
        infos = set_allowed(
            args.project_dir,
            allowed_ids=_csv(args.allow) if args.allow else None,
            denied_ids=_csv(args.deny) if args.deny else None,
            all_allowed=args.allow_all,
        )
    else:
        infos = read_balconies(args.project_dir)
    _print_table_balconies(infos)
    return 0


def _default_size(project, library):
    from .geometry.pipeline import resolve_odu_specs
    from .layout.model import Layout, OduPlacement

    dummy = Layout("_", "", "manual", (1,), (OduPlacement("_", 0.0, 0.0, 0.0),))
    sizes, _, _, warnings = resolve_odu_specs(project, dummy, library)
    return sizes["_"], warnings


def _print_problems(problems) -> None:
    for p in problems:
        print(f"{'Lỗi' if p.level == 'error' else 'Cảnh báo'}: {p.message}")


def _cmd_layout_auto(args) -> int:
    from .geometry.pipeline import body_from_plan, read_plan_json
    from .layout.auto import auto_layout
    from .layout.balconies import read_balconies
    from .layout.io import layout_path, write_layout
    from .layout.model import parse_floors
    from .layout.validate import validate_layout

    plan = read_plan_json(args.project_dir)
    balconies = read_balconies(args.project_dir)
    path = layout_path(args.project_dir, args.name)
    _need_new(path, args.name, args.force)
    floors = parse_floors(args.floors)
    _check_floors_in_building(floors, plan["num_floors"])
    facing = _parse_facing(args.facing)
    only = _csv(args.balconies) if args.balconies else None
    if only is not None:
        valid = [b.balcony_id for b in balconies]
        unknown = [i for i in only if i not in valid]
        if unknown:
            raise ConfigError(f"không có ban công {', '.join(unknown)}; id hợp lệ: {', '.join(valid)}")
    project = load_project(_project_file(args.project_dir))
    if args.size:
        size, lib_warnings = _parse_size(args.size), []
    else:
        size, lib_warnings = _default_size(project, args.library)
    layout, warnings = auto_layout(
        balconies,
        body_from_plan(plan),
        name=args.name,
        floors=floors,
        size=size,
        count=args.count,
        pattern=args.pattern,
        wall_gap_m=args.wall_gap,
        spacing_m=args.spacing,
        facing=facing,
        min_area_m2=args.min_area,
        only_ids=only,
        description=args.description,
        size_explicit=bool(args.size),
    )
    if not layout.odus and not args.allow_empty:
        for w in lib_warnings + warnings:
            print(f"Cảnh báo: {w}", file=sys.stderr)
        raise ConfigError(
            "không đặt được dàn nóng nào (tổng số dàn nóng = 0), chưa ghi phương án; kiểm tra ban công được phép, "
            "--balconies, --min-area, --count hoặc dùng --allow-empty để vẫn ghi phương án trống"
        )
    problems = validate_layout(layout, balconies, plan["num_floors"], {o.odu_id: size for o in layout.odus})
    write_layout(path, layout)
    for w in lib_warnings + warnings + [p.message for p in problems]:
        print(f"Cảnh báo: {w}", file=sys.stderr)
    print(f"Đã ghi phương án '{args.name}': {len(layout.odus)} dàn nóng, tầng {args.floors} ({path})")
    print(f"Dựng 3D: odu-cfd geometry {args.project_dir} --layout {args.name}")
    return 0


def _cmd_layout_from_ingest(args) -> int:
    from .geometry.pipeline import read_plan_json
    from .ingest.config import read_ingest_config
    from .layout.balconies import read_balconies
    from .layout.from_ingest import layout_from_ingest
    from .layout.io import layout_path, write_layout
    from .layout.model import parse_floors

    plan = read_plan_json(args.project_dir)
    balconies = read_balconies(args.project_dir)
    path = layout_path(args.project_dir, args.name)
    _need_new(path, args.name, args.force)
    floors = parse_floors(args.floors)
    _check_floors_in_building(floors, plan["num_floors"])
    cfg = read_ingest_config(Path(args.project_dir) / "input" / "ingest.yaml")
    layout, warnings = layout_from_ingest(
        cfg.odus, balconies, name=args.name, floors=floors, description=args.description
    )
    write_layout(path, layout)
    if not cfg.odus:
        warnings.append("ingest.yaml không có dàn nóng nào nên phương án trống")
    for w in warnings:
        print(f"Cảnh báo: {w}", file=sys.stderr)
    print(f"Đã ghi phương án '{args.name}' từ bản vẽ: {len(layout.odus)} dàn nóng, tầng {args.floors} ({path})")
    return 0


def _read_named_layout(project_dir, name):
    from .layout.io import layout_path, list_layouts, read_layout

    path = layout_path(project_dir, name)
    if not path.is_file():
        existing = list_layouts(project_dir)
        raise ConfigError(
            f"không có phương án '{name}' ({path}); phương án hiện có: "
            f"{', '.join(existing) if existing else '(chưa có phương án nào)'}"
        )
    return read_layout(path)


def _print_balcony_usage(layout, balconies) -> None:
    from shapely.geometry import Point

    zones = [(b, b.polygon.buffer(0.01)) for b in balconies]
    counts = {b.balcony_id: 0 for b, _ in zones}
    for p in layout.odus:
        pt = Point(p.x, p.y)
        for b, z in zones:
            if z.covers(pt):
                counts[b.balcony_id] += 1
                break
    print("Số dàn nóng trên mỗi ban công:")
    for b, _ in zones:
        flag = "" if b.allowed else " (không cho phép)"
        print(f"  {b.balcony_id}: {counts[b.balcony_id]} dàn nóng{flag}")
    empty = [b.balcony_id for b, _ in zones if b.allowed and counts[b.balcony_id] == 0]
    if empty:
        print(f"Ban công cho phép nhưng không có dàn nóng nào: {', '.join(empty)}")
    else:
        print("Mọi ban công cho phép đều có dàn nóng.")


def _cmd_layout_validate(args) -> int:
    from .geometry.pipeline import read_plan_json, resolve_odu_specs
    from .layout.balconies import read_balconies
    from .layout.validate import validate_layout

    plan = read_plan_json(args.project_dir)
    balconies = read_balconies(args.project_dir)
    layout = _read_named_layout(args.project_dir, args.name)
    project = load_project(_project_file(args.project_dir))
    sizes, _, _, spec_warnings = resolve_odu_specs(project, layout, args.library)
    problems = validate_layout(layout, balconies, plan["num_floors"], sizes)
    for w in spec_warnings:
        print(f"Cảnh báo: {w}")
    _print_problems(problems)
    if args.verbose:
        _print_balcony_usage(layout, balconies)
    errors = [p for p in problems if p.level == "error"]
    if errors:
        print(f"Phương án '{layout.name}' có {len(errors)} lỗi.")
        return 2
    print(f"OK: phương án '{layout.name}' hợp lệ ({len(layout.odus)} dàn nóng)")
    return 0


def _cmd_layout_list(args) -> int:
    from .layout.io import layout_path, list_layouts, read_layout
    from .layout.model import format_floors

    names = list_layouts(args.project_dir)
    if not names:
        print(f"Chưa có phương án nào trong {Path(args.project_dir) / 'layouts'}")
        return 0
    print(f"{'tên':<24}{'nguồn':<12}{'dàn nóng':>9}  tầng")
    for n in names:
        try:
            lay = read_layout(layout_path(args.project_dir, n))
        except ConfigError as exc:
            print(f"{n:<24}(lỗi: {exc})")
            continue
        print(f"{n:<24}{lay.source:<12}{len(lay.odus):>9}  {format_floors(lay.floors)}")
    return 0


def _cmd_layout_new(args) -> int:
    from .geometry.pipeline import read_plan_json
    from .layout.io import layout_path, write_layout
    from .layout.model import Layout, parse_floors

    plan = read_plan_json(args.project_dir)
    path = layout_path(args.project_dir, args.name)
    _need_new(path, args.name, args.force)
    floors = parse_floors(args.floors)
    _check_floors_in_building(floors, plan["num_floors"])
    write_layout(path, Layout(args.name, args.description, "manual", floors, ()))
    print(
        f"Đã tạo phương án trống '{args.name}' ({path}); "
        f"chỉnh bằng `odu-cfd edit {args.project_dir} --layout {args.name}`"
    )
    return 0


def _cmd_edit(args) -> int:
    from .geometry.pipeline import read_plan_json
    from .layout.balconies import read_balconies
    from .layout.io import layout_path, list_layouts, write_layout
    from .layout.model import Layout, parse_floors

    plan = read_plan_json(args.project_dir)
    read_balconies(args.project_dir)
    name = args.layout
    if name is None:
        existing = list_layouts(args.project_dir)
        name = existing[0] if existing else "layout-1"
    path = layout_path(args.project_dir, name)
    if not path.is_file():
        if not args.floors:
            raise ConfigError(
                f"phương án '{name}' chưa có; thêm --floors \"4-19\" để tạo phương án trống rồi mở trình chỉnh"
            )
        floors = parse_floors(args.floors)
        _check_floors_in_building(floors, plan["num_floors"])
        write_layout(path, Layout(name, "", "manual", floors, ()))
        print(f"Đã tạo phương án trống '{name}' ({path})")

    from .layout.server import run_editor  # nhập lười: chỉ cần khi thật sự mở trình chỉnh

    return int(
        run_editor(
            args.project_dir,
            name,
            library_dir=args.library,
            port=args.port,
            open_browser=not args.no_open,
        )
    )


def _force_utf8_output() -> None:
    """Tránh UnicodeEncodeError khi stdout/stderr là cp1252 (pipe hoặc console cũ trên Windows)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv=None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(prog="odu-cfd", description="Đánh giá nhiệt độ ban công đặt dàn nóng bằng CFD")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="tạo dự án mới")
    p.add_argument("project_dir")
    p.set_defaults(func=_cmd_init)

    p = sub.add_parser("validate", help="kiểm tra project.yaml")
    p.add_argument("project_dir")
    p.add_argument("--library", help="thư mục thư viện ODU để kiểm tra model_id")
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("scenarios", help="sinh danh sách kịch bản")
    p.add_argument("project_dir")
    p.set_defaults(func=_cmd_scenarios)

    p = sub.add_parser("ingest", help="đọc bản vẽ DWG/DXF, nhận diện layer và dàn nóng")
    p.add_argument("project_dir")
    p.add_argument("source", nargs="?", help="file .dwg hoặc .dxf")
    p.add_argument("--view", help="chọn view (V1, V2, ...); mặc định V1")
    p.add_argument("--units", help="đơn vị bản vẽ nếu không khai báo: mm, cm, m, in, ft")
    p.add_argument("--confirm", action="store_true", help="xác nhận kết quả trong input/ingest.yaml")
    p.add_argument("--force", action="store_true", help="ghi đè ingest.yaml đã xác nhận (bản cũ lưu thành .bak)")
    p.set_defaults(func=_cmd_ingest)

    p = sub.add_parser("geometry", help="dựng hình học 3D (STL/GLB) từ kết quả ingest đã xác nhận")
    p.add_argument("project_dir")
    p.add_argument("--library", help="thư mục thư viện ODU để lấy kích thước và chiều cao dàn nóng")
    p.add_argument(
        "--layout",
        help="tên phương án bố trí dàn nóng (layouts/<tên>.yaml); bỏ trống thì dùng dàn nóng trong ingest.yaml",
    )
    p.set_defaults(func=_cmd_geometry)

    p = sub.add_parser("view", help="mở viewer 3D của hình học đã dựng")
    p.add_argument("project_dir")
    p.add_argument("--layout", help="xem hình học của phương án đã dựng bằng `geometry --layout`")
    p.add_argument("--no-open", action="store_true", help="chỉ in đường dẫn, không mở trình duyệt")
    p.set_defaults(func=_cmd_view)

    p = sub.add_parser("layout", help="phương án bố trí dàn nóng và ban công")
    lsub = p.add_subparsers(dest="layout_command", required=True)

    q = lsub.add_parser("balconies", help="xem hoặc đặt cờ allowed của ban công")
    q.add_argument("project_dir")
    q.add_argument("--allow", help="id ban công cho phép đặt dàn nóng, cách nhau bằng dấu phẩy (B01,B02)")
    q.add_argument("--deny", help="id ban công không cho phép đặt dàn nóng")
    q.add_argument("--allow-all", action="store_true", help="cho phép mọi ban công")
    q.set_defaults(func=_cmd_layout_balconies)

    q = lsub.add_parser("auto", help="sinh phương án theo quy tắc (dựa lưng vào tường, hàng hoặc lưới trong ban công)")
    q.add_argument("project_dir")
    q.add_argument("--name", required=True, help="tên phương án (chữ cái không dấu, số, _ . -)")
    q.add_argument("--floors", required=True, help='mức tầng áp dụng, ví dụ "4-19,22-23" (tầng 1 là tầng trệt)')
    q.add_argument("--count", type=int, default=1, help="số dàn nóng mỗi ban công (mặc định 1)")
    q.add_argument("--pattern", default="row", help="row (một hàng) hoặc grid (nhiều hàng từ tường ra)")
    q.add_argument(
        "--facing", default="outward", help="outward (thổi ra ngoài) hoặc góc độ ngược chiều kim đồng hồ từ +x"
    )
    q.add_argument("--wall-gap", type=float, default=0.2, help="khe hở tới tường, mét (mặc định 0.2)")
    q.add_argument("--spacing", type=float, default=0.1, help="khe hở giữa các dàn, mét (mặc định 0.1)")
    q.add_argument("--min-area", type=float, default=0.0, help="bỏ ban công nhỏ hơn diện tích này (m²)")
    q.add_argument("--balconies", help="chỉ các ban công này (B01,B02)")
    q.add_argument("--size", help="kích thước chân đế RỘNG,SÂU mét; mặc định theo thư viện rồi geometry.odu_default_*")
    q.add_argument("--library", help="thư mục thư viện ODU")
    q.add_argument("--description", default="", help="mô tả phương án")
    q.add_argument("--allow-empty", action="store_true", help="vẫn ghi phương án khi không đặt được dàn nóng nào")
    q.add_argument("--force", action="store_true", help="ghi đè phương án đã có (bản cũ lưu thành .bak)")
    q.set_defaults(func=_cmd_layout_auto)

    q = lsub.add_parser("from-ingest", help="chuyển dàn nóng nhận diện từ bản vẽ thành phương án")
    q.add_argument("project_dir")
    q.add_argument("--name", required=True)
    q.add_argument("--floors", required=True)
    q.add_argument("--description", default="")
    q.add_argument("--force", action="store_true")
    q.set_defaults(func=_cmd_layout_from_ingest)

    q = lsub.add_parser("validate", help="kiểm tra một phương án (mã 2 khi có lỗi)")
    q.add_argument("project_dir")
    q.add_argument("name")
    q.add_argument("--library", help="thư mục thư viện ODU (để lấy kích thước)")
    q.add_argument("--verbose", action="store_true", help="liệt kê số dàn nóng trên mỗi ban công và ban công trống")
    q.set_defaults(func=_cmd_layout_validate)

    q = lsub.add_parser("list", help="liệt kê các phương án")
    q.add_argument("project_dir")
    q.set_defaults(func=_cmd_layout_list)

    q = lsub.add_parser("new", help="tạo phương án trống (manual) để chỉnh bằng `edit`")
    q.add_argument("project_dir")
    q.add_argument("--name", required=True)
    q.add_argument("--floors", required=True)
    q.add_argument("--description", default="")
    q.add_argument("--force", action="store_true")
    q.set_defaults(func=_cmd_layout_new)

    p = sub.add_parser("edit", help="mở trình chỉnh 3D cục bộ để kéo và xoay dàn nóng")
    p.add_argument("project_dir")
    p.add_argument(
        "--layout", help="tên phương án; chưa có thì tạo trống (cần --floors); bỏ trống: phương án đầu tiên"
    )
    p.add_argument("--floors", help='mức tầng khi tạo phương án mới, ví dụ "4-19"')
    p.add_argument("--library", help="thư mục thư viện ODU")
    p.add_argument("--port", type=int, default=0, help="cổng cục bộ (0 = tự chọn)")
    p.add_argument("--no-open", action="store_true", help="không tự mở trình duyệt")
    p.set_defaults(func=_cmd_edit)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2
