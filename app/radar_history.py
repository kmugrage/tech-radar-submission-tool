"""Load and search historical Technology Radar blip data.

Data source: https://github.com/setchy/thoughtworks-tech-radar-volumes
CSV columns: name, ring, quadrant, isNew, status, description
"""

from __future__ import annotations

import csv
import io
import re
import urllib.request
from pathlib import Path

from app.config import RADAR_HISTORY_DIR
from app.models import HistoricalBlip

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


def _volume_label(filename: str) -> str:
    """Extract a short volume label from the filename.

    'Thoughtworks Technology Radar Volume 31 (Oct 2024).csv'
    -> 'Volume 31 (Oct 2024)'
    """
    match = re.search(r"(Volume \d+ \([^)]+\))", filename)
    return match.group(1) if match else filename


def _fetch_csv_listing() -> list[str]:
    """Get the list of CSV filenames from the GitHub API."""
    import json

    req = urllib.request.Request(_GITHUB_API_URL)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "tw-radar-blip-tool")
    with urllib.request.urlopen(req, timeout=30) as resp:
        entries = json.loads(resp.read().decode())
    return [e["name"] for e in entries if e["name"].endswith(".csv")]


def _fetch_csv(filename: str) -> str:
    """Download a single CSV file from GitHub raw."""
    url = _GITHUB_RAW_BASE + urllib.request.quote(filename)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "tw-radar-blip-tool")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _parse_csv(content: str, volume: str) -> list[HistoricalBlip]:
    """Parse CSV content into HistoricalBlip objects."""
    reader = csv.DictReader(io.StringIO(content))
    blips = []
    for row in reader:
        name = row.get("name", "").strip()
        if not name:
            continue
        blips.append(
            HistoricalBlip(
                name=name,
                ring=row.get("ring", "").strip().capitalize(),
                quadrant=_normalize_quadrant(row.get("quadrant", "")),
                volume=volume,
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

    Results are cached in memory after the first load.
    """
    global _history
    if _history and not force_refresh:
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
