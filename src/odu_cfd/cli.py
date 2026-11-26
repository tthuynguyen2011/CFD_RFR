import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .climate import build_scenarios
from .errors import ConfigError
from .odu import get_model, load_odu_library
from .schema import load_project

TEMPLATE = Path(__file__).parent / "templates" / "project.yaml"
PROJECT_SUBDIRS = ("input", "cases", "results", "report")


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


def _force_utf8_output() -> None:
    """Tránh UnicodeEncodeError khi stdout/stderr là cp1252 (pipe hoặc console cũ trên Windows)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv=None) -> int:
    _force_utf8_output()
    parser =argparse.ArgumentParser(prog="odu-cfd", description="Đánh giá nhiệt độ ban công đặt dàn nóng bằng CFD")
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

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2
