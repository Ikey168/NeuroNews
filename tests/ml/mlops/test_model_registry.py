import pytest
from neuronews.ml.registry.registry import ModelRegistry


def test_registry_register_and_retrieve():
    reg = ModelRegistry()
    rm1 = reg.register("classifier", {"w": 1})
    rm2 = reg.register("classifier", {"w": 2})
    assert rm1.version == 1
    assert rm2.version == 2
    latest = reg.latest("classifier")
    assert latest.version == 2
    fetched = reg.get("classifier", 1)
    assert fetched.obj["w"] == 1


def test_registry_stage_transition():
    reg = ModelRegistry()
    rm = reg.register("detector", object())
    reg.transition_stage("detector", rm.version, "Production")
    assert reg.get("detector", rm.version).stage == "Production"


def test_latest_missing():
    reg = ModelRegistry()
    with pytest.raises(KeyError):
        reg.latest("none")
