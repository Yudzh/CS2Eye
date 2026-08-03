from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoPlayerStat, DemoTeamOpponentContext
from cs2eye.services.demo_team_link_service import PlayerOpponentSnapshot


async def replace_demo_opponent_contexts(
    session: AsyncSession,
    demo_file_id: int,
    snapshots: Iterable[PlayerOpponentSnapshot],
) -> list[str]:
    """Persist one canonical opponent-rank context per resolved demo team."""
    await session.execute(delete(DemoTeamOpponentContext).where(
        DemoTeamOpponentContext.demo_file_id == demo_file_id,
    ))
    grouped: dict[int, list[PlayerOpponentSnapshot]] = {}
    for snapshot in snapshots:
        if snapshot.demo_team_id is not None:
            grouped.setdefault(snapshot.demo_team_id, []).append(snapshot)
    warnings: list[str] = []
    for team_id, items in grouped.items():
        values = {
            (
                item.opponent_team_id, item.opponent_team_name, item.opponent_rank,
                item.opponent_rank_group, item.opponent_rank_source,
                item.opponent_rank_snapshot_id, item.opponent_rank_snapshot_date,
            )
            for item in items
        }
        if len(values) != 1:
            warnings.append(f"inconsistent_opponent_group: demo={demo_file_id}, team={team_id}")
            continue
        value = next(iter(values))
        session.add(DemoTeamOpponentContext(
            demo_file_id=demo_file_id, team_id=team_id,
            opponent_team_id=value[0], opponent_team_name=value[1],
            opponent_rank=value[2], opponent_rank_group=value[3],
            opponent_rank_source=value[4], opponent_rank_snapshot_id=value[5],
            opponent_rank_snapshot_date=value[6],
        ))
    return warnings


async def rebuild_demo_opponent_contexts_from_player_stats(
    session: AsyncSession, demo_file_id: int,
) -> list[str]:
    stats = list((await session.execute(select(DemoPlayerStat).where(
        DemoPlayerStat.demo_file_id == demo_file_id,
    ))).scalars())
    snapshots = [PlayerOpponentSnapshot(
        demo_team_id=item.demo_team_id, demo_team_name=item.demo_team_name,
        opponent_team_id=item.opponent_team_id, opponent_team_name=item.opponent_team_name,
        opponent_rank=item.opponent_rank, opponent_rank_group=item.opponent_rank_group,
        opponent_rank_source=item.opponent_rank_source,
        opponent_rank_snapshot_id=item.opponent_rank_snapshot_id,
        opponent_rank_snapshot_date=item.opponent_rank_snapshot_date,
    ) for item in stats]
    return await replace_demo_opponent_contexts(session, demo_file_id, snapshots)
