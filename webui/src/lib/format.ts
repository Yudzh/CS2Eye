const ROLE_LABELS: Record<
  string,
  string
> = {
  igl: "Капитан / IGL",
  awper: "AWP-снайпер",
  rifler: "Рифлер",
  entry_frag: "Энтри-фрагер",
  lurk: "Люркер",
  anchor_support:
    "Опорник / поддержка",
  coach: "Тренер",
};


const CONFIDENCE_LABELS: Record<string, string> = {
  high: "Высокое",
  medium: "Среднее",
  low: "Низкое",

  not_enough_data:
    "Недостаточно данных",
};


const MAP_TIER_LABELS: Record<string, string> = {
  strong: "Сильная",
  average: "Средняя",
  weak: "Слабая",

  floating:
    "Малая выборка",

  permaban:
    "Нет игр / пермабан",
};


export function formatNumber(
  value: number | null | undefined,
  digits = 1,
): string {
  if (
    value === null
    || value === undefined
    || Number.isNaN(value)
  ) {
    return "—";
  }

  return value.toFixed(digits);
}


export function formatPercent(
  value: number | null | undefined,
  digits = 1,
): string {
  if (
    value === null
    || value === undefined
    || Number.isNaN(value)
  ) {
    return "—";
  }

  return `${value.toFixed(digits)}%`;
}


export function formatDate(
  value: string | null | undefined,
): string {
  if (!value) {
    return "—";
  }

  return new Intl.DateTimeFormat(
    "ru-RU",
  ).format(
    new Date(`${value}T00:00:00`),
  );
}


export function roleLabel(
  role: string | null,
): string {
  if (!role) {
    return "Роль не указана";
  }

  return ROLE_LABELS[role] || role;
}


export function confidenceLabel(
  value: string,
): string {
  return CONFIDENCE_LABELS[value] || value;
}


export function mapTierLabel(
  value: string,
): string {
  return MAP_TIER_LABELS[value] || value;
}


export function rosterMemberStatusLabel(
  value: string,
): string {
  if (value === "coach") {
    return "Тренер";
  }

  if (value === "active") {
    return "Основной состав";
  }

  if (value === "stand-in") {
    return "Stand-in";
  }

  return value;
}