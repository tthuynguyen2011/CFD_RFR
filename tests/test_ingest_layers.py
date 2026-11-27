import pytest

from odu_cfd.ingest.layers import ROLES, classify_layers

CASES = {
    "A-WALL": "wall_ext",
    "A-200-M_WALL_EXT": "wall_ext",
    "A-214-M_CURT_WALL": "wall_ext",
    "A-200-M_WALL_INT": "wall_int",
    "I-WALL": "wall_int",
    "A-200-M_WALL_PAT": None,
    "A-FLOR-HRAL": "rail",
    "A-HANDRAIL": "rail",
    "A-340-M_RAILING": "rail",
    "A-BALC": "balcony",
    "S-COLS": "column",
    "A-COLS": "column",
    "M-EQPM": "odu",
    "RFR-MVAC-ODU": "odu",
    "A-230-M_FLOOR": "slab",
    "A-FLOR": "slab",
    "A-FLOR-PATT": None,
    "A-215-M_CURT_PANEL": None,
    "A-242-M_STAIR": None,
    "A-010-D_DIM": None,
    "RFR-MVAC-PAD": None,
    "0": None,
}


@pytest.mark.parametrize("name,role", CASES.items())
def test_known_layers(name, role):
    assert classify_layers([name])[name] == role


def test_case_insensitive_and_keeps_all_layers():
    out = classify_layers(["a-wall", "Zzz"])
    assert out == {"a-wall": "wall_ext", "Zzz": None}


def test_roles_are_declared():
    assert set(CASES.values()) - {None} <= set(ROLES)
