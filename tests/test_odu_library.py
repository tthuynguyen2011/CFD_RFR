import pytest
import yaml

from odu_cfd.errors import ConfigError
from odu_cfd.odu import get_model, load_odu_library

ENTRY = {
    "model_id": "test-odu",
    "vendor": "TestCo",
    "width_m": 0.9,
    "depth_m": 0.35,
    "height_m": 0.8,
    "airflow_m3_h": 6000,
    "cooling_kw": 10.0,
    "compressor_kw": 3.0,
    "intake_limit_c": 46.0,
    "source": "dữ liệu thử",
}


def _write(path, entries):
    path.write_text(yaml.safe_dump({"models": entries}, allow_unicode=True), encoding="utf-8")


def test_loads_models_from_all_yaml_files(tmp_path):
    _write(tmp_path / "a.yaml", [ENTRY])
    other = dict(ENTRY, model_id="other-odu")
    _write(tmp_path / "b.yaml", [other])
    lib = load_odu_library(tmp_path)
    assert set(lib) == {"test-odu", "other-odu"}
    assert lib["test-odu"].airflow_m3_h == 6000.0


def test_underscore_files_are_ignored(tmp_path):
    _write(tmp_path / "_template.yaml", [ENTRY])
    assert load_odu_library(tmp_path) == {}


def test_missing_directory_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="thư viện"):
        load_odu_library(tmp_path / "khong_co")


def test_source_is_mandatory(tmp_path):
    bad = dict(ENTRY)
    bad["source"] = ""
    _write(tmp_path / "a.yaml", [bad])
    with pytest.raises(ConfigError, match="source"):
        load_odu_library(tmp_path)


def test_missing_field_names_the_model(tmp_path):
    bad = dict(ENTRY)
    del bad["airflow_m3_h"]
    _write(tmp_path / "a.yaml", [bad])
    with pytest.raises(ConfigError, match="airflow_m3_h"):
        load_odu_library(tmp_path)


def test_non_positive_value_rejected(tmp_path):
    bad = dict(ENTRY, width_m=0)
    _write(tmp_path / "a.yaml", [bad])
    with pytest.raises(ConfigError, match="width_m"):
        load_odu_library(tmp_path)


def test_duplicate_model_id_rejected(tmp_path):
    _write(tmp_path / "a.yaml", [ENTRY, ENTRY])
    with pytest.raises(ConfigError, match="trùng"):
        load_odu_library(tmp_path)


def test_get_model_unknown_lists_available(tmp_path):
    _write(tmp_path / "a.yaml", [ENTRY])
    lib = load_odu_library(tmp_path)
    assert get_model(lib, "test-odu").vendor == "TestCo"
    with pytest.raises(ConfigError, match="test-odu"):
        get_model(lib, "khong-co")


@pytest.mark.parametrize("key,val", [("width_m", float("nan")), ("airflow_m3_h", float("inf"))])
def test_non_finite_numeric_rejected(tmp_path, key, val):
    _write(tmp_path / "a.yaml", [dict(ENTRY, **{key: val})])
    with pytest.raises(ConfigError, match=key):
        load_odu_library(tmp_path)


def test_yml_extension_loaded(tmp_path):
    _write(tmp_path / "a.yml", [ENTRY])
    assert set(load_odu_library(tmp_path)) == {"test-odu"}


def test_underscore_yml_ignored(tmp_path):
    _write(tmp_path / "_t.yml", [ENTRY])
    assert load_odu_library(tmp_path) == {}


def test_non_utf8_library_file(tmp_path):
    (tmp_path / "a.yaml").write_bytes("models: []\n# Đà\n".encode("cp1258"))
    with pytest.raises(ConfigError, match="UTF-8"):
        load_odu_library(tmp_path)
