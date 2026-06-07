from dataclasses import dataclass
from pathlib import Path

from demoparser2 import DemoParser


PREPARED_DEMOS_DIR = Path("storage/demos/prepared")


class DemoBasicStatsAnalyzeError(Exception):
    pass


@dataclass(frozen=True)
class PlayerDamageStats:
    player_name: str
    team_name: str | None
    total_damage: int
    rounds: int
    average_damage_per_round: float

@dataclass(frozen=True)
class BombRoundStats:
    round_number: int
    planter_name: str | None
    planter_team_name: str | None
    defuser_name: str | None
    defuser_team_name: str | None
    outcome: str  # planted / exploded / defused
    plant_tick: int | None
    defuse_tick: int | None
    explosion_tick: int | None

@dataclass(frozen=True)
class DemoBasicStats:
    demo_file_path: Path
    rounds: int
    players: list[PlayerDamageStats]
    bomb_rounds: list[BombRoundStats]


def _resolve_prepared_demo_path(demo_file_path: str) -> Path:
    path = Path(demo_file_path)

    if path.suffix.lower() != ".dem":
        raise DemoBasicStatsAnalyzeError("Only .dem files can be analyzed")

    resolved_path = path.resolve()
    prepared_root = PREPARED_DEMOS_DIR.resolve()

    try:
        resolved_path.relative_to(prepared_root)
    except ValueError as error:
        raise DemoBasicStatsAnalyzeError(
            "Demo file must be located inside storage/demos/prepared"
        ) from error

    if not resolved_path.exists():
        raise DemoBasicStatsAnalyzeError("Demo file was not found")

    if not resolved_path.is_file():
        raise DemoBasicStatsAnalyzeError("Demo path is not a file")

    return resolved_path


def _count_played_rounds(parser: DemoParser, hurt_df) -> int:
    try:
        round_end_df = parser.parse_event(
            "round_end",
            other=["is_warmup_period"],
        )
    except Exception:
        round_end_df = None

    if round_end_df is not None and not round_end_df.empty:
        if "is_warmup_period" in round_end_df.columns:
            round_end_df = round_end_df[
                round_end_df["is_warmup_period"] == False
            ]

        if not round_end_df.empty:
            return int(len(round_end_df))

    if "total_rounds_played" in hurt_df.columns and not hurt_df.empty:
        return int(hurt_df["total_rounds_played"].max()) + 1

    return 1


def analyze_demo_basic_stats(demo_file_path: str) -> DemoBasicStats:
    resolved_demo_path = _resolve_prepared_demo_path(demo_file_path)

    try:
        parser = DemoParser(str(resolved_demo_path))

        hurt_df = parser.parse_event(
            "player_hurt",
            player=["team_name"],
            other=["total_rounds_played", "is_warmup_period"],
        )
    except Exception as error:
        raise DemoBasicStatsAnalyzeError(
            f"Could not parse demo file: {error}"
        ) from error

    if hurt_df.empty:
        raise DemoBasicStatsAnalyzeError("No player_hurt events found in demo")

    required_columns = {"attacker_name", "dmg_health"}
    missing_columns = required_columns - set(hurt_df.columns)

    if missing_columns:
        raise DemoBasicStatsAnalyzeError(
            f"player_hurt event has unexpected format. Missing columns: "
            f"{', '.join(sorted(missing_columns))}"
        )

    if "is_warmup_period" in hurt_df.columns:
        hurt_df = hurt_df[hurt_df["is_warmup_period"] == False]

    if "attacker_team_name" in hurt_df.columns and "user_team_name" in hurt_df.columns:
        hurt_df = hurt_df[
            hurt_df["attacker_team_name"] != hurt_df["user_team_name"]
        ]

    hurt_df = hurt_df[
        hurt_df["attacker_name"].notna()
        & (hurt_df["attacker_name"] != "")
    ]

    if hurt_df.empty:
        raise DemoBasicStatsAnalyzeError(
            "No valid damage events found after filtering warmup/team damage"
        )

    rounds_count = _count_played_rounds(parser, hurt_df)
    bomb_rounds = _analyze_bomb_rounds(parser)

    group_columns = ["attacker_name"]

    if "attacker_team_name" in hurt_df.columns:
        group_columns.append("attacker_team_name")

    damage_df = (
        hurt_df
        .groupby(group_columns, dropna=False)["dmg_health"]
        .sum()
        .reset_index()
        .sort_values("dmg_health", ascending=False)
    )

    players: list[PlayerDamageStats] = []

    for row in damage_df.to_dict(orient="records"):
        total_damage = int(row["dmg_health"])

        players.append(
            PlayerDamageStats(
                player_name=str(row["attacker_name"]),
                team_name=(
                    None
                    if "attacker_team_name" not in row
                    else str(row["attacker_team_name"])
                ),
                total_damage=total_damage,
                rounds=rounds_count,
                average_damage_per_round=round(
                    total_damage / rounds_count,
                    2,
                ),
            )
        )

    return DemoBasicStats(
        demo_file_path=resolved_demo_path,
        rounds=rounds_count,
        bomb_rounds=bomb_rounds,
        players=players,
    )

def _safe_parse_event(parser: DemoParser, event_name: str, player: list[str] | None = None, other: list[str] | None = None):
    try:
        return parser.parse_event(
            event_name,
            player=player or [],
            other=other or [],
        )
    except Exception:
        return None


def _clean_string(value) -> str | None:
    if value is None:
        return None

    if value != value:  # NaN check
        return None

    value_as_string = str(value).strip()

    if not value_as_string:
        return None

    return value_as_string


def _get_optional_int(row: dict, column_names: list[str]) -> int | None:
    for column_name in column_names:
        if column_name not in row:
            continue

        value = row[column_name]

        if value is None or value != value:
            continue

        return int(value)

    return None


def _get_event_round_number(row: dict) -> int:
    total_rounds_played = _get_optional_int(row, ["total_rounds_played"])

    if total_rounds_played is None:
        return 1

    return total_rounds_played + 1


def _get_event_tick(row: dict) -> int | None:
    return _get_optional_int(row, ["tick", "event_tick"])


def _event_rows_without_warmup(event_df) -> list[dict]:
    if event_df is None:
        return []

    if isinstance(event_df, list):
        rows: list[dict] = []

        for row in event_df:
            if not isinstance(row, dict):
                continue

            if row.get("is_warmup_period") is True:
                continue

            rows.append(row)

        return rows

    if hasattr(event_df, "empty") and event_df.empty:
        return []

    if hasattr(event_df, "is_empty") and event_df.is_empty():
        return []

    if hasattr(event_df, "columns") and "is_warmup_period" in event_df.columns:
        event_df = event_df[event_df["is_warmup_period"] == False]

    if hasattr(event_df, "to_dict"):
        return event_df.to_dict(orient="records")

    return []


def _analyze_bomb_rounds(parser: DemoParser) -> list[BombRoundStats]:
    plant_df = _safe_parse_event(
        parser,
        "bomb_planted",
        player=["team_name"],
        other=["total_rounds_played", "is_warmup_period"],
    )

    defuse_df = _safe_parse_event(
        parser,
        "bomb_defused",
        player=["team_name"],
        other=["total_rounds_played", "is_warmup_period"],
    )

    explosion_df = _safe_parse_event(
        parser,
        "bomb_exploded",
        other=["total_rounds_played", "is_warmup_period"],
    )

    bomb_rounds_by_number: dict[int, dict] = {}

    for row in _event_rows_without_warmup(plant_df):
        round_number = _get_event_round_number(row)

        bomb_rounds_by_number[round_number] = {
            "round_number": round_number,
            "planter_name": _clean_string(row.get("user_name")),
            "planter_team_name": _clean_string(row.get("user_team_name")),
            "defuser_name": None,
            "defuser_team_name": None,
            "outcome": "planted",
            "plant_tick": _get_event_tick(row),
            "defuse_tick": None,
            "explosion_tick": None,
        }

    for row in _event_rows_without_warmup(explosion_df):
        round_number = _get_event_round_number(row)

        bomb_round = bomb_rounds_by_number.setdefault(
            round_number,
            {
                "round_number": round_number,
                "planter_name": None,
                "planter_team_name": None,
                "defuser_name": None,
                "defuser_team_name": None,
                "outcome": "exploded",
                "plant_tick": None,
                "defuse_tick": None,
                "explosion_tick": None,
            },
        )

        bomb_round["outcome"] = "exploded"
        bomb_round["explosion_tick"] = _get_event_tick(row)

    for row in _event_rows_without_warmup(defuse_df):
        round_number = _get_event_round_number(row)

        bomb_round = bomb_rounds_by_number.setdefault(
            round_number,
            {
                "round_number": round_number,
                "planter_name": None,
                "planter_team_name": None,
                "defuser_name": None,
                "defuser_team_name": None,
                "outcome": "defused",
                "plant_tick": None,
                "defuse_tick": None,
                "explosion_tick": None,
            },
        )

        bomb_round["outcome"] = "defused"
        bomb_round["defuser_name"] = _clean_string(row.get("user_name"))
        bomb_round["defuser_team_name"] = _clean_string(row.get("user_team_name"))
        bomb_round["defuse_tick"] = _get_event_tick(row)

    return [
        BombRoundStats(**bomb_round)
        for bomb_round in sorted(
            bomb_rounds_by_number.values(),
            key=lambda item: item["round_number"],
        )
    ]