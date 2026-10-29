"""Seeded world generator carrying both timestamps on every event.

No public dataset records when a fact became true and when it arrived in the
warehouse as separate columns, which is exactly why point-in-time leakage is
hard to study on real data (ADR-001). This generator exists to make the leak
measurable: it produces entities, events and outcomes where the arrival delay
is a configured distribution, so the gap between what a pipeline read and what
was knowable has a ground truth.

The causal order matters and is fixed: latent risk, then incidents, then the
outcome label, then the post-outcome contamination (assessments written after
the prediction instant see the outcome; corrections backdate their fact time).
The contamination steps are what make the "latest value" join and the
fact-time-only join leak in the specific ways E2 attributes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import GeneratorConfig

EPOCH = pd.Timestamp("2025-01-01T00:00:00", tz="UTC")

STATUS_OK = "ok"
STATUS_WATCH = "watch"
STATUS_RISKY = "risky"


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _lognormal_delay(rng: np.random.Generator, n: int, median: float, sigma: float) -> np.ndarray:
    """Lognormal arrival delays parameterised by their median, in days.

    A median of zero is allowed and means instantaneous arrival, which E4
    uses as the no-delay endpoint of the sweep.
    """
    if median <= 0.0:
        return np.zeros(n)
    return rng.lognormal(mean=np.log(median), sigma=sigma, size=n)


def generate_world(cfg: GeneratorConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (events, predictions).

    events columns: event_id, entity_id, event_type, fact_days, arrival_days,
    value, status. Times are float days since the epoch; materialisation to
    timestamps happens in the event log writer so that this module stays a
    pure function of the config.

    predictions columns: entity_id, prediction_days, label.
    """
    rng = np.random.default_rng(cfg.seed)
    n = cfg.n_entities
    d = cfg.delays

    risk = rng.normal(0.0, 1.0, size=n)
    lo, hi = cfg.prediction_window
    pred_days = rng.uniform(lo, hi, size=n)

    frames: list[pd.DataFrame] = []

    # Activity: frequent, fast arriving, mildly informative through its rate.
    act_counts = rng.poisson(np.exp(cfg.activity_rate_base + cfg.activity_rate_risk * risk))
    act_entity = np.repeat(np.arange(n), act_counts)
    n_act = int(act_counts.sum())
    act_fact = rng.uniform(0.0, cfg.horizon_days, size=n_act)
    act_arrival = act_fact + _lognormal_delay(rng, n_act, d.activity_median, d.activity_sigma)
    act_value = rng.lognormal(3.0, 0.6, size=n_act)
    frames.append(
        pd.DataFrame(
            {
                "entity_id": act_entity,
                "event_type": "activity",
                "fact_days": act_fact,
                "arrival_days": act_arrival,
                "value": act_value,
                "status": None,
            }
        )
    )

    # Incidents: the fact that is true before prediction time and recorded
    # after it. Their count inside the feature window feeds the label, so a
    # pipeline that reads them by fact time alone is reading the answer key.
    inc_counts = rng.poisson(np.exp(cfg.incident_rate_base + cfg.incident_rate_risk * risk))
    inc_entity = np.repeat(np.arange(n), inc_counts)
    n_inc = int(inc_counts.sum())
    inc_fact = rng.uniform(
        np.repeat(pred_days, inc_counts) - cfg.incident_fact_before,
        np.repeat(pred_days, inc_counts) + cfg.incident_fact_after,
    )
    inc_arrival = inc_fact + _lognormal_delay(rng, n_inc, d.incident_median, d.incident_sigma)
    inc_sev = rng.lognormal(0.5 + 0.35 * np.repeat(risk, inc_counts), 0.5, size=n_inc)
    frames.append(
        pd.DataFrame(
            {
                "entity_id": inc_entity,
                "event_type": "incident",
                "fact_days": inc_fact,
                "arrival_days": inc_arrival,
                "value": inc_sev,
                "status": None,
            }
        )
    )

    # Label: risk plus the incident count inside the window the leaking
    # feature uses, so the leak has a known mechanism rather than a vibe.
    window_count = np.zeros(n)
    in_window = (inc_fact > np.repeat(pred_days, inc_counts) - cfg.feature_window_days) & (
        inc_fact <= np.repeat(pred_days, inc_counts)
    )
    np.add.at(window_count, inc_entity[in_window], 1.0)
    p = _sigmoid(
        cfg.label_risk_weight * risk + cfg.label_incident_weight * window_count + cfg.label_bias
    )
    label = (rng.uniform(size=n) < p).astype(np.int8)

    # Risk assessments: periodic scores. Assessments written after the
    # prediction instant see the outcome, which is how a "latest value" join
    # on a slowly changing dimension reads the future.
    k_assess = int(np.ceil(cfg.horizon_days / cfg.assessment_every_days))
    base_grid = (np.arange(k_assess) + 0.5) * cfg.assessment_every_days
    ass_entity = np.repeat(np.arange(n), k_assess)
    ass_fact = (
        np.tile(base_grid, n) + rng.uniform(-2.0, 2.0, size=n * k_assess)
    ).clip(0.0, cfg.horizon_days)
    ass_arrival = ass_fact + _lognormal_delay(
        rng, n * k_assess, d.assessment_median, d.assessment_sigma
    )
    post = ass_fact >= np.repeat(pred_days, k_assess)
    ass_value = (
        np.repeat(risk, k_assess)
        + cfg.post_assessment_label_shift * post * (np.repeat(label, k_assess) - 0.5)
        + rng.normal(0.0, cfg.assessment_noise, size=n * k_assess)
    )
    frames.append(
        pd.DataFrame(
            {
                "entity_id": ass_entity,
                "event_type": "risk_assessment",
                "fact_days": ass_fact,
                "arrival_days": ass_arrival,
                "value": ass_value,
                "status": None,
            }
        )
    )

    # Status changes, including backdated corrections. A correction is created
    # weeks after the outcome but its fact time is set before the prediction
    # instant, which is the leak class that defeats even a correct fact-time
    # predicate: only the arrival predicate keeps it out.
    st_entity = np.arange(n)
    st_fact0 = np.zeros(n)
    st_arr0 = st_fact0 + _lognormal_delay(rng, n, d.status_median, d.status_sigma)
    frames.append(
        pd.DataFrame(
            {
                "entity_id": st_entity,
                "event_type": "status_change",
                "fact_days": st_fact0,
                "arrival_days": st_arr0,
                "value": np.zeros(n),
                "status": STATUS_OK,
            }
        )
    )
    watch = risk > 0.6
    n_watch = int(watch.sum())
    w_fact = rng.uniform(5.0, np.minimum(pred_days[watch] - 1.0, cfg.horizon_days))
    w_arr = w_fact + _lognormal_delay(rng, n_watch, d.status_median, d.status_sigma)
    frames.append(
        pd.DataFrame(
            {
                "entity_id": st_entity[watch],
                "event_type": "status_change",
                "fact_days": w_fact,
                "arrival_days": w_arr,
                "value": np.zeros(n_watch),
                "status": STATUS_WATCH,
            }
        )
    )
    corr_draw = rng.uniform(size=n)
    corrected = ((label == 1) & (corr_draw < cfg.correction_prob_positive)) | (
        (label == 0) & (corr_draw < cfg.correction_prob_negative)
    )
    n_corr = int(corrected.sum())
    corr_created = pred_days[corrected] + rng.uniform(5.0, 25.0, size=n_corr)
    corr_fact = pred_days[corrected] - rng.uniform(0.0, cfg.correction_backdate_max, size=n_corr)
    frames.append(
        pd.DataFrame(
            {
                "entity_id": st_entity[corrected],
                "event_type": "status_change",
                "fact_days": corr_fact,
                "arrival_days": corr_created,
                "value": np.ones(n_corr),
                "status": STATUS_RISKY,
            }
        )
    )

    events = pd.concat(frames, ignore_index=True)
    events["entity_id"] = events["entity_id"].astype(np.int32)
    events["value"] = events["value"].round(6)
    events["fact_days"] = events["fact_days"].round(6)
    events["arrival_days"] = events["arrival_days"].round(6)

    # Canonical order is arrival order, which is what a log preserves and a
    # warehouse forgets. Event ids are assigned after this sort so they are a
    # pure function of the config.
    events = events.sort_values(
        ["arrival_days", "entity_id", "event_type", "fact_days", "value"],
        kind="mergesort",
    ).reset_index(drop=True)
    events.insert(0, "event_id", np.arange(len(events), dtype=np.int64))

    predictions = pd.DataFrame(
        {
            "entity_id": np.arange(n, dtype=np.int32),
            "prediction_days": np.round(pred_days, 6),
            "label": label,
        }
    )
    return events, predictions


def to_timestamp(days: pd.Series) -> pd.Series:
    """Materialise float days since the epoch as UTC microsecond timestamps."""
    micros = np.round(days.to_numpy() * 86400.0 * 1e6).astype(np.int64)
    return pd.Series(EPOCH + pd.to_timedelta(micros, unit="us"), index=days.index)
