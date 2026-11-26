import pytest

from odu_cfd.odu.model import OduModel

MODEL = OduModel(
    model_id="test-odu",
    vendor="TestCo",
    width_m=0.9,
    depth_m=0.35,
    height_m=0.8,
    airflow_m3_h=6000.0,
    cooling_kw=10.0,
    compressor_kw=3.0,
    intake_limit_c=46.0,
    source="dữ liệu thử trong tests",
)


def test_heat_rejection_is_cooling_plus_compressor_times_load():
    assert MODEL.heat_rejection_kw(1.0) == pytest.approx(13.0)
    assert MODEL.heat_rejection_kw(0.8) == pytest.approx(10.4)


def test_discharge_temperature_matches_energy_balance():
    # rho = 101325/(287.05*308.15) = 1.1455 kg/m3; mdot = rho*6000/3600 = 1.9092 kg/s
    # dT = 13000 W / (1.9092 kg/s * 1005 J/kg/K) = 6.775 K
    t_out = MODEL.discharge_temperature_c(35.0, 1.0)
    assert t_out == pytest.approx(35.0 + 6.775, abs=0.02)


def test_hotter_intake_gives_lower_dT_because_air_is_thinner():
    dt_cool = MODEL.discharge_temperature_c(25.0, 1.0) - 25.0
    dt_hot = MODEL.discharge_temperature_c(45.0, 1.0) - 45.0
    assert dt_hot > dt_cool


def test_zero_load_gives_no_temperature_rise():
    assert MODEL.discharge_temperature_c(35.0, 0.0) == pytest.approx(35.0)


def test_load_outside_range_rejected():
    with pytest.raises(ValueError):
        MODEL.heat_rejection_kw(1.5)
    with pytest.raises(ValueError):
        MODEL.heat_rejection_kw(-0.1)


@pytest.mark.parametrize("load", [float("nan"), float("inf"), True])
def test_heat_rejection_rejects_bad_load(load):
    with pytest.raises(ValueError):
        MODEL.heat_rejection_kw(load)


@pytest.mark.parametrize("intake", [float("nan"), float("inf"), -273.15, -300.0])
def test_discharge_rejects_bad_intake(intake):
    with pytest.raises(ValueError):
        MODEL.discharge_temperature_c(intake, 0.5)
