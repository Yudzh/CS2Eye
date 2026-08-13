from typing import Literal

EconomyState = Literal["eco", "force_buy", "full_buy", "unknown"]

# Экспертная базовая версия v1 для суммарной стоимости снаряжения пятёрки в
# конце freeze time. Порог CT выше из-за более дорогих винтовок и defuse kit.
ECONOMY_CLASSIFICATION_VERSION = "v1"
ECO_MAX_VALUE = 6_000
T_FULL_BUY_MIN = 18_000
CT_FULL_BUY_MIN = 20_000


def classify_economy(value: int | None, side: str | None) -> EconomyState:
    if value is None or value < 0 or side not in {"T", "CT"}:
        return "unknown"
    if value <= ECO_MAX_VALUE:
        return "eco"
    full_min = CT_FULL_BUY_MIN if side == "CT" else T_FULL_BUY_MIN
    if value >= full_min:
        return "full_buy"
    return "force_buy"
