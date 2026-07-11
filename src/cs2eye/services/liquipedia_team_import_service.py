import re
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from urllib.parse import quote, unquote

import httpx

LIQUIPEDIA_COUNTERSTRIKE_API_URL = "https://liquipedia.net/counterstrike/api.php"
LIQUIPEDIA_COUNTERSTRIKE_BASE_URL = "https://liquipedia.net/counterstrike"
LIQUIPEDIA_USER_AGENT = "CS2Eye/0.1 local-development"


@dataclass(frozen=True)
class LiquipediaRosterPlayer:
    nickname: str
    real_name: str | None
    country: str | None
    status: str
    role: str | None
    joined_at: date | None
    left_at: date | None
    liquipedia_url: str | None
    source_url: str
    source_confidence: float
    notes: str | None


@dataclass(frozen=True)
class LiquipediaTeamRosterDraft:
    team_name: str
    liquipedia_url: str
    players: list[LiquipediaRosterPlayer]
    warnings: list[str]


@dataclass
class _Link:
    href: str | None
    text: str


@dataclass
class _Cell:
    text: str = ""
    links: list[_Link] = field(default_factory=list)


@dataclass
class _Row:
    cells: list[_Cell] = field(default_factory=list)


@dataclass
class _Table:
    section_heading: str | None
    subsection_heading: str | None
    rows: list[_Row] = field(default_factory=list)


class _LiquipediaHTMLTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[_Table] = []

        self._section_heading: str | None = None
        self._subsection_heading: str | None = None
        self._heading_tag: str | None = None
        self._heading_parts: list[str] = []

        self._table_depth = 0
        self._current_table: _Table | None = None
        self._current_row: _Row | None = None
        self._current_cell: _Cell | None = None

        self._current_link_href: str | None = None
        self._current_link_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)

        if tag in {"h2", "h3", "h4"}:
            self._heading_tag = tag
            self._heading_parts = []
            return

        if tag == "table":
            self._table_depth += 1

            if self._table_depth == 1:
                self._current_table = _Table(
                    section_heading=self._section_heading,
                    subsection_heading=self._subsection_heading,
                )
            return

        if self._table_depth <= 0:
            return

        if tag == "tr" and self._table_depth == 1:
            self._current_row = _Row()
            return

        if tag in {"td", "th"} and self._table_depth == 1 and self._current_row is not None:
            self._current_cell = _Cell()
            return

        if tag == "a" and self._current_cell is not None:
            self._current_link_href = attrs_map.get("href")
            self._current_link_parts = []
            return

    def handle_endtag(self, tag: str) -> None:
        if tag == self._heading_tag:
            heading = _clean_text(" ".join(self._heading_parts))

            if heading:
                if tag == "h2":
                    self._section_heading = heading
                    self._subsection_heading = None
                elif tag in {"h3", "h4"}:
                    self._subsection_heading = heading

            self._heading_tag = None
            self._heading_parts = []
            return

        if tag == "a" and self._current_link_parts is not None:
            link_text = _clean_text(" ".join(self._current_link_parts))

            if self._current_cell is not None and link_text:
                self._current_cell.links.append(
                    _Link(
                        href=self._current_link_href,
                        text=link_text,
                    )
                )

            self._current_link_href = None
            self._current_link_parts = None
            return

        if tag in {"td", "th"} and self._current_cell is not None:
            if self._current_row is not None:
                self._current_cell.text = _clean_text(self._current_cell.text)
                self._current_row.cells.append(self._current_cell)

            self._current_cell = None
            return

        if tag == "tr" and self._current_row is not None:
            if self._current_table is not None and self._current_row.cells:
                self._current_table.rows.append(self._current_row)

            self._current_row = None
            return

        if tag == "table" and self._table_depth > 0:
            if self._table_depth == 1 and self._current_table is not None:
                self.tables.append(self._current_table)
                self._current_table = None

            self._table_depth -= 1
            return

    def handle_data(self, data: str) -> None:
        if self._heading_tag is not None:
            self._heading_parts.append(data)

        if self._current_cell is not None:
            self._current_cell.text += " " + data

        if self._current_link_parts is not None:
            self._current_link_parts.append(data)


def _clean_text(value: str | None) -> str:
    if value is None:
        return ""

    return " ".join(value.replace("\xa0", " ").split()).strip()


def _normalize_page_name(value: str) -> str:
    value = value.strip()

    if value.startswith("https://liquipedia.net/counterstrike/"):
        value = value.removeprefix("https://liquipedia.net/counterstrike/")

    value = value.removeprefix("/counterstrike/")
    value = value.split("#", 1)[0]
    value = value.split("?", 1)[0]
    value = unquote(value)

    return value.replace(" ", "_")


def _page_url(page_name: str) -> str:
    return f"{LIQUIPEDIA_COUNTERSTRIKE_BASE_URL}/{quote(page_name, safe='_/')}"


def _status_from_table_context(table: _Table) -> str | None:
    section = (table.section_heading or "").casefold()
    subsection = (table.subsection_heading or "").casefold()

    # Игроков берём только из Player Roster -> Active.
    # Это не даст взять people/staff из Organization -> Active.
    if "player roster" in section:
        if "active" in subsection:
            return "active"

        return None

    # Из Organization -> Active разрешаем только coach-строки.
    if "organization" in section:
        if "active" in subsection:
            return "coach"

        return None

    return None


def _role_from_text(value: str) -> str | None:
    normalized = value.casefold()

    markers = [
        ("awper", "awper"),
        ("awp", "awper"),
        ("sniper", "awper"),
        ("igl", "igl"),
        ("in-game leader", "igl"),
        ("entry", "entry"),
        ("lurker", "lurker"),
        ("support", "support"),
        ("rifler", "rifler"),
        ("coach", "coach"),
    ]

    for marker, role in markers:
        if marker in normalized:
            return role

    return None


_DATE_RE = re.compile(
    r"(?P<year>20\d{2}|19\d{2})[-/.](?P<month>\d{1,2}|\?\?)[-/.](?P<day>\d{1,2}|\?\?)"
)


def _parse_liquipedia_date(value: str | None) -> date | None:
    if not value:
        return None

    match = _DATE_RE.search(value)

    if match is None:
        return None

    month = match.group("month")
    day = match.group("day")

    if "?" in month or "?" in day:
        return None

    try:
        return date(
            int(match.group("year")),
            int(month),
            int(day),
        )
    except ValueError:
        return None


def _extract_dates_from_row(row_text: str) -> tuple[date | None, date | None]:
    parsed_dates: list[date] = []

    for match in _DATE_RE.finditer(row_text):
        parsed_date = _parse_liquipedia_date(match.group(0))

        if parsed_date is not None:
            parsed_dates.append(parsed_date)

    joined_at = parsed_dates[0] if parsed_dates else None
    left_at = parsed_dates[1] if len(parsed_dates) >= 2 else None

    return joined_at, left_at


def _is_coach_row(row_text: str) -> bool:
    normalized = row_text.casefold()

    blocked_markers = [
        "assistant coach",
        "performance coach",
        "performance department",
        "analyst",
        "manager",
        "coordinator",
        "director",
        "owner",
        "ceo",
        "founder",
        "head of",
        "content",
        "media",
        "editor",
        "designer",
        "photographer",
        "videographer",
        "operations",
        "scout",
        "advisor",
        "ambassador",
        "partnership",
        "marketing",
        "community",
    ]

    if any(marker in normalized for marker in blocked_markers):
        return False

    return (
            "head coach" in normalized
            or " coach" in normalized
            or "coach " in normalized
            or normalized.endswith("coach")
    )


def _is_non_playing_staff_row(row_text: str) -> bool:
    normalized = row_text.casefold()

    if _is_coach_row(row_text):
        return False

    staff_markers = [
        "ceo",
        "chief executive officer",
        "owner",
        "co-owner",
        "founder",
        "co-founder",
        "manager",
        "general manager",
        "team manager",
        "director",
        "head of",
        "analyst",
        "data analyst",
        "performance analyst",
        "performance department",
        "coordinator",
        "content",
        "creator",
        "streamer",
        "media",
        "social media",
        "editor",
        "designer",
        "photographer",
        "videographer",
        "operations",
        "operation",
        "scout",
        "advisor",
        "ambassador",
        "partnership",
        "marketing",
        "community",
    ]

    return any(marker in normalized for marker in staff_markers)


def _is_allowed_roster_status(status: str) -> bool:
    return status in {
        "active",
        "coach",
    }


def _is_counterstrike_player_link(link: _Link) -> bool:
    href = link.href or ""

    if not href.startswith("/counterstrike/"):
        return False

    banned_parts = [
        "/File:",
        "/Category:",
        "/Special:",
        "/Help:",
        "/Liquipedia:",
        "/Template:",
        "/User:",
        "/Talk:",
    ]

    if any(part in href for part in banned_parts):
        return False

    text = _clean_text(link.text)

    if not text:
        return False

    if len(text) > 40:
        return False

    banned_texts = {
        "denmark",
        "russia",
        "ukraine",
        "france",
        "spain",
        "poland",
        "romania",
        "jordan",
        "montenegro",
        "bosnia and herzegovina",
        "north macedonia",
        "serbia",
        "sweden",
        "finland",
        "norway",
        "germany",
        "brazil",
        "united states",
        "canada",
        "kazakhstan",
        "estonia",
        "latvia",
        "lithuania",
        "turkey",
        "israel",
        "china",
        "mongolia",
        "australia",
        "united kingdom",
        "netherlands",
        "belgium",
        "czech republic",
        "slovakia",
    }

    if text.casefold() in banned_texts:
        return False

    return True


def _extract_player_from_row(
        *,
        row: _Row,
        status: str,
        source_url: str,
) -> LiquipediaRosterPlayer | None:
    row_text = _clean_text(" ".join(cell.text for cell in row.cells))

    if not row_text:
        return None

    if not _is_allowed_roster_status(status):
        return None

    if status == "coach" and not _is_coach_row(row_text):
        return None

    if status == "active" and _is_non_playing_staff_row(row_text):
        return None

    normalized_row_text = row_text.casefold()

    # Header rows.
    if (
            any(marker in normalized_row_text for marker in ["id", "name", "join", "role"])
            and len(row.cells) <= 2
    ):
        return None

    links = [
        link
        for cell in row.cells
        for link in cell.links
        if _is_counterstrike_player_link(link)
    ]

    if not links:
        return None

    player_link = links[0]
    nickname = _clean_text(player_link.text)

    if not nickname:
        return None

    href = player_link.href or ""
    liquipedia_url = f"https://liquipedia.net{href}" if href.startswith("/") else href

    role = _role_from_text(row_text)
    joined_at, left_at = _extract_dates_from_row(row_text)

    if status == "coach" or _is_coach_row(row_text) or role == "coach":
        status = "coach"
        role = "coach"

    return LiquipediaRosterPlayer(
        nickname=nickname,
        real_name=None,
        country=None,
        status=status,
        role=role,
        joined_at=joined_at,
        left_at=left_at,
        liquipedia_url=liquipedia_url,
        source_url=source_url,
        source_confidence=0.7,
        notes="Импортировано из Liquipedia MediaWiki API. Берём только Player Roster -> Active и coach из Organization -> Active.",
    )


def _deduplicate_players(players: list[LiquipediaRosterPlayer]) -> list[LiquipediaRosterPlayer]:
    result: list[LiquipediaRosterPlayer] = []
    seen: set[tuple[str, str]] = set()
    coach_added = False

    for player in players:
        if player.status == "coach":
            if coach_added:
                continue

            coach_added = True

        key = (player.nickname.casefold(), player.status)

        if key in seen:
            continue

        seen.add(key)
        result.append(player)

    return result


def parse_liquipedia_team_roster_html(
        *,
        team_name: str,
        page_name: str,
        html: str,
) -> LiquipediaTeamRosterDraft:
    source_url = _page_url(page_name)

    parser = _LiquipediaHTMLTableParser()
    parser.feed(html)

    players: list[LiquipediaRosterPlayer] = []
    warnings: list[str] = []

    for table in parser.tables:
        status = _status_from_table_context(table)

        if status is None:
            continue

        for row in table.rows:
            player = _extract_player_from_row(
                row=row,
                status=status,
                source_url=source_url,
            )

            if player is not None:
                players.append(player)

    players = _deduplicate_players(players)

    active_count = sum(1 for player in players if player.status == "active")

    if active_count == 0:
        warnings.append(
            "Не удалось найти active-состав. Проверь секции Player Roster -> Active на странице Liquipedia.")
    elif active_count < 5:
        warnings.append(f"Найдено меньше 5 active-игроков: {active_count}.")
    elif active_count > 6:
        warnings.append(f"Найдено больше 6 active-игроков: {active_count}. Нужно проверить разметку Liquipedia.")

    if not any(player.role == "awper" for player in players if player.status == "active"):
        warnings.append("AWPer не найден автоматически. Возможно, роль нужно указать вручную.")

    if not any(player.role == "igl" for player in players if player.status == "active"):
        warnings.append("IGL не найден автоматически. Возможно, роль нужно указать вручную.")

    return LiquipediaTeamRosterDraft(
        team_name=team_name,
        liquipedia_url=source_url,
        players=players,
        warnings=warnings,
    )


async def fetch_liquipedia_team_roster(
        *,
        team_page: str,
        team_name: str | None = None,
) -> LiquipediaTeamRosterDraft:
    page_name = _normalize_page_name(team_page)
    resolved_team_name = team_name.strip() if team_name else page_name.replace("_", " ")

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            LIQUIPEDIA_COUNTERSTRIKE_API_URL,
            params={
                "action": "parse",
                "page": page_name,
                "prop": "text|displaytitle",
                "format": "json",
                "formatversion": "2",
            },
            headers={
                "User-Agent": LIQUIPEDIA_USER_AGENT,
                "Accept-Encoding": "gzip",
            },
        )

    response.raise_for_status()
    payload = response.json()

    if "error" in payload:
        error = payload["error"]
        raise ValueError(error.get("info") or error.get("code") or "Liquipedia API error")

    parse_payload = payload.get("parse") or {}
    html = parse_payload.get("text") or ""
    display_title = _clean_text(parse_payload.get("displaytitle"))

    if display_title and team_name is None:
        resolved_team_name = display_title

    if not html:
        raise ValueError("Liquipedia returned empty page content")

    return parse_liquipedia_team_roster_html(
        team_name=resolved_team_name,
        page_name=page_name,
        html=html,
    )


def liquipedia_draft_to_team_payload(
        draft: LiquipediaTeamRosterDraft,
) -> dict:
    return {
        "name": draft.team_name,
        "country": None,
        "region": None,
        "liquipedia_url": draft.liquipedia_url,
        "hltv_id": None,
        "players": [
            {
                "nickname": player.nickname,
                "real_name": player.real_name,
                "country": player.country,
                "status": player.status,
                "role": player.role,
                "joined_at": player.joined_at,
                "left_at": player.left_at,
                "liquipedia_url": player.liquipedia_url,
                "hltv_id": None,
                "current_rating": None,
                "player_strength_score": None,
                "source_name": "liquipedia",
                "source_url": player.source_url,
                "source_confidence": player.source_confidence,
                "notes": player.notes,
            }
            for player in draft.players
        ],
    }
