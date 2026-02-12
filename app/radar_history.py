"""Load and search historical Technology Radar blip data.

Data source: https://github.com/setchy/thoughtworks-tech-radar-volumes
CSV columns: name, ring, quadrant, isNew, status, description
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.config import RADAR_HISTORY_DIR
from app.models import HistoricalBlip
from app.sanitization import sanitize_external_data

logger = logging.getLogger(__name__)

_GITHUB_API_URL = (
    "https://api.github.com/repos/"
    "setchy/thoughtworks-tech-radar-volumes/contents/volumes/csv"
)
_GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/"
    "setchy/thoughtworks-tech-radar-volumes/main/volumes/csv/"
)

# In-memory cache of all historical blips
_history: list[HistoricalBlip] = []
_history_loaded_at: float = 0.0

# Cache TTL: reload from disk/network after 24 hours
CACHE_TTL_SECONDS = 86400

# Rate limiting: minimum seconds between GitHub API requests
_last_github_request: float = 0.0
MIN_REQUEST_INTERVAL = 1.0  # At least 1 second between requests


def _rate_limit_wait() -> None:
    """Ensure we don't exceed GitHub's rate limits."""
    global _last_github_request
    elapsed = time.time() - _last_github_request
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    _last_github_request = time.time()


def _fetch_with_retry(url: str, headers: dict, max_retries: int = 3) -> bytes:
    """Fetch URL with exponential backoff retry."""
    last_error = None
    for attempt in range(max_retries):
        try:
            _rate_limit_wait()
            req = urllib.request.Request(url)
            for key, value in headers.items():
                req.add_header(key, value)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 403:  # Rate limited
                retry_after = int(e.headers.get("Retry-After", 60))
                logger.warning("GitHub rate limit hit, waiting %d seconds", retry_after)
                time.sleep(min(retry_after, 300))  # Cap at 5 minutes
            elif e.code >= 500:  # Server error, retry
                wait_time = (2 ** attempt) * 1.0  # Exponential backoff
                logger.warning("GitHub server error %d, retrying in %.1fs", e.code, wait_time)
                time.sleep(wait_time)
            else:
                raise
        except urllib.error.URLError as e:
            last_error = e
            wait_time = (2 ** attempt) * 1.0
            logger.warning("Network error fetching %s, retrying in %.1fs: %s", url, wait_time, e)
            time.sleep(wait_time)

    raise last_error or Exception(f"Failed to fetch {url} after {max_retries} retries")


def _volume_label(filename: str) -> str:
    """Extract a short volume label from the filename.

    'Thoughtworks Technology Radar Volume 31 (Oct 2024).csv'
    -> 'Volume 31 (Oct 2024)'
    """
    match = re.search(r"(Volume \d+ \([^)]+\))", filename)
    return match.group(1) if match else filename


def _fetch_csv_listing() -> list[str]:
    """Get the list of CSV filenames from the GitHub API."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "tw-radar-blip-tool",
    }
    data = _fetch_with_retry(_GITHUB_API_URL, headers)
    entries = json.loads(data.decode())
    return [e["name"] for e in entries if e["name"].endswith(".csv")]


def _fetch_csv(filename: str) -> str:
    """Download a single CSV file from GitHub raw."""
    url = _GITHUB_RAW_BASE + urllib.request.quote(filename)
    headers = {"User-Agent": "tw-radar-blip-tool"}
    data = _fetch_with_retry(url, headers)
    return data.decode("utf-8")


def _parse_csv(content: str, volume: str) -> list[HistoricalBlip]:
    """Parse CSV content into HistoricalBlip objects.

    External data is sanitized to prevent prompt injection attacks.
    """
    reader = csv.DictReader(io.StringIO(content))
    blips = []
    for row in reader:
        # Sanitize all external data
        name = sanitize_external_data(row.get("name", "").strip())
        if not name:
            continue
        blips.append(
            HistoricalBlip(
                name=name,
                ring=sanitize_external_data(row.get("ring", "").strip().capitalize()),
                quadrant=_normalize_quadrant(row.get("quadrant", "")),
                volume=sanitize_external_data(volume),
            )
        )
    return blips


def _normalize_quadrant(raw: str) -> str:
    """Normalize CSV quadrant values to display form.

    CSV uses lowercase hyphenated forms like 'languages-and-frameworks'.
    """
    raw = raw.strip().lower()
    mapping = {
        "techniques": "Techniques",
        "tools": "Tools",
        "platforms": "Platforms",
        "languages-and-frameworks": "Languages & Frameworks",
    }
    return mapping.get(raw, raw.title())


def _cache_path(filename: str) -> Path:
    return RADAR_HISTORY_DIR / filename


def load_history(force_refresh: bool = False) -> list[HistoricalBlip]:
    """Load all historical blips, fetching from GitHub if not cached.

    Results are cached in memory after the first load, with a TTL of 24 hours.
    """
    global _history, _history_loaded_at

    # Check if cache is still valid
    cache_age = time.time() - _history_loaded_at
    cache_expired = cache_age > CACHE_TTL_SECONDS

    if _history and not force_refresh and not cache_expired:
        return _history

    RADAR_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    # Check for locally cached CSV files first
    cached_files = sorted(RADAR_HISTORY_DIR.glob("*.csv"))

    if not cached_files or force_refresh:
        filenames = _fetch_csv_listing()
        for fname in filenames:
            cache = _cache_path(fname)
            if not cache.exists() or force_refresh:
                content = _fetch_csv(fname)
                cache.write_text(content, encoding="utf-8")
        cached_files = sorted(RADAR_HISTORY_DIR.glob("*.csv"))

    all_blips: list[HistoricalBlip] = []
    for csv_path in cached_files:
        volume = _volume_label(csv_path.name)
        content = csv_path.read_text(encoding="utf-8")
        all_blips.extend(_parse_csv(content, volume))

    _history = all_blips
    _history_loaded_at = time.time()
    return _history


def find_matching_blips(name: str) -> list[HistoricalBlip]:
    """Find historical blips matching the given name.

    Uses case-insensitive exact match first, then falls back to
    substring matching. Returns all appearances across editions,
    sorted by volume.
    """
    if not _history:
        load_history()

    normalized = name.strip().lower()
    if not normalized:
        return []

    # Exact match (case-insensitive)
    exact = [b for b in _history if b.name.strip().lower() == normalized]
    if exact:
        return sorted(exact, key=lambda b: b.volume)

    # Substring match — the query is contained in a blip name or vice versa
    partial = [
        b
        for b in _history
        if normalized in b.name.strip().lower()
        or b.name.strip().lower() in normalized
    ]
    return sorted(partial, key=lambda b: b.volume)


def refresh_history() -> int:
    """Re-fetch all history from GitHub. Returns count of blips loaded."""
    blips = load_history(force_refresh=True)
    return len(blips)
