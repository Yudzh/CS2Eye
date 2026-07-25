from datetime import date
from typing import Any


def make_ranking_payload(
    *,
    first_team_id: int = 1,
    teams_count: int = 30,
    ranking_date: date = date(2026, 7, 24),
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []

    for rank in range(1, teams_count + 1):
        team_id = first_team_id + rank - 1
        items.append(
            {
                "id": 100_000 + team_id,
                "team_id": team_id,
                "region": "EU",
                "ranking_date": ranking_date.isoformat(),
                "score": str(2100 - rank * 10),
                "rank": rank,
                "rank_diff": 0,
                "team": {
                    "id": team_id,
                    "slug": f"team-{team_id}",
                    "name": f"Team {team_id}",
                    "image_url": (
                        "https://files.bo3.gg/"
                        f"team-{team_id}.webp"
                    ),
                    "country": {
                        "code": "EU",
                        "name": "Europe",
                    },
                },
                "roster_players": [
                    {
                        "id": team_id * 100 + index,
                        "nickname": (
                            f"Player {team_id}-{index}"
                        ),
                        "slug": (
                            f"player-{team_id}-{index}"
                        ),
                        "score": "6.10",
                        "image_url": None,
                        "country_code": "EU",
                    }
                    for index in range(1, 6)
                ],
            }
        )

    return {
        "data": items,
        "meta": {
            "current_page": 1,
            "per_page": teams_count,
            "total_count": 320,
            "ranking_date": ranking_date.isoformat(),
            "source": "internal",
            "is_official": True,
            "updated_at": (
                f"{ranking_date.isoformat()}"
                "T08:00:00+00:00"
            ),
        },
    }
