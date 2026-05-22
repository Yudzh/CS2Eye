import re
from urllib.parse import urljoin, urlparse

import httpx


HLTV_BASE_URL = "https://www.hltv.org"

DEMO_DOWNLOAD_LINK_PATTERN = re.compile(
    r'href="(?P<href>/download/demo/\d+)"'
)


def _validate_hltv_match_url(match_url: str) -> None:
    parsed_url = urlparse(match_url)

    if parsed_url.netloc not in {"www.hltv.org", "hltv.org"}:
        raise ValueError("Only HLTV match URLs are supported")

    if not parsed_url.path.startswith("/matches/"):
        raise ValueError("URL must be an HLTV match URL")


def _extract_demo_download_url(html: str) -> str:
    match = DEMO_DOWNLOAD_LINK_PATTERN.search(html)

    if match is None:
        raise ValueError("Demo download link was not found on HLTV match page")

    download_path = match.group("href")

    return urljoin(HLTV_BASE_URL, download_path)


async def _resolve_archive_url(
    client: httpx.AsyncClient,
    download_url: str,
) -> str | None:
    response = await client.get(download_url, follow_redirects=False)

    if response.is_redirect:
        location = response.headers.get("location")

        if location:
            return urljoin(HLTV_BASE_URL, location)

    return None


async def resolve_hltv_demo_url(match_url: str) -> dict[str, str | None]:
    _validate_hltv_match_url(match_url)

    headers = {
        "User-Agent": "Mozilla/5.0 CS2Eye/0.1",
    }

    async with httpx.AsyncClient(
        timeout=30.0,
        headers=headers,
        follow_redirects=True,
    ) as client:
        match_page_response = await client.get(match_url)
        match_page_response.raise_for_status()

        download_url = _extract_demo_download_url(match_page_response.text)
        archive_url = await _resolve_archive_url(client, download_url)

    return {
        "match_url": match_url,
        "download_url": download_url,
        "archive_url": archive_url,
    }