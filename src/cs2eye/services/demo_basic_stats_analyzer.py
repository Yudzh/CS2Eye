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
class DemoBasicStats:
    demo_file_path: Path
    rounds: int
    players: list[PlayerDamageStats]


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
        players=players,
    )