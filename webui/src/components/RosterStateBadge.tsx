import type {
  TeamRosterState,
} from "../types";


const LABELS: Record<
  TeamRosterState["code"],
  string
> = {
  stable: "Стабильный состав",
  new: "Новый состав",
  incomplete: "Неполный состав",
  stand_in: "Есть stand-in",
  unknown: "Статус не определён",
};


export function RosterStateBadge({
  state,
}: {
  state: TeamRosterState;
}) {
  return (
    <span
      className={
        `status-badge status-badge--${state.code}`
      }
    >
      {LABELS[state.code]}
    </span>
  );
}