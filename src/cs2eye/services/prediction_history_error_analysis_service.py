from __future__ import annotations

from collections import defaultdict


RELIABILITY_BUCKETS = (("low", 0.0, .45), ("medium", .45, .75), ("high", .75, 1.0000001))
CONTRIBUTION_BUCKETS = (("0-1", 0, 1), ("1-2", 1, 2), ("2-3", 2, 3), ("3+", 3, float("inf")))
MARGIN_BUCKETS = (("0-5", 0, 5), ("5-10", 5, 10), ("10-20", 10, 20), ("20+", 20, float("inf")))


class PredictionHistoryErrorAnalysisService:
    """Deterministic diagnostics based exclusively on immutable snapshot values."""

    @staticmethod
    def analyze_item(item: dict, matchup_factors: dict | None) -> dict:
        actual = item["actual_winner_id"]
        completed = item["completed"] and actual is not None

        def correctness(prediction: dict) -> bool | None:
            winner = prediction["predicted_winner_id"]
            return None if not completed or winner is None else winner == actual

        ts_margin = PredictionHistoryErrorAnalysisService._margin(item["team_strength"])
        matchup_margin = PredictionHistoryErrorAnalysisService._margin(item["matchup"])
        ml_winner = item["ml"]["predicted_winner_id"]
        ml_a, ml_b = item["ml"]["team_a_value"], item["ml"]["team_b_value"]
        selected_probability = None
        if ml_winner is not None and ml_a is not None and ml_b is not None:
            selected_probability = ml_a if ml_winner == item["team_a"]["id"] else ml_b

        factor_rows = []
        factors = (matchup_factors or {}).get("factors") or {}
        predicted = item["matchup"]["predicted_winner_id"]
        for key, factor in factors.items():
            score = factor.get("team_a_score")
            contribution = float(factor.get("contribution") or 0)
            direction_id = None if score is None or float(score) == 50 else (
                item["team_a"]["id"] if float(score) > 50 else item["team_b"]["id"])
            toward_prediction = contribution if predicted == item["team_a"]["id"] else -contribution
            factor_rows.append({**factor, "factor": key, "contribution": contribution,
                                "direction_winner_id": direction_id,
                                "direction_correct": None if direction_id is None or not completed else direction_id == actual,
                                "toward_predicted_winner": toward_prediction > 0})
        drivers = sorted((row for row in factor_rows if row["toward_predicted_winner"]),
                         key=lambda row: abs(row["contribution"]), reverse=True)
        matchup_correct = correctness(item["matchup"])
        matchup_analysis = {
            "status": "available" if factor_rows else "not_available",
            "is_correct": matchup_correct, "margin": matchup_margin,
            "strongest_driver": PredictionHistoryErrorAnalysisService._driver(drivers[0]) if drivers else None,
            "error_drivers": [PredictionHistoryErrorAnalysisService._driver(row) for row in drivers]
                             if matchup_correct is False else [],
            "factors": factor_rows,
        }
        return {
            "team_strength": {"is_correct": correctness(item["team_strength"]), "margin": ts_margin},
            "matchup": matchup_analysis,
            "ml": {"is_correct": correctness(item["ml"]), "probability": selected_probability,
                   "confidence_margin": None if selected_probability is None else abs(selected_probability - .5)},
        }

    def aggregate(self, items: list[dict]) -> dict:
        official = [x for x in items if x["source"] == "pre_match" and x["completed"]
                    and x["actual_winner_id"] is not None]
        return {
            "matchup_factor_quality": self._factor_quality(official),
            "matchup_error_drivers": self._error_drivers(official),
            "matchup_margin_quality": self._margin_quality(official, "matchup"),
            "team_strength_margin_quality": self._margin_quality(official, "team_strength"),
            "ml_high_confidence_errors": self._ml_high_confidence(official),
            "by_matchup_version": self._by_matchup_version(official),
        }

    @staticmethod
    def _margin(prediction: dict) -> float | None:
        a, b = prediction["team_a_value"], prediction["team_b_value"]
        return None if a is None or b is None else abs(a - b)

    @staticmethod
    def _driver(row: dict) -> dict:
        return {"factor": row["factor"], "label": row.get("label", row["factor"]),
                "contribution": abs(row["contribution"]),
                "reliability": row.get("reliability")}

    def _factor_quality(self, items: list[dict]) -> dict:
        factors = defaultdict(list)
        for item in items:
            for factor in item["error_analysis"]["matchup"]["factors"]:
                if factor["direction_correct"] is not None:
                    factors[factor["factor"]].append(factor)
        result = {}
        for key, rows in sorted(factors.items()):
            correct = sum(row["direction_correct"] for row in rows)
            reliability = {}
            for name, lower, upper in RELIABILITY_BUCKETS:
                bucket = [row for row in rows if row.get("reliability") is not None
                          and lower <= float(row["reliability"]) < upper]
                reliability[name] = self._accuracy(bucket)
            contribution = []
            for name, lower, upper in CONTRIBUTION_BUCKETS:
                bucket = [row for row in rows if lower <= abs(row["contribution"]) < upper]
                contribution.append({"range": name, **self._accuracy(bucket)})
            result[key] = {"directional_cases": len(rows), "direction_correct": correct,
                           "direction_accuracy": correct / len(rows),
                           "reliability": reliability, "contribution_buckets": contribution,
                           "label": rows[0].get("label", key)}
        return result

    @staticmethod
    def _accuracy(rows: list[dict]) -> dict:
        correct = sum(row["direction_correct"] for row in rows)
        return {"samples": len(rows), "direction_accuracy": None if not rows else correct / len(rows)}

    @staticmethod
    def _error_drivers(items: list[dict]) -> dict:
        result = defaultdict(lambda: {"top_driver_cases": 0, "present_in_error_cases": 0})
        for item in items:
            matchup = item["error_analysis"]["matchup"]
            if matchup["is_correct"] is not False or matchup["status"] != "available":
                continue
            drivers = matchup["error_drivers"]
            if drivers:
                result[drivers[0]["factor"]]["top_driver_cases"] += 1
            for driver in drivers:
                result[driver["factor"]]["present_in_error_cases"] += 1
        return dict(sorted(result.items()))

    @staticmethod
    def _margin_quality(items: list[dict], model: str) -> list[dict]:
        rows = [item for item in items if item[model]["predicted_winner_id"] is not None
                and item["error_analysis"][model]["margin"] is not None]
        result = []
        for name, lower, upper in MARGIN_BUCKETS:
            bucket = [item for item in rows if lower <= item["error_analysis"][model]["margin"] < upper]
            correct = sum(item[model]["correct"] is True for item in bucket)
            result.append({"range": name, "samples": len(bucket), "correct": correct,
                           "accuracy": None if not bucket else correct / len(bucket)})
        return result

    @staticmethod
    def _ml_high_confidence(items: list[dict]) -> dict:
        result = {}
        for label, threshold in (("65_plus", .65), ("70_plus", .70), ("80_plus", .80)):
            rows = [item for item in items if item["error_analysis"]["ml"]["probability"] is not None
                    and item["error_analysis"]["ml"]["probability"] >= threshold]
            errors = sum(item["error_analysis"]["ml"]["is_correct"] is False for item in rows)
            result[label] = {"predictions": len(rows), "errors": errors,
                             "error_rate": None if not rows else errors / len(rows)}
        return result

    def _by_matchup_version(self, items: list[dict]) -> dict:
        groups = defaultdict(list)
        for item in items:
            groups[item["versions"]["matchup"] or "unknown"].append(item)
        return {version: {"matchup_factor_quality": self._factor_quality(rows),
                          "matchup_error_drivers": self._error_drivers(rows),
                          "matchup_margin_quality": self._margin_quality(rows, "matchup")}
                for version, rows in sorted(groups.items())}
