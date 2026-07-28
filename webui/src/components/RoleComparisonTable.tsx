import type { TeamComparison } from "../types";

const labels: Record<string, string> = {
  igl: "IGL", awper: "AWPer", entry_frag: "Entry Frag",
  lurk: "Lurk", anchor_support: "Anchor / Support", rifler: "Rifler",
};

export function RoleComparisonTable({ comparison }: { comparison: TeamComparison }) {
  return (
    <section className="role-comparison">
      <div className="section-heading"><div><p className="eyebrow">Роли</p><h2>Сравнение игроков</h2></div></div>
      <div className="role-table">
        <div className="role-row role-row--head"><span>Роль</span><span>{comparison.team_a.name}</span><span>{comparison.team_b.name}</span><span>Преимущество</span></div>
        {comparison.role_comparisons.map((role) => (
          <div className="role-row" key={role.role}>
            <strong>{labels[role.role]}</strong>
            {[role.team_a_players, role.team_b_players].map((players, index) => <div key={index}>{players.length ? players.map((player) => <a href={`/players/${player.id}`} key={player.id}>{player.nickname} · {player.effective_player_strength}{player.strength_is_fallback ? "*" : ""}</a>) : <span>Роль не назначена</span>}</div>)}
            <div><strong>{role.advantage_team_name || "Нет явного"}</strong>{role.advantage_diff !== null && <small>Разница: {role.advantage_diff.toFixed(2)}</small>}<small>{role.note}</small></div>
          </div>
        ))}
      </div>
    </section>
  );
}
