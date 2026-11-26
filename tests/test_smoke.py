import odu_cfd
from odu_cfd.errors import ConfigError


def test_version_is_string():
    assert isinstance(odu_cfd.__version__, str)


def test_config_error_is_exception():
    assert issubclass(ConfigError, Exception)
