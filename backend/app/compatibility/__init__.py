from app.compatibility.engine import (
    CompatibilityInput,
    CompatibilityResult,
    CategoryScore,
    compute_compatibility,
    compute_category,
)
from app.compatibility.explanation import (
    CompatibilityExplanation,
    ExplanationItem,
    build_explanation,
)
from app.compatibility.traits import goal_compatibility
from app.compatibility.weights import (
    DEFAULT_WEIGHT_CONFIG,
    DEFAULT_WEIGHTS,
    WeightConfig,
    build_weight_config,
)

__all__ = [
    "CompatibilityInput",
    "CompatibilityResult",
    "CategoryScore",
    "compute_compatibility",
    "compute_category",
    "CompatibilityExplanation",
    "ExplanationItem",
    "build_explanation",
    "goal_compatibility",
    "DEFAULT_WEIGHT_CONFIG",
    "DEFAULT_WEIGHTS",
    "WeightConfig",
    "build_weight_config",
]
