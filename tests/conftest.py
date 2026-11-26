import copy

import pytest

VALID = {
    "project": {"name": "demo", "description": "dự án thử"},
    "climate": {
        "design_temp_c": 36.8,
        "wind": {
            "ref_height_m": 10.0,
            "speeds_ms": [0, 2.6],
            "directions_deg": [0, 90, 180, 270],
            "terrain_category": "III",
        },
    },
    "building": {"num_floors": 19, "floor_height_m": 3.3},
    "odu": {
        "model_id": "test-odu",
        "load_fraction": 0.8,
        "simultaneity_fraction": 0.8,
        "louver_open_fraction": 0.8,
    },
    "compute": {"backend": "local", "cores": 4, "confidence": "screening"},
}


@pytest.fixture
def valid_dict():
    return copy.deepcopy(VALID)
