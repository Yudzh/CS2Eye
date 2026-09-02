from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


COMPARISON_TYPES = {
    "consensus_3_3", "team_strength_dissent", "matchup_dissent", "ml_dissent", "incomplete",
}


class PredictionHistoryEvaluationService:
    """Pure evaluation formulas for immutable prediction-history snapshots."""

    CALIBRATION_BUCKETS = ((.50, .55), (.55, .60), (.60, .65), (.65, .70), (.70, .80), (.80, 1.0))

    @staticmethod
    def comparison(predictions: list[int | None]) -> dict[str, Any]:
        base = {"type": "incomplete", "majority_winner_id": None,
                "dissent_model": None, "dissent_winner_id": None}
        if len(predictions) != 3 or any(value is None for value in predictions):
            return base
        ts, matchup, ml = predictions
        if ts == matchup == ml:
            return {**base, "type": "consensus_3_3", "majority_winner_id": ts}
        if ts == matchup:
            return {**base, "type": "ml_dissent", "majority_winner_id": ts,
                    "dissent_model": "ml", "dissent_winner_id": ml}
        if ts == ml:
            return {**base, "type": "matchup_dissent", "majority_winner_id": ts,
                    "dissent_model": "matchup", "dissent_winner_id": matchup}
        # With two teams, the remaining valid 2-vs-1 case is Matchup + ML vs TS.
        if matchup == ml:
            return {**base, "type": "team_strength_dissent", "majority_winner_id": matchup,
                    "dissent_model": "team_strength", "dissent_winner_id": ts}
        return base

    def evaluate(self, items: list[dict], *, count_items: list[dict] | None = None) -> dict:
        count_items = items if count_items is None else count_items
        official = [item for item in items if item["source"] == "pre_match" and item["completed"]
                    and item["actual_winner_id"] is not None]

        def metric(key: str) -> dict:
            values = [item[key] for item in official if item[key]["predicted_winner_id"] is not None]
            correct = sum(value["correct"] is True for value in values)
            return self._metric(correct, len(values))

        consensus_items = [item for item in official if item["comparison"]["type"] == "consensus_3_3"]
        consensus_correct = sum(item["comparison"]["majority_winner_id"] == item["actual_winner_id"]
                                for item in consensus_items)
        conflict_items = [item for item in official if item["comparison"]["type"].endswith("_dissent")]
        majority_correct = sum(item["comparison"]["majority_winner_id"] == item["actual_winner_id"]
                               for item in conflict_items)
        dissent_correct = sum(item["comparison"]["dissent_winner_id"] == item["actual_winner_id"]
                              for item in conflict_items)
        conflicts = {"total": len(conflict_items), "majority_correct": majority_correct,
                     "majority_accuracy": self._ratio(majority_correct, len(conflict_items)),
                     "dissent_correct": dissent_correct,
                     "dissent_accuracy": self._ratio(dissent_correct, len(conflict_items))}
        # Keep the v2.2 per-shape keys while exposing the v2.3 aggregate above.
        legacy_types = {"ml_dissent": "ts_matchup_vs_ml", "matchup_dissent": "ts_ml_vs_matchup",
                        "team_strength_dissent": "matchup_ml_vs_ts"}
        for comparison_type, legacy_key in legacy_types.items():
            cases = [item for item in conflict_items if item["comparison"]["type"] == comparison_type]
            mc = sum(item["comparison"]["majority_winner_id"] == item["actual_winner_id"] for item in cases)
            dc = sum(item["comparison"]["dissent_winner_id"] == item["actual_winner_id"] for item in cases)
            conflicts[legacy_key] = {"total": len(cases), "majority_correct": mc, "dissent_correct": dc,
                                     "majority_accuracy": self._ratio(mc, len(cases)),
                                     "dissent_accuracy": self._ratio(dc, len(cases))}
        dissent = {}
        for model in ("team_strength", "matchup", "ml"):
            cases = [item for item in conflict_items if item["comparison"]["dissent_model"] == model]
            dc = sum(item["comparison"]["dissent_winner_id"] == item["actual_winner_id"] for item in cases)
            mc = len(cases) - dc
            dissent[model] = {"cases": len(cases), "dissent_correct": dc,
                              "dissent_accuracy": self._ratio(dc, len(cases)),
                              "majority_correct": mc,
                              "majority_accuracy": self._ratio(mc, len(cases))}

        ml_items = [item for item in official if self._valid_ml(item)]
        ml_quality = self._ml_quality(ml_items)
        return {
            "team_strength": metric("team_strength"), "matchup": metric("matchup"), "ml": metric("ml"),
            "consensus_3_3": self._metric(consensus_correct, len(consensus_items)),
            "conflicts": conflicts, "dissent": dissent,
            "disagreement": self._disagreement(official),
            "ml_quality": ml_quality,
            "calibration": self._calibration(ml_items),
            "by_version": self._by_version(official),
            "snapshot_counts": {
                "pre_match": sum(item["source"] == "pre_match" for item in count_items),
                "retrospective": sum(item["source"] == "retrospective" for item in count_items),
                "completed_pre_match": sum(item["source"] == "pre_match" and item["completed"] for item in count_items),
            },
        }

    @staticmethod
    def _ratio(value: int, total: int) -> float | None:
        return None if not total else value / total

    @classmethod
    def _metric(cls, correct: int, total: int) -> dict:
        return {"correct": correct, "total": total, "accuracy": cls._ratio(correct, total)}

    @staticmethod
    def _valid_ml(item: dict) -> bool:
        p = item["ml"]["team_a_value"]
        return item["ml"]["predicted_winner_id"] is not None and p is not None and 0 <= p <= 1

    def _ml_quality(self, items: list[dict]) -> dict:
        if not items:
            return {"samples": 0, "brier_score": None, "log_loss": None}
        brier = 0.0
        log_loss = 0.0
        epsilon = 1e-15
        for item in items:
            p = item["ml"]["team_a_value"]
            y = 1.0 if item["actual_winner_id"] == item["team_a"]["id"] else 0.0
            brier += (p - y) ** 2
            clamped = min(max(p, epsilon), 1 - epsilon)
            log_loss += -(y * math.log(clamped) + (1 - y) * math.log(1 - clamped))
        return {"samples": len(items), "brier_score": brier / len(items),
                "log_loss": log_loss / len(items)}

    def _calibration(self, items: list[dict]) -> list[dict]:
        result = []
        for lower, upper in self.CALIBRATION_BUCKETS:
            bucket = []
            for item in items:
                p_a = item["ml"]["team_a_value"]
                p_b = item["ml"].get("team_b_value")
                favorite_p = max(p_a, (1 - p_a) if p_b is None else p_b)
                if lower <= favorite_p < upper or upper == 1.0 and favorite_p <= upper and favorite_p >= lower:
                    favorite_id = item["ml"]["predicted_winner_id"]
                    bucket.append((favorite_p, favorite_id == item["actual_winner_id"]))
            label = f"{int(lower * 100)}-{int(upper * 100)}"
            result.append({"range": label, "samples": len(bucket),
                           "average_predicted_probability": None if not bucket else sum(x[0] for x in bucket) / len(bucket),
                           "actual_win_rate": None if not bucket else sum(x[1] for x in bucket) / len(bucket)})
        return result

    @staticmethod
    def _disagreement(items: list[dict]) -> dict:
        pairs = (("team_strength", "matchup"), ("team_strength", "ml"), ("matchup", "ml"))
        result = {}
        for left, right in pairs:
            comparable = [item for item in items if item[left]["predicted_winner_id"] is not None
                          and item[right]["predicted_winner_id"] is not None]
            different = sum(item[left]["predicted_winner_id"] != item[right]["predicted_winner_id"]
                            for item in comparable)
            result[f"{left}_vs_{right}"] = {"different": different, "total_comparable": len(comparable),
                                             "rate": None if not comparable else different / len(comparable)}
        return result

    def _by_version(self, items: list[dict]) -> dict:
        result = {}
        for model, version_key in (("team_strength", "team_strength"), ("matchup", "matchup"), ("ml", "ml")):
            groups = defaultdict(list)
            for item in items:
                if item[model]["predicted_winner_id"] is not None:
                    schema = item["versions"]["ml_feature_schema"] if model == "ml" else None
                    groups[(item["versions"][version_key] or "unknown", schema or "unknown")].append(item)
            rows = []
            for (version, schema), group in sorted(groups.items()):
                correct = sum(item[model]["correct"] is True for item in group)
                row = {"model_version": version, "samples": len(group), "accuracy": correct / len(group)}
                if model == "ml":
                    quality = self._ml_quality([item for item in group if self._valid_ml(item)])
                    row.update({"feature_schema_version": schema, "brier_score": quality["brier_score"],
                                "log_loss": quality["log_loss"]})
                rows.append(row)
            result[model] = rows
        return result
