"""Owner-requested removal of Beijing 2026, including reports and forecasts.

Only this explicitly named event is purged. Shared teams/players are retained.
"""
from sqlalchemy import delete, select, update, or_
import cs2eye.models  # register all dependencies
from cs2eye.db.base import Base
from cs2eye.models.match import Tournament, Match


def apply(session):
    tournament_ids = list(session.scalars(select(Tournament.id).where(
        Tournament.name == 'IEM Beijing 2026', Tournament.year == 2026)))
    if not tournament_ids:
        return
    tables = Base.metadata.tables
    match_ids = list(session.scalars(select(Match.id).where(Match.tournament_id.in_(tournament_ids))))
    # Discover tournament-specific descendants, including SET NULL references:
    # deleting just the tournament would leave forecasts/reports detached.
    selected = {'tournaments':set(tournament_ids), 'matches':set(match_ids)}
    changed = True
    while changed:
        changed = False
        for table in tables.values():
            if table.name in {'teams','players','matches','tournaments'}:
                continue
            conditions = [fk.parent.in_(selected[fk.column.table.name]) for fk in table.foreign_keys
                          if fk.column.table.name in selected and selected[fk.column.table.name]]
            if not conditions:
                continue
            pk = list(table.primary_key.columns)
            if len(pk) != 1:
                raise RuntimeError(f'Cannot safely purge dependent table {table.name}')
            ids = set(session.scalars(select(pk[0]).where(or_(*conditions))))
            merged = selected.get(table.name,set()) | ids
            if merged != selected.get(table.name,set()):
                selected[table.name] = merged
                changed = True
    # Null references from outside this event without touching those rows.
    for table in tables.values():
        for fk in table.foreign_keys:
            parent = fk.column.table.name
            if parent in selected and selected[parent] and fk.parent.nullable:
                session.execute(update(table).where(fk.parent.in_(selected[parent])).values({fk.parent.name:None}))
    # Child-first order; self references have already been cleared.
    pending = set(selected)
    while pending:
        ready = [name for name in pending if not any(
            fk.column.table.name == name and child != name
            for child in pending for fk in tables[child].foreign_keys)]
        if not ready:
            raise RuntimeError('Cannot safely purge cyclic event dependencies')
        for name in ready:
            table = tables[name]
            session.execute(delete(table).where(list(table.primary_key.columns)[0].in_(selected[name])))
            pending.remove(name)
