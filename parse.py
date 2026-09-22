import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from threading import BoundedSemaphore, Lock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
from github import Auth, Github

from scripts.readme_entries import (
    BADGE_RE,
    ENTRY_RE,
    HEADING_RE,
    extract_languages,
    slugify,
)

_github_client = None
_REPO_CACHE: dict = {}
_REPO_CACHE_LOCK = Lock()
# Bound concurrent repo-page requests so token-free runs do not trip
# GitHub's abuse-rate limiting.
_SCRAPE_SLOTS = BoundedSemaphore(4)
_SCRAPE_UA = "awesome-quant-bot (metadata check)"
# Transient codes worth retrying; GitHub signals burst-throttling via 429/403.
_RETRYABLE = frozenset({403, 429, 500, 502, 503, 504})


def _fetch_text(url, attempts=4, timeout=20):
    """GET `url` as text with jittered exponential backoff on retryable codes."""
    delay = 5.0
    for attempt in range(attempts):
        try:
            req = Request(url, headers={"User-Agent": _SCRAPE_UA})
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except HTTPError as e:
            if e.code in _RETRYABLE and attempt < attempts - 1:
                retry_after = e.headers.get("Retry-After") if e.headers else None
                if retry_after and str(retry_after).isdigit():
                    wait = float(retry_after)
                else:
                    wait = delay
                time.sleep(wait + random.uniform(0, 2))
                delay = min(delay * 2, 60)
                continue
            raise
        except (URLError, TimeoutError, OSError):
            # Transient transport failures (DNS, resets, timeouts, TLS) —
            # retry with the same backoff as retryable statuses.
            if attempt < attempts - 1:
                time.sleep(delay + random.uniform(0, 2))
                delay = min(delay * 2, 60)
                continue
            raise
    return ""


def get_github_client():
    """Create the GitHub client lazily so importing this module is token-free."""
    global _github_client  # noqa: PLW0603
    if _github_client is None:
        auth = Auth.Token(os.environ["GITHUB_ACCESS_TOKEN"])
        _github_client = Github(auth=auth)
    return _github_client


def _parse_star_count(text):
    """Normalize a star count like '20,948' or '63.7k' to an int."""
    text = text.strip().lower().rstrip(".,+")
    try:
        if text.endswith("k"):
            return int(float(text[:-1]) * 1000)
        if text.endswith("m"):
            return int(float(text[:-1]) * 1_000_000)
        return int(text.replace(",", ""))
    except ValueError:
        return 0


def get_repo_info_scrape(repo):
    """Fetch last commit date, stars, and archived flag from the repo's
    github.com page. Token-free fallback for `get_repo_info`.

    Returns (last_commit, stars, archived); empty/0/False on failure.
    """
    with _SCRAPE_SLOTS:
        try:
            page = _fetch_text(f"https://github.com/{repo}")
        except Exception as e:
            print(f"SCRAPE ERROR {repo}: {e}")
            return "error", 0, False

    stars = 0
    m = re.search(
        r'id="repo-stars-counter-star"[^>]*(?:title|aria-label)="([^"]+)"',
        page,
    )
    if not m:
        m = re.search(r'"stargazerCount"\s*:\s*(\d+)', page)
    if m:
        stars = _parse_star_count(m.group(1))

    # The repo page lazy-loads commit history; the commits Atom feed is the
    # cheap canonical source for the default branch's last commit date.
    last_commit = ""
    with _SCRAPE_SLOTS:
        try:
            feed = _fetch_text(f"https://github.com/{repo}/commits.atom")
            m = re.search(r"<updated>(\d{4}-\d{2}-\d{2})", feed)
            if m:
                last_commit = m.group(1)
        except Exception:
            last_commit = ""  # feed unreadable; fall through with stars only

    archived = bool(
        re.search(r"This repository has been archived", page)
        or re.search(r'"isArchived"\s*:\s*true', page)
        or re.search(r'"archived"\s*:\s*true', page)
    )
    return last_commit, stars, archived


def extract_repo(url):
    reu = re.compile(r"^https://github\.com/([\w-]+/[-\w\.]+?)/?(?:\.git)?$")
    m = reu.match(url)
    if m:
        return m.group(1)
    else:
        return ""


def extract_github_url(description):
    """Extract GitHub URL from description if present."""
    github_pattern = re.compile(r"\[GitHub\]\((https://github\.com/[\w-]+/[-\w\.]+)\)")
    m = github_pattern.search(description)
    if m:
        return m.group(1)
    return ""


def get_cran_info(url):
    """Fetch Published date and GitHub URL from a CRAN package page.

    Returns (published_date, github_url) — either may be empty string.
    """
    try:
        m = re.search(r"package=(\w+)", url) or re.search(
            r"/packages/(\w+)", url
        )
        if not m:
            return "", ""
        pkg = m.group(1)
        page_url = f"https://cran.r-project.org/web/packages/{pkg}/index.html"
        with urlopen(page_url, timeout=10) as resp:
            page_html = resp.read().decode("utf-8", errors="replace")

        class CranParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self._in_td = False
                self._found_published = False
                self._in_github_span = False
                self.date = ""
                self.github_url = ""

            def handle_starttag(self, tag, attrs):
                if tag == "td":
                    self._in_td = True
                # GitHub links are wrapped in <span class="GitHub">
                if tag == "span":
                    classes = dict(attrs).get("class", "")
                    if "GitHub" in classes:
                        self._in_github_span = True
                # Also check <a href> for github.com links
                if tag == "a" and not self.github_url:
                    href = dict(attrs).get("href", "")
                    if "github.com" in href and "/issues" not in href:
                        self.github_url = href

            def handle_endtag(self, tag):
                if tag == "td":
                    self._in_td = False
                if tag == "span":
                    self._in_github_span = False

            def handle_data(self, data):
                if self._in_td:
                    if data.strip() == "Published:":
                        self._found_published = True
                    elif self._found_published and not self.date:
                        d = data.strip()
                        if re.match(r"\d{4}-\d{2}-\d{2}", d):
                            self.date = d

        parser = CranParser()
        parser.feed(page_html)
        # Clean trailing slashes or .git from GitHub URL
        gh = parser.github_url.rstrip("/")
        gh = gh.removesuffix(".git")
        return parser.date, gh
    except Exception as e:
        print(f"CRAN ERROR {url}: {e}")
        return "", ""


def get_pypi_last_updated(url):
    """Fetch the last release date from PyPI JSON API."""
    try:
        # Extract package name from URL like https://pypi.org/project/tushare/
        m = re.search(r"pypi\.org/project/([\w.-]+)", url) or re.search(
            r"pypi\.python\.org/pypi/([\w.-]+)", url
        )
        if not m:
            return ""
        pkg = m.group(1).rstrip("/")
        api_url = f"https://pypi.org/pypi/{pkg}/json"
        with urlopen(api_url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        releases = data.get("releases", {})
        if not releases:
            return ""

        # Newest upload across all files — release keys sort lexically
        # ("9.9" > "10.0"), so they are not a reliable ordering.
        upload_times = [
            file.get("upload_time_iso_8601", "")
            for release_data in releases.values()
            for file in release_data
        ]
        upload_times = [t for t in upload_times if t]
        return max(upload_times).split("T")[0] if upload_times else ""
    except Exception as e:
        print(f"PYPI ERROR {url}: {e}")
        return ""


def get_repo_info(repo):
    """Fetch last commit date, star count, and archived flag for a repo.

    Uses the GitHub API when GITHUB_ACCESS_TOKEN is set; otherwise falls
    back to scraping the repo's github.com page (token-free). Results are
    cached so repeated references to one repo only fetch it once.

    Returns (last_commit, stars, archived).
    """
    if not repo:
        return "", 0, False
    with _REPO_CACHE_LOCK:
        if repo in _REPO_CACHE:
            return _REPO_CACHE[repo]
    if os.environ.get("GITHUB_ACCESS_TOKEN"):
        result = _get_repo_info_api(repo)
    else:
        result = get_repo_info_scrape(repo)
    with _REPO_CACHE_LOCK:
        _REPO_CACHE[repo] = result
    return result


def _get_repo_info_api(repo):
    """Fetch last commit date, star count, and archived flag via the API."""
    try:
        r = get_github_client().get_repo(repo)
        cs = r.get_commits()
        last_commit = cs[0].commit.author.date.strftime("%Y-%m-%d")
        return last_commit, r.stargazers_count, bool(r.archived)
    except Exception:
        print("ERROR " + repo)
        return "error", 0, False


class Project:
    def __init__(self, match, language, category, section_path):
        self._match = match
        self.regs = None
        self._language = language
        self._category = category
        self._section_path = section_path
        self.languages = []
        self.clean_description = ""

    def run(self):
        m = self._match
        primary_url = m.group(2)
        # Use clean_description if it was set by the parser, otherwise extract from match
        description = self.clean_description or m.group(3)

        # Check if primary URL is GitHub
        is_github = "github.com" in primary_url

        # If not GitHub, check if there's a GitHub link in the description
        github_url = extract_github_url(description) if not is_github else primary_url

        is_cran = "cran.r-project.org" in primary_url
        is_pypi = "pypi.org" in primary_url or "pypi.python.org" in primary_url
        is_commercial = self._category == "Commercial & Proprietary Services"

        # For CRAN projects, scrape the CRAN page for GitHub URL and published date
        cran_date = ""
        if is_cran:
            cran_date, cran_github = get_cran_info(primary_url)
            if cran_github and not github_url:
                github_url = cran_github

        repo = extract_repo(github_url)
        print(repo or primary_url)
        last_commit, stars, archived = get_repo_info(repo)

        # Fallback: use CRAN/PyPI dates when no GitHub data
        if not last_commit or last_commit == "error":
            if is_cran and cran_date:
                last_commit = cran_date
            elif is_pypi:
                pypi_date = get_pypi_last_updated(primary_url)
                if pypi_date:
                    last_commit = pypi_date
        if last_commit == "error":
            last_commit = ""

        # Build section slug from category or language
        section_slug = slugify(self._category or self._language)

        self.regs = {
            "project": m.group(1),
            "language": self._language,
            "languages": ",".join(self.languages),
            "category": self._category,
            "section": self._section_path,
            "section_slug": section_slug,
            "last_commit": last_commit,
            "stars": stars,
            "archived": archived,
            "url": primary_url,
            "description": description,
            "github": is_github or bool(github_url),
            "cran": is_cran,
            "pypi": is_pypi,
            "commercial": is_commercial,
            "repo": repo,
        }


def main():
    projects = []

    with open("README.md", encoding="utf8") as f:
        ret = HEADING_RE
        rex = ENTRY_RE
        re_badge = BADGE_RE
        current_category = ""
        for raw_line in f:
            line = re_badge.sub(" ", raw_line)
            m = rex.match(line)
            if m:
                raw_desc = m.group(3).strip()

                # Extract language tags from description
                languages, clean_description = extract_languages(raw_desc)
                primary_language = languages[0] if languages else ""

                p = Project(
                    m,
                    primary_language,
                    current_category,
                    current_category,
                )
                p.languages = languages
                p.clean_description = clean_description
                projects.append(p)
            else:
                m = ret.match(line)
                if m:
                    hrs = m.group(1)
                    title = m.group(2).strip()
                    if len(hrs) == 2 and title != "Contents":
                        current_category = title

    # Bound the worker pool: one thread per entry (~700) spikes memory and
    # leaves non-GitHub fetches unbounded; 8 is plenty for I/O-bound work.
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(p.run) for p in projects]
        for future in futures:
            future.result()

    missing = [p for p in projects if p.regs is None]
    if missing:
        raise SystemExit(f"{len(missing)} project(s) failed to produce data")

    projects = [p.regs for p in projects]
    df = pd.DataFrame(projects)
    df.to_csv("site/projects.csv", index=False)


if __name__ == "__main__":
    main()
