TEAM_ROLE_OPTIONS: tuple[
    tuple[str, str],
    ...,
] = (
    ("igl", "Капитан / IGL"),
    ("awper", "AWP-снайпер"),
    ("rifler", "Рифлер"),
    ("entry_frag", "Энтри-фрагер"),
    ("lurk", "Люркер"),
    (
        "anchor_support",
        "Опорник / поддержка",
    ),
    ("coach", "Тренер"),
)

ACTIVE_TEAM_ROLE_CODES = frozenset(
    code
    for code, _ in TEAM_ROLE_OPTIONS
    if code != "coach"
)

TEAM_ROLE_CODES = frozenset(
    code
    for code, _ in TEAM_ROLE_OPTIONS
)

TEAM_ROLE_ALIASES = {
    "igl": "igl",
    "captain": "igl",
    "капитан": "igl",
    "in-game leader": "igl",
    "in game leader": "igl",

    "awp": "awper",
    "awper": "awper",
    "sniper": "awper",

    "entry": "entry_frag",
    "entry frag": "entry_frag",
    "entry fragger": "entry_frag",
    "entry_frag": "entry_frag",

    "lurk": "lurk",
    "lurker": "lurk",

    "anchor": "anchor_support",
    "support": "anchor_support",
    "anchor/support": "anchor_support",
    "anchor support": "anchor_support",
    "anchor_support": "anchor_support",
    "rifler": "rifler",
    "rifle": "rifler",
    "рифлер": "rifler",

    "coach": "coach",
    "тренер": "coach",
}


def normalize_team_role(
        value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = value.strip().casefold()

    if not normalized:
        return None

    role = TEAM_ROLE_ALIASES.get(
        normalized,
        normalized,
    )

    if role not in TEAM_ROLE_CODES:
        raise ValueError(
            f"Invalid role: {value}. "
            f"Allowed roles: "
            f"{', '.join(sorted(TEAM_ROLE_CODES))}"
        )

    return role