import os
import subprocess
import time
from pathlib import Path

import pytest

from odu_cfd.errors import IngestError
from odu_cfd.ingest import dwg


def _fake_dwg(path, magic=b"AC1032"):
    path.write_bytes(magic + b"\x00" * 100)
    return path


def test_locate_prefers_env(monkeypatch, tmp_path):
    exe = tmp_path / "dwg2dxf.exe"
    exe.write_text("")
    monkeypatch.setenv("ODU_CFD_DWG2DXF", str(exe))
    assert dwg.locate_dwg2dxf() == exe


def test_locate_env_pointing_nowhere_is_error(monkeypatch, tmp_path):
    monkeypatch.setenv("ODU_CFD_DWG2DXF", str(tmp_path / "none.exe"))
    with pytest.raises(IngestError, match="none.exe"):
        dwg.locate_dwg2dxf()


def test_locate_missing_asks_for_dxf(monkeypatch):
    monkeypatch.delenv("ODU_CFD_DWG2DXF", raising=False)
    monkeypatch.setattr(dwg, "_bundled_candidates", lambda: [])
    monkeypatch.setattr(dwg.shutil, "which", lambda name: None)
    with pytest.raises(IngestError, match="xuất DXF"):
        dwg.locate_dwg2dxf()


def test_rejects_file_that_is_not_dwg(tmp_path):
    f = tmp_path / "a.dwg"
    f.write_bytes(b"hello world")
    with pytest.raises(IngestError, match="không phải DWG"):
        dwg.convert_dwg_to_dxf(f, tmp_path / "a.dxf", exe=tmp_path / "x.exe")


def _stub(monkeypatch, code, write=True, stderr=b"boom", exc=None):
    """Thay subprocess.run: ghi file DXF vào đường dẫn sau -o (nếu write), trả CompletedProcess."""
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        if exc is not None:
            raise exc
        if write:
            open(cmd[cmd.index("-o") + 1], "w").write("0\nEOF\n")
        return subprocess.CompletedProcess(cmd, code, b"", stderr)

    monkeypatch.setattr(dwg.subprocess, "run", fake_run)
    return calls


def test_convert_runs_tool(monkeypatch, tmp_path):
    src, out = _fake_dwg(tmp_path / "a.dwg"), tmp_path / "a.converted.dxf"
    exe = tmp_path / "dwg2dxf.exe"
    calls = _stub(monkeypatch, 0)
    assert dwg.convert_dwg_to_dxf(src, out, exe=exe) == out
    cmd, kw = calls[0]
    assert cmd[0] == str(exe)
    assert out.read_text() == "0\nEOF\n" and not out.with_name(out.name + ".tmp").exists()
    assert "text" not in kw and "universal_newlines" not in kw  # đọc bytes, tự giải mã


def test_recoverable_exit_code_is_accepted(monkeypatch, tmp_path):
    src, out = _fake_dwg(tmp_path / "a.dwg"), tmp_path / "a.converted.dxf"
    _stub(monkeypatch, 1)
    assert dwg.convert_dwg_to_dxf(src, out, exe=tmp_path / "e.exe") == out


@pytest.mark.parametrize("code", [128, 3221225477, -11])
def test_critical_exit_code_fails_even_if_file_was_written(monkeypatch, tmp_path, code):
    src, out = _fake_dwg(tmp_path / "a.dwg"), tmp_path / "a.converted.dxf"
    _stub(monkeypatch, code, write=True)  # file dở dang vẫn được ghi, nhưng mã lỗi nặng phải thắng
    with pytest.raises(IngestError, match="lỗi nặng"):
        dwg.convert_dwg_to_dxf(src, out, exe=tmp_path / "e.exe")
    assert not out.exists() and not dwg._sidecar(out).exists()


def test_no_output_file_fails(monkeypatch, tmp_path):
    src, out = _fake_dwg(tmp_path / "a.dwg"), tmp_path / "a.converted.dxf"
    _stub(monkeypatch, 0, write=False)
    with pytest.raises(IngestError):
        dwg.convert_dwg_to_dxf(src, out, exe=tmp_path / "e.exe")


def test_error_message_contains_stderr_even_if_not_utf8(monkeypatch, tmp_path):
    src, out = _fake_dwg(tmp_path / "a.dwg"), tmp_path / "a.converted.dxf"
    _stub(monkeypatch, 1, write=False, stderr=b"File not found: t\xe1\xbb\xa7ng \xff\xfe")
    with pytest.raises(IngestError, match="File not found"):
        dwg.convert_dwg_to_dxf(src, out, exe=tmp_path / "e.exe")


def test_timeout_removes_stale_output(monkeypatch, tmp_path):
    src, out = _fake_dwg(tmp_path / "a.dwg"), tmp_path / "a.converted.dxf"
    out.write_text("cũ")
    dwg._sidecar(out).write_text("khác")
    _stub(monkeypatch, 0, exc=subprocess.TimeoutExpired("x", 900))
    with pytest.raises(IngestError, match="900"):
        dwg.convert_dwg_to_dxf(src, out, exe=tmp_path / "e.exe")
    assert not out.exists() and not dwg._sidecar(out).exists()


def test_output_is_reused_only_when_sha256_matches(monkeypatch, tmp_path):
    src, out = _fake_dwg(tmp_path / "a.dwg"), tmp_path / "a.converted.dxf"
    calls = _stub(monkeypatch, 0)
    dwg.convert_dwg_to_dxf(src, out, exe=tmp_path / "e.exe")
    assert len(calls) == 1
    dwg.convert_dwg_to_dxf(src, out, exe=tmp_path / "e.exe")
    assert len(calls) == 1  # cùng nội dung DWG: dùng lại
    # DWG mới nhưng mtime CŨ hơn kết quả: vẫn phải chuyển đổi lại
    src.write_bytes(b"AC1032" + b"" * 100)
    os.utime(src, (time.time() - 1000, time.time() - 1000))
    dwg.convert_dwg_to_dxf(src, out, exe=tmp_path / "e.exe")
    assert len(calls) == 2


def test_leftover_output_without_sidecar_is_not_trusted(monkeypatch, tmp_path):
    src, out = _fake_dwg(tmp_path / "a.dwg"), tmp_path / "a.converted.dxf"
    out.write_bytes(b"x" * 23)  # file dở dang của lần crash trước
    calls = _stub(monkeypatch, 0)
    dwg.convert_dwg_to_dxf(src, out, exe=tmp_path / "e.exe")
    assert len(calls) == 1 and out.read_text() == "0\nEOF\n"


def test_empty_cached_output_is_not_reused(monkeypatch, tmp_path):
    src, out = _fake_dwg(tmp_path / "a.dwg"), tmp_path / "a.converted.dxf"
    calls = _stub(monkeypatch, 0)
    dwg.convert_dwg_to_dxf(src, out, exe=tmp_path / "e.exe")
    out.write_bytes(b"")
    dwg.convert_dwg_to_dxf(src, out, exe=tmp_path / "e.exe")
    assert len(calls) == 2


def test_users_own_dxf_is_never_touched(monkeypatch, tmp_path):
    src = _fake_dwg(tmp_path / "a.dwg")
    mine = tmp_path / "a.dxf"
    mine.write_text("của người dùng")
    _stub(monkeypatch, 0)
    dwg.convert_dwg_to_dxf(src, tmp_path / "a.converted.dxf", exe=tmp_path / "e.exe")
    assert mine.read_text() == "của người dùng"


def test_tool_receives_ascii_paths_only(monkeypatch, tmp_path):
    folder = tmp_path / "thư mục"
    folder.mkdir()
    src, out = _fake_dwg(folder / "tầng điển hình.dwg"), folder / "tầng điển hình.converted.dxf"
    calls = _stub(monkeypatch, 0)
    dwg.convert_dwg_to_dxf(src, out, exe=tmp_path / "e.exe")
    assert all(a.isascii() for a in calls[0][0][1:])
    assert out.is_file()


def test_non_ascii_temp_dir_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(dwg.tempfile, "gettempdir", lambda: str(tmp_path / "Tạm"))
    pub = tmp_path / "public"
    monkeypatch.setenv("PUBLIC", str(pub))
    root = dwg._ascii_tmp_root()
    assert root.isascii() and (pub / "odu_cfd_tmp").is_dir()


_EXE = next((c for c in dwg._bundled_candidates() if c.is_file()), None)
_TITLE = Path(__file__).resolve().parents[1] / "scratch" / "dwgtest" / "title.dwg"


@pytest.mark.skipif(_EXE is None or not _TITLE.is_file(), reason="thiếu LibreDWG đi kèm hoặc title.dwg")
def test_real_libredwg_with_vietnamese_path(tmp_path):
    import shutil

    folder = tmp_path / "thư mục"
    folder.mkdir()
    src = folder / "tầng điển hình.dwg"
    shutil.copy(_TITLE, src)
    out = dwg.convert_dwg_to_dxf(src, folder / "tầng điển hình.converted.dxf", exe=_EXE)
    assert out.stat().st_size > 1000 and b"SECTION" in out.read_bytes()[:200]
