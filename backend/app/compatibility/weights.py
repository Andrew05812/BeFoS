from __future__ import annotations

from dataclasses import dataclass

from app.compatibility.traits import ALL_CATEGORIES

# Default weights (sum == 1.0). Changeable without touching the engine.
DEFAULT_WEIGHTS: dict[str, float] = {
    "values": 0.25,
    "personality": 0.15,
    "interests": 0.15,
    "communication": 0.15,
    "lifestyle": 0.15,
    "leisure": 0.10,
    "goals": 0.05,
}

ENGINE_VERSION = 1


@dataclass(frozen=True)
class WeightConfig:
    weights: dict[str, float]
    version: int = ENGINE_VERSION

    def weight(self, category: str) -> float:
        return self.weights.get(category, 0.0)

    def validate(self) -> None:
        categories = {c.key for c in ALL_CATEGORIES}
        missing = categories - self.weights.keys()
        if missing:
            raise ValueError(f"Missing weights for categories: {sorted(missing)}")
        total = round(sum(self.weights.values()), 6)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Compatibility weights must sum to 1.0, got {total}")


DEFAULT_WEIGHT_CONFIG = WeightConfig(weights=dict(DEFAULT_WEIGHTS))
DEFAULT_WEIGHT_CONFIG.validate()


def build_weight_config(overrides: dict[str, float] | None = None) -> WeightConfig:
    """Build a validated WeightConfig from optional overrides."""
    weights = dict(DEFAULT_WEIGHTS)
    if overrides:
        weights.update({k: float(v) for k, v in overrides.items()})
    config = WeightConfig(weights=weights)
    config.validate()
    return config
