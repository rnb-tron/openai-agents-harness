from src.capabilities.model_routing import (
    ModelResilienceCapability,
    ModelRouterCapability,
    ResilienceConfig,
)
from src.capabilities.model_routing.router import ModelRouter


def test_model_router_marker_provides_model_selection():
    cap = ModelRouterCapability()

    assert cap.is_enabled() is True
    assert cap.manifest.name == "model_router"
    assert "model_selection" in cap.manifest.provides
    assert cap.manifest.depends_on == ()


def test_model_resilience_marker_depends_on_model_router():
    cap = ModelResilienceCapability(enabled=True)

    assert cap.is_enabled() is True
    assert cap.manifest.depends_on == ("model_router",)
    assert "model_resilience" in cap.manifest.provides


def test_model_router_only_creates_runner_when_resilience_enabled():
    plain = ModelRouter(resilience_config=ResilienceConfig(enabled=False))
    resilient = ModelRouter(resilience_config=ResilienceConfig(enabled=True))

    assert plain.last_metrics is None
    assert resilient.last_metrics is not None
