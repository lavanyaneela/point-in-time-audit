"""Frozen configuration objects, because the experiment harness is measurement
code and anything that keys a cache or a filename must hash the whole config,
never a hand-picked subset of its fields.

Every knob that changes a published number lives here. The generator config is
serialised into the fixture manifest, so a fixture regenerated under a drifted
config refuses to pass the manifest check instead of silently producing
different numbers under the same name.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class DelayConfig:
    """Arrival delay distributions, in days, one per event type.

    Each entry is (median_days, sigma) of a lognormal. The incident delay is
    the knob E4 sweeps, because incidents are the facts that are true before
    prediction time and recorded after it.
    """

    activity_median: float = 0.1
    activity_sigma: float = 0.6
    assessment_median: float = 1.5
    assessment_sigma: float = 0.8
    incident_median: float = 30.0
    incident_sigma: float = 1.0
    status_median: float = 5.0
    status_sigma: float = 1.2


@dataclass(frozen=True)
class GeneratorConfig:
    """The committed world. Changing any field changes the fixture identity."""

    seed: int = 7
    n_entities: int = 3000
    horizon_days: float = 120.0
    prediction_window: tuple[float, float] = (60.0, 90.0)
    n_partitions: int = 8

    # Latent risk drives everything observable.
    activity_rate_base: float = 3.2
    activity_rate_risk: float = -0.15
    assessment_every_days: float = 10.0
    assessment_noise: float = 0.7
    incident_rate_base: float = -0.3
    incident_rate_risk: float = 1.2
    incident_fact_before: float = 25.0
    incident_fact_after: float = 15.0

    # Label model: risk plus the incident count inside the feature window.
    label_risk_weight: float = 0.5
    label_incident_weight: float = 1.4
    label_bias: float = -3.2
    feature_window_days: float = 90.0

    # Post-outcome contamination of slowly changing dimensions. Corrections
    # fire for a minority of positives and, wrongly, for a few negatives, so
    # the corrected status is evidence about the outcome rather than a copy
    # of it. The first committed world set the positive rate at 0.7 with no
    # false corrections, and E2 convicted it: one feature carried the whole
    # gap, which is a planted answer key, not a leak.
    post_assessment_label_shift: float = 1.2
    correction_prob_positive: float = 0.35
    correction_prob_negative: float = 0.04
    correction_backdate_max: float = 10.0

    delays: DelayConfig = field(default_factory=DelayConfig)

    def config_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# The three visibility policies a pipeline can apply when it reads the log.
# "latest" is a join on entity id alone. "fact_only" filters on the business
# timestamp, which is the version that passes code review. "point_in_time"
# requires both timestamps to precede the prediction instant, which is the
# only one of the three a production system could actually have computed.
POLICIES = ("latest", "fact_only", "point_in_time")
