"""ROSClaw Ecology Crawler - Utilities (Deduplication, Normalization, Embodied Filter)"""

import re
from urllib.parse import urlparse
from typing import List, Optional, Tuple

from config import ALL_EMBODIED_KEYWORDS


def normalize_github_url(url: str) -> str:
    """
    Normalize a GitHub URL to be used as the deduplication key.
    Removes .git suffix, trailing slashes, forces lowercase,
    and strips protocol/www prefixes to a canonical github.com/user/repo form.
    Returns empty string for known non-repo paths (e.g. user-attachments, features).
    """
    url = url.strip().lower()
    url = url.replace("www.github.com", "github.com")
    url = url.replace("http://", "https://")
    if url.endswith(".git"):
        url = url[:-4]
    if url.endswith("/"):
        url = url[:-1]
    # Keep only github.com/owner/repo — drop tree, blob, etc.
    parsed = urlparse(url)
    if parsed.netloc == "github.com":
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            if parts[0] in BLOCKED_GITHUB_PATHS or parts[1] in BLOCKED_GITHUB_PATHS:
                return ""
            return f"https://github.com/{parts[0]}/{parts[1]}"
    return url


def extract_repo_owner_name(url: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract (owner, repo_name) from a normalized GitHub URL."""
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None, None


def classify_embodied(text: Optional[str]) -> Tuple[bool, List[str]]:
    """
    Simple keyword-based classifier to flag resources related to
    robotics / embodied AI / physical AI.
    Returns (is_embodied: bool, matched_tags: list)
    """
    if not text:
        return False, []
    text_lower = text.lower()
    matched = []
    for keyword in ALL_EMBODIED_KEYWORDS:
        if keyword.lower() in text_lower:
            matched.append(keyword)
    # Deduplicate matched tags while preserving order
    seen = set()
    unique_matched = []
    for tag in matched:
        if tag.lower() not in seen:
            seen.add(tag.lower())
            unique_matched.append(tag)
    return len(unique_matched) > 0, unique_matched


def guess_resource_type(name: Optional[str], description: Optional[str], source: str) -> str:
    """Heuristic to guess whether a resource is an MCP server or an Agent Skill."""
    text = f"{name or ''} {description or ''} {source}".lower()
    if "mcp" in text or "model context protocol" in text:
        return "mcp_server"
    if "skill" in text or "agent" in text or "plugin" in text:
        return "agent_skill"
    return "mcp_server"  # Default fallback


GITHUB_RAW_MIRRORS = [
    "https://raw.githubusercontent.com",
    "https://ghfast.top/https://raw.githubusercontent.com",
]


def resolve_github_raw_readme(owner: str, repo: str, branch: str = "main") -> str:
    """Build a raw.githubusercontent.com URL for the default README."""
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"


def resolve_github_raw_readme_with_mirror(owner: str, repo: str, branch: str = "main") -> list:
    """Return list of possible raw README URLs with mirrors."""
    return [f"{mirror}/{owner}/{repo}/{branch}/README.md" for mirror in GITHUB_RAW_MIRRORS]


# Regex to find markdown list items that contain GitHub links
GITHUB_REPO_LINK_RE = re.compile(
    r"https?://(?:www\.)?github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+"
)

# Paths that look like /owner/repo but are actually GitHub platform pages
BLOCKED_GITHUB_PATHS = {
    "user-attachments", "features", "marketplace", "mobile", "topics",
    "enterprises", "organizations", "team", "explore", "pricing",
    "search", "settings", "security", "login", "signup", "logout",
    "collections", "trending", "events", "sponsors",
}


def is_valid_github_repo_url(url: str) -> bool:
    """Return False if the URL is a known GitHub non-repo path."""
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2:
        return False
    if parts[0].lower() in BLOCKED_GITHUB_PATHS or parts[1].lower() in BLOCKED_GITHUB_PATHS:
        return False
    return True
