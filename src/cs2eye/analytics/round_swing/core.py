"""Pure, reproducible Round Swing V1 model and attribution primitives."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import exp, log
from statistics import median
from typing import Iterable, Sequence


ROUND_WIN_MODEL_VERSION = "v1"
ROUND_SWING_MODEL_VERSION = "v1"
FEATURE_SCHEMA_VERSION = "v1"


@dataclass(frozen=True)
class RoundState:
    map_name: str
    alive_t: int
    alive_ct: int
    bomb_state: str
    equipment_value_t: int | None
    equipment_value_ct: int | None
    round_time_remaining: float | None
    bomb_time_remaining: float | None = None
    bombsite: str | None = None

    def payload(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TrainingExample:
    match_key: str
    chronology: float
    state: RoundState
    t_won: int


@dataclass(frozen=True)
class AttributionCredit:
    identity_key: str
    role: str
    share: float
    credited_swing: float


def attribution_v1(
    event_swing_for_killer_team: float,
    killer_key: str,
    victim_key: str,
    *,
    damage_by_player: dict[str, int] | None = None,
    flash_assister_key: str | None = None,
) -> list[AttributionCredit]:
    """Allocate one transition once; victim impact is explanatory, not additive.

    Positive credit is split by same-round damage to the victim. The finisher is
    guaranteed 20 damage-equivalent so a zero/absent damage event cannot erase
    kill credit. A reliable normalized flash assister receives 10% before the
    remaining damage split. Victim gets the opposite signed transition in the
    player view and is marked non-additive, so team totals use positive roles only.
    """
    damage = {key: max(0, value) for key, value in (damage_by_player or {}).items()}
    damage[killer_key] = max(20, damage.get(killer_key, 0))
    flash_share = .10 if flash_assister_key and flash_assister_key not in {killer_key, victim_key} else 0.0
    pool = 1.0 - flash_share
    total_damage = sum(damage.values()) or 1
    credits = [
        AttributionCredit(key, "killer" if key == killer_key else "damage_assist",
                          pool * value / total_damage, event_swing_for_killer_team * pool * value / total_damage)
        for key, value in sorted(damage.items()) if value > 0
    ]
    if flash_share:
        credits.append(AttributionCredit(flash_assister_key, "flash_assist", flash_share,
                                         event_swing_for_killer_team * flash_share))
    credits.append(AttributionCredit(victim_key, "victim_non_additive", 0.0, -event_swing_for_killer_team))
    return credits


class RoundWinProbabilityModel:
    """Dependency-free standardized logistic regression returning P(T wins)."""

    def __init__(self, artifact: dict):
        self.artifact = artifact

    @staticmethod
    def _sigmoid(value: float) -> float:
        if value >= 0:
            z = exp(-value)
            return 1 / (1 + z)
        z = exp(value)
        return z / (1 + z)

    @staticmethod
    def feature_names(maps: Sequence[str]) -> list[str]:
        return [
            "alive_t", "alive_ct", "alive_delta", "bomb_planted",
            "equipment_t", "equipment_ct", "equipment_delta",
            "round_time_remaining", "round_time_missing",
            "bomb_time_remaining", "bomb_time_missing",
            *[f"map:{name}" for name in maps],
        ]

    @classmethod
    def vector(cls, state: RoundState, maps: Sequence[str]) -> list[float]:
        et = float(state.equipment_value_t or 0) / 25000.0
        ec = float(state.equipment_value_ct or 0) / 25000.0
        rt = float(state.round_time_remaining or 0) / 115.0
        bt = float(state.bomb_time_remaining or 0) / 40.0
        return [
            float(state.alive_t), float(state.alive_ct), float(state.alive_t - state.alive_ct),
            float(state.bomb_state == "planted"), et, ec, et - ec, rt,
            float(state.round_time_remaining is None), bt, float(state.bomb_time_remaining is None),
            *[float(state.map_name.casefold() == name) for name in maps],
        ]

    def predict_batch(self, states: Sequence[RoundState]) -> list[float]:
        maps = self.artifact["maps"]
        means, scales = self.artifact["means"], self.artifact["scales"]
        coefficients = self.artifact["coefficients"]
        output = []
        for state in states:
            values = self.vector(state, maps)
            z = self.artifact["intercept"] + sum(
                coefficient * ((value - mean) / scale)
                for coefficient, value, mean, scale in zip(coefficients, values, means, scales)
            )
            output.append(min(1.0, max(0.0, self._sigmoid(z))))
        return output

    @classmethod
    def train(cls, examples: Sequence[TrainingExample], *, epochs: int = 8,
              learning_rate: float = .10, l2: float = .01) -> tuple["RoundWinProbabilityModel", dict]:
        import numpy as np
        if len(examples) < 2 or len({item.t_won for item in examples}) < 2:
            raise ValueError("Training requires at least two examples and both outcomes.")
        maps = sorted({item.state.map_name.casefold() for item in examples})
        raw = np.asarray([cls.vector(item.state, maps) for item in examples], dtype=float)
        count, width = raw.shape
        means_array = raw.mean(axis=0); scales_array = np.maximum(raw.std(axis=0), 1e-6)
        x = (raw - means_array) / scales_array
        y = np.asarray([float(item.t_won) for item in examples], dtype=float)
        weights = np.zeros(width, dtype=float)
        positive = float(y.sum()); negative = count - positive
        intercept = log((positive + 1) / (negative + 1))
        for _ in range(epochs):
            logits = np.clip(intercept + x @ weights, -35, 35)
            predictions = 1.0 / (1.0 + np.exp(-logits)); errors = predictions - y
            intercept -= learning_rate * float(errors.mean())
            weights -= learning_rate * ((x.T @ errors) / count + l2 * weights)
        means, scales, weights = means_array.tolist(), scales_array.tolist(), weights.tolist()
        artifact = {
            "model_type": "standardized_logistic_regression", "model_version": ROUND_WIN_MODEL_VERSION,
            "feature_schema_version": FEATURE_SCHEMA_VERSION, "feature_names": cls.feature_names(maps),
            "maps": maps, "means": means, "scales": scales, "coefficients": weights,
            "intercept": intercept, "l2": l2,
        }
        model = cls(artifact)
        return model, calibration_metrics(model.predict_batch([item.state for item in examples]), y)


def calibration_metrics(probabilities: Sequence[float], targets: Sequence[float], bins: int = 10) -> dict:
    if not probabilities or len(probabilities) != len(targets):
        raise ValueError("Probabilities and targets must be non-empty and equally sized.")
    eps = 1e-12; n = len(probabilities)
    brier = sum((p - y) ** 2 for p, y in zip(probabilities, targets)) / n
    log_loss = -sum(y * log(max(eps, p)) + (1-y) * log(max(eps, 1-p)) for p, y in zip(probabilities, targets)) / n
    error = 0.0; reliability = []
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        selected = [(p, y) for p, y in zip(probabilities, targets) if low <= p < high or (index == bins-1 and p == 1)]
        if not selected: continue
        predicted = sum(p for p, _ in selected) / len(selected); actual = sum(y for _, y in selected) / len(selected)
        error += len(selected) / n * abs(predicted - actual)
        reliability.append({"low": low, "high": high, "count": len(selected), "predicted": predicted, "actual": actual})
    return {"brier_score": brier, "log_loss": log_loss, "calibration_error": error, "reliability": reliability}


def temporal_group_split(examples: Iterable[TrainingExample], validation_fraction: float = .2):
    grouped: dict[str, list[TrainingExample]] = {}
    for item in examples: grouped.setdefault(item.match_key, []).append(item)
    ordered = sorted(grouped, key=lambda key: min(item.chronology for item in grouped[key]))
    cut = max(1, min(len(ordered) - 1, int(len(ordered) * (1-validation_fraction))))
    train_keys = set(ordered[:cut])
    return ([item for key in ordered if key in train_keys for item in grouped[key]],
            [item for key in ordered if key not in train_keys for item in grouped[key]])


def robust_swing_score(value: float, distribution: Sequence[float]) -> float | None:
    if not distribution: return None
    center = median(distribution)
    deviations = [abs(item - center) for item in distribution]
    scale = max(median(deviations) * 1.4826, 1e-6)
    z = min(3.0, max(-3.0, (value - center) / scale))
    return round(50 + z * (50 / 3), 2)
