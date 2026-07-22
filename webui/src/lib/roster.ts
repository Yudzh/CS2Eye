export const ACTIVE_ROSTER_SIZE = 5;

export const ROSTER_STATUS_ACTIVE =
  "active";

export const ROSTER_STATUS_COACH =
  "coach";


interface CurrentRosterEntry {
  status: string;
  left_at: string | null;
}


export function isActiveRosterStatus(
  status: string,
): boolean {
  return (
    status === ROSTER_STATUS_ACTIVE
  );
}


export function isCoachRosterStatus(
  status: string,
): boolean {
  return (
    status === ROSTER_STATUS_COACH
  );
}


export function isCurrentActivePlayer(
  item: CurrentRosterEntry,
): boolean {
  return (
    isActiveRosterStatus(item.status)
    && item.left_at === null
  );
}