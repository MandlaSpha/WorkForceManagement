"""Features that can be switched off per deployment (requirement FEAT-01).

A feature is a sellable module. A customer who stops paying for one has it switched off with a
setting, not a code change. The rules:

- The switch is the `WFM_FEATURES` setting: `all`, `none`, or a comma-separated list of names.
- It is enforced by the API (a disabled feature's endpoints answer 403 `feature.disabled`, even
  for an admin). The UI hides what the API reports as disabled, but that is cosmetic.
- Every API operation must declare the feature it belongs to, or `CORE` (always on). The auth
  class refuses to be built without one, so a new endpoint cannot ship outside the switch.
- A mistake stops the application from starting: an unknown name, an empty value, or a feature
  switched on without the features it depends on. Silently enabling or disabling something is
  worse than not starting.
- Switching a feature off never deletes its data. Switching it back on restores it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import Final, Literal

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class Feature(StrEnum):
    TELEPHONY = "telephony"
    FORECASTING = "forecasting"
    SCHEDULING = "scheduling"
    PEOPLE = "people"
    OPTIMISATION = "optimisation"
    OVERTIME = "overtime"
    INSIGHT = "insight"
    CAPACITY = "capacity"
    INTRADAY = "intraday"
    SERVICE_DESK = "service_desk"


CORE: Final = "core"
"""Marks an operation that belongs to no sellable feature: sign-in, the audit log, configuration."""
FeatureOrCore = Feature | Literal["core"]


@dataclass(frozen=True, slots=True)
class FeatureInfo:
    label: str
    requires: tuple[Feature, ...] = ()


# Features are declared before their code exists so the licensing shape is settled early; a
# feature with no endpoints yet simply has nothing to switch off.
REGISTRY: Final[dict[Feature, FeatureInfo]] = {
    Feature.TELEPHONY: FeatureInfo("Call data: import and measured service figures"),
    Feature.FORECASTING: FeatureInfo(
        "Forecast and staffing requirement", requires=(Feature.TELEPHONY,)
    ),
    Feature.SCHEDULING: FeatureInfo(
        "Shift templates, roster and the planner", requires=(Feature.FORECASTING,)
    ),
    Feature.PEOPLE: FeatureInfo(
        "Leave, shift swaps, availability and employees", requires=(Feature.SCHEDULING,)
    ),
    Feature.OPTIMISATION: FeatureInfo(
        "Auto-scheduling and recommendations", requires=(Feature.SCHEDULING,)
    ),
    Feature.OVERTIME: FeatureInfo(
        "Overtime, standby and call-outs", requires=(Feature.SCHEDULING,)
    ),
    Feature.INSIGHT: FeatureInfo(
        "Analytics, reports and calibration", requires=(Feature.TELEPHONY,)
    ),
    Feature.CAPACITY: FeatureInfo("Capacity planning", requires=(Feature.FORECASTING,)),
    Feature.INTRADAY: FeatureInfo("Intraday monitoring", requires=(Feature.TELEPHONY,)),
    Feature.SERVICE_DESK: FeatureInfo("Tickets and emails alongside calls"),
}


class FeaturesMisconfiguredError(ImproperlyConfigured):
    """WFM_FEATURES cannot be understood. Raised at start-up so a typo never goes live."""


def parse_features(value: str) -> frozenset[Feature]:
    text = value.strip()
    if not text:
        raise FeaturesMisconfiguredError(
            "WFM_FEATURES is empty. Write 'all', 'none' or a comma-separated list of features."
        )
    if text.lower() == "all":
        return frozenset(Feature)
    if text.lower() == "none":
        return frozenset()

    names = [part.strip() for part in text.split(",") if part.strip()]
    unknown = [n for n in names if n not in {f.value for f in Feature}]
    if unknown:
        known = ", ".join(f.value for f in Feature)
        raise FeaturesMisconfiguredError(
            f"WFM_FEATURES names unknown feature(s): {', '.join(sorted(unknown))}. Known: {known}."
        )
    enabled = frozenset(Feature(n) for n in names)
    for feature in sorted(enabled):
        missing = [r for r in REGISTRY[feature].requires if r not in enabled]
        if missing:
            raise FeaturesMisconfiguredError(
                f"Feature '{feature.value}' needs {', '.join(m.value for m in missing)}, "
                "which is not enabled."
            )
    return enabled


@lru_cache(maxsize=16)
def _parse_cached(value: str) -> frozenset[Feature]:
    return parse_features(value)


def enabled_features() -> frozenset[Feature]:
    """The features switched on in this deployment. Read each time so a changed setting (and a
    test that overrides it) takes effect, but parsed once per distinct value."""
    return _parse_cached(settings.WFM_FEATURES)


def is_enabled(feature: FeatureOrCore) -> bool:
    return feature == CORE or Feature(feature) in enabled_features()
