import type {
  TeamStrength,
  TeamStrengthFactor,
} from "../types";


interface TeamStrengthExplanationProps {
  strength:
    | TeamStrength
    | null
    | undefined;

  compact?: boolean;
}


function numberValue(
  value: unknown,
): number {
  const parsed = Number(value);

  return Number.isFinite(parsed)
    ? parsed
    : 0;
}


function factorValueText(
  factor: TeamStrengthFactor,
): string {
  const value = numberValue(
    factor.value,
  );

  if (factor.kind === "base") {
    return value.toFixed(1);
  }

  if (value > 0) {
    return `+${value.toFixed(1)}`;
  }

  if (value < 0) {
    return value.toFixed(1);
  }

  return "0.0";
}


function factorClassName(
  factor: TeamStrengthFactor,
): string {
  return [
    "strength-factor",
    `strength-factor--${factor.kind}`,
  ].join(" ");
}


export function TeamStrengthExplanation({
  strength,
  compact = false,
}: TeamStrengthExplanationProps) {
  if (!strength) {
    return null;
  }

  const basePlayerScore = numberValue(
    strength.base_player_score,
  );

  const rosterBonus = numberValue(
    strength.roster_bonus,
  );

  const rosterPenalty = numberValue(
    strength.roster_penalty,
  );

  const teamStrengthScore = numberValue(
    strength.team_strength_score,
  );

  const factors = Array.isArray(
    strength.factors,
  )
    ? strength.factors
    : [];

  const calculation =
    strength.calculation
    || [
      basePlayerScore.toFixed(1),
      "+",
      rosterBonus.toFixed(1),
      "-",
      rosterPenalty.toFixed(1),
      "=",
      teamStrengthScore.toFixed(1),
    ].join(" ");

  return (
    <section
      className={
        compact
          ? [
              "strength-explanation",
              "strength-explanation--compact",
            ].join(" ")
          : "strength-explanation"
      }
    >
      <div className="strength-explanation__header">
        <div>
          <span className="panel__label">
            Расчёт силы состава
          </span>

          <h2>
            Почему{" "}
            {teamStrengthScore.toFixed(1)}%
          </h2>
        </div>

        <strong className="strength-explanation__formula">
          {calculation}
        </strong>
      </div>

      <div className="strength-explanation__summary">
        <article>
          <span>
            Средняя сила игроков
          </span>

          <strong>
            {basePlayerScore.toFixed(1)}
          </strong>
        </article>

        <article>
          <span>
            Бонусы
          </span>

          <strong className="text-positive">
            +{rosterBonus.toFixed(1)}
          </strong>
        </article>

        <article>
          <span>
            Штрафы
          </span>

          <strong className="text-danger">
            -{rosterPenalty.toFixed(1)}
          </strong>
        </article>

        <article>
          <span>
            Итог
          </span>

          <strong>
            {teamStrengthScore.toFixed(1)}%
          </strong>
        </article>
      </div>

      {factors.length > 0 ? (
        <div className="strength-factor-list">
          {factors.map(
            (factor, index) => {
              const players =
                Array.isArray(
                  factor.players,
                )
                  ? factor.players
                  : [];

              const key = [
                factor.code || "factor",
                index,
              ].join("-");

              return (
                <article
                  className={
                    factorClassName(
                      factor,
                    )
                  }
                  key={key}
                >
                  <div className="strength-factor__value">
                    {factorValueText(
                      factor,
                    )}
                  </div>

                  <div className="strength-factor__content">
                    <strong>
                      {factor.label
                        || "Фактор силы"}
                    </strong>

                    <p>
                      {factor.explanation
                        || "Описание отсутствует."}
                    </p>

                    {players.length > 0 ? (
                      <small>
                        Игроки:{" "}
                        {players.join(", ")}
                      </small>
                    ) : null}
                  </div>
                </article>
              );
            },
          )}
        </div>
      ) : (
        <p className="muted-text">
          Подробные факторы расчёта
          пока не получены от API.
        </p>
      )}
    </section>
  );
}