#!/usr/bin/env python3
"""Parse README.md and generate a static HTML site for awesome-quant.

Can run in two modes:
1. With projects.csv (produced by parse.py) — includes stars, last commit, etc.
2. Without CSV — parses README.md directly for a quick local preview.
"""

import csv
import html
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.readme_entries import (
    GITHUB_LINK_RE,
    iter_readme_entries,
    slugify,
)

# Repo that this deployment's site links back to (Submit a Project, GitHub,
# Contribute). Overridable for previews/forks via env var.
REPO_SLUG = os.environ.get("SITE_REPO_SLUG", "sharmapriyank/awesome-quant")
REPO_URL = f"https://github.com/{REPO_SLUG}"
REPO_CONTRIBUTING_URL = f"{REPO_URL}/blob/master/CONTRIBUTING.md"
MAINTAINER_NAME = os.environ.get("SITE_MAINTAINER_NAME", "sharmapriyank")
MAINTAINER_URL = os.environ.get("SITE_MAINTAINER_URL", "https://github.com/sharmapriyank")

# Backtick tags that denote a programming language or language runtime — used
# for the hero "N languages" stat and the tag cloud's language bucket. Topic
# and format tags (MCP, REST, Historical, Papers, ...) stay filterable via
# row pills but do not inflate the language count.
PROGRAMMING_LANGUAGES = frozenset({
    "C#", "C++", "Elixir/Erlang", "Go", "Haskell", "Java", "JavaScript",
    "Julia", "Kotlin", "Matlab", "Node.js", "PHP", "Pine Script",
    "Python", "R", "Ruby", "Rust", "Scala", "TypeScript", "WebAssembly",
})

NON_LANGUAGE_TAGS = frozenset({
    "Commercial & Proprietary Services",
    "Related Lists",
    "Reproducing Works, Training & Books",
    "Cross-Language Frameworks",
})


def parse_readme(path: str) -> list[dict]:
    """Parse README.md for a quick preview (no API data).

    Uses the shared `iter_readme_entries` parser so preview output matches
    the CSV pipeline exactly.
    """
    entries = []
    for entry in iter_readme_entries(path):
        gh_match = GITHUB_LINK_RE.search(entry.description)
        if gh_match:
            github_url = gh_match.group(1)
            desc = GITHUB_LINK_RE.sub("", entry.description).rstrip(". ").rstrip() + "."
        elif "github.com" in entry.url:
            github_url = entry.url
            desc = entry.description
        else:
            github_url = ""
            desc = entry.description

        repo = ""
        if github_url:
            repo_match = re.match(
                r"https://github\.com/([\w-]+/[-\w\.]+)", github_url
            )
            if repo_match:
                repo = repo_match.group(1)

        entries.append(
            {
                "project": entry.name,
                "language": entry.languages[0] if entry.languages else "",
                "languages": ",".join(entry.languages),
                "category": entry.section,
                "section_slug": slugify(entry.section),
                "url": entry.url,
                "description": desc,
                "github": bool(github_url),
                "cran": "cran.r-project.org" in entry.url,
                "pypi": "pypi.org" in entry.url or "pypi.python.org" in entry.url,
                "commercial": entry.section == "Commercial & Proprietary Services",
                "github_url": github_url,
                "repo": repo,
                "stars": 0,
                "last_commit": "",
                "archived": False,
            }
        )
    return entries


def load_csv(path: str) -> list[dict]:
    """Load projects from CSV produced by parse.py."""
    entries = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Normalize booleans
            for key in ("github", "cran", "pypi", "commercial", "archived"):
                row[key] = str(row.get(key, "")).lower() in ("true", "1", "yes")
            # Normalize numbers
            row["stars"] = int(float(row.get("stars", 0) or 0))
            # Extract github_url and repo from CSV data
            repo = row.get("repo", "")
            row["github_url"] = f"https://github.com/{repo}" if repo else ""
            # Ensure languages column exists
            row["languages"] = row.get("languages", row.get("language", ""))
            # Clean description: strip [GitHub](url) if present
            desc = row.get("description", "")
            desc = re.sub(
                r"\s*\[GitHub\]\(https://github\.com/[\w-]+/[-\w\.]+\)\s*",
                "",
                desc,
            )
            desc = desc.rstrip(". ").rstrip()
            if desc and not desc.endswith("."):
                desc += "."
            row["description"] = desc
            entries.append(row)
    return entries


def format_stars(n: int) -> str:
    """Format star count for display."""
    if n >= 1000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return str(n) if n > 0 else ""


def build_tags_html(e: dict) -> str:
    """Build tag pills for an entry."""
    esc = html.escape
    tags = []

    # Language tags (from inline backtick tags)
    languages_str = e.get("languages", e.get("language", ""))
    languages = [l.strip() for l in languages_str.split(",") if l.strip()]
    for lang in languages:
        if lang and lang not in NON_LANGUAGE_TAGS:
            tags.append(
                f'<button class="tag tag-lang" data-filter-type="language" '
                f'data-filter-value="{esc(lang)}">{esc(lang.lower())}</button>'
            )

    # Category tag
    category = e.get("category", "")
    section_slug = e.get("section_slug", "")
    if section_slug:
        tags.append(
            f'<button class="tag tag-section" data-filter-type="category" '
            f'data-filter-value="{esc(category)}">{esc(section_slug)}</button>'
        )

    # Source tags (unchanged)
    if e.get("github"):
        tags.append(
            '<button class="tag tag-source tag-github" '
            'data-filter-type="source" data-filter-value="github">github</button>'
        )
    if e.get("cran"):
        tags.append(
            '<button class="tag tag-source tag-cran" '
            'data-filter-type="source" data-filter-value="cran">cran</button>'
        )
    if e.get("pypi"):
        tags.append(
            '<button class="tag tag-source tag-pypi" '
            'data-filter-type="source" data-filter-value="pypi">pypi</button>'
        )
    if e.get("commercial"):
        tags.append(
            '<button class="tag tag-source tag-commercial" '
            'data-filter-type="source" data-filter-value="commercial">commercial</button>'
        )
    if e.get("archived"):
        tags.append(
            '<button class="tag tag-source tag-archived" '
            'data-filter-type="source" data-filter-value="archived">archived</button>'
        )

    return "\n          ".join(tags)


def build_tag_cloud(entries: list[dict]) -> str:
    """Build a tag cloud of popular languages and categories."""
    # Count language frequencies (real programming languages only)
    lang_counts: Counter = Counter()
    for e in entries:
        langs = [l.strip() for l in e.get("languages", e.get("language", "")).split(",") if l.strip()]
        lang_counts.update(langs)

    for tag in list(lang_counts):
        if tag not in PROGRAMMING_LANGUAGES:
            del lang_counts[tag]

    # Count category frequencies
    cat_counts = Counter(e.get("category", "") for e in entries if e.get("category"))

    # Get top items
    top_langs = lang_counts.most_common(8)  # Top 8 languages
    top_cats = cat_counts.most_common(6)    # Top 6 categories

    if not top_langs and not top_cats:
        return ""

    # Combine and sort by frequency
    all_items = []
    for lang, count in top_langs:
        all_items.append(("language", lang, count))
    for cat, count in top_cats:
        all_items.append(("category", cat, count))

    # Sort by count descending
    all_items.sort(key=lambda x: x[2], reverse=True)

    # Calculate size scale (1.0 to 1.6x)
    if all_items:
        min_count = min(item[2] for item in all_items)
        max_count = max(item[2] for item in all_items)
        count_range = max_count - min_count if max_count > min_count else 1
    else:
        min_count = max_count = count_range = 1

    tags = []
    esc = html.escape
    for tag_type, value, count in all_items:
        # Calculate font size: 1.0 to 1.6
        size = 1.0 + ((count - min_count) / count_range * 0.6) if count_range > 0 else 1.0

        label = esc(value.lower()) if tag_type == "language" else esc(value)
        cls = "tag-lang" if tag_type == "language" else "tag-section"
        tags.append(
            f'<button class="tag {cls} tag-cloud-item" '
            f'data-filter-type="{tag_type}" data-filter-value="{esc(value)}" '
            f'style="font-size: {size:.2f}em;">'
            f'{label} <span class="cloud-count">{count}</span></button>'
        )

    if not tags:
        return ""

    return f"""        <div class="tag-cloud">
          <div class="tag-cloud-label">Popular filters:</div>
          <div class="tag-cloud-items">
            {chr(10).join("            " + tag for tag in tags)}
          </div>
        </div>"""


def generate_html(entries: list[dict]) -> str:
    """Generate the full HTML page from project entries."""
    languages = sorted(
        {
            lang.strip()
            for e in entries
            for lang in e.get("languages", e.get("language", "")).split(",")
            if lang.strip() in PROGRAMMING_LANGUAGES
        }
    )

    # Generate tag cloud
    tag_cloud_html = build_tag_cloud(entries)

    def safe_href(url: str) -> str:
        scheme = url.split(":", 1)[0].lower()
        return url if scheme in {"http", "https"} else ""

    # Build table rows
    rows = []
    for i, e in enumerate(entries, 1):
        esc = html.escape
        name = esc(e["project"])
        url = esc(safe_href(e["url"]))
        desc = esc(e["description"])
        category = esc(e.get("category", ""))
        github_url = esc(safe_href(e.get("github_url", "")))
        stars = int(e.get("stars", 0) or 0)
        last_commit = e.get("last_commit", "") or ""
        is_github = e.get("github", False)
        is_cran = e.get("cran", False)
        is_pypi = e.get("pypi", False)
        is_commercial = e.get("commercial", False)
        is_archived = bool(e.get("archived"))

        # Languages attribute (|-separated: tags may contain spaces)
        languages_attr = esc("|".join(
            l.strip() for l in e.get("languages", e.get("language", "")).split(",") if l.strip()
        ))

        # Stars display
        stars_html = (
            f'<span class="stars" title="{stars:,} stars">'
            f'<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 22 12 18.56 5.82 22 7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>'
            f" {format_stars(stars)}</span>"
            if stars > 0
            else ""
        )

        # Last update display
        last_update_html = (
            f'<span class="last-update" title="Last commit: {esc(last_commit)}">{esc(last_commit)}</span>'
            if last_commit and last_commit != "error"
            else ""
        )

        # Source flags for data attributes
        sources = []
        if is_github:
            sources.append("github")
        if is_cran:
            sources.append("cran")
        if is_pypi:
            sources.append("pypi")
        if is_commercial:
            sources.append("commercial")
        if is_archived:
            sources.append("archived")
        sources_attr = esc(" ".join(sources))

        tags_html = build_tags_html(e)

        rows.append(
            f"""      <tr class="row" data-name="{esc(e['project'].lower(), quote=True)}" data-languages="{languages_attr}" data-category="{category}" data-sources="{sources_attr}" data-stars="{stars}" tabindex="-1" aria-expanded="false">
        <td class="col-num">{i}</td>
        <td class="col-name">
          {f'<a href="{url}" target="_blank" rel="noopener">{name}</a>' if url else name}
          <span class="mobile-category">{category}</span>
        </td>
        <td class="col-stars">{stars_html}</td>
        <td class="col-update">{last_update_html}</td>
        <td class="col-tags">
          {tags_html}
        </td>
        <td class="col-arrow"><span class="arrow">&#8250;</span></td>
      </tr>
      <tr class="expand-row" hidden>
        <td colspan="6">
          <div class="expand-content">
            <p class="expand-desc">{desc}</p>
            <div class="expand-links">
              {f'<a href="{url}" target="_blank" rel="noopener">{url}</a>' if url else ''}
              {f'<a href="{github_url}" target="_blank" rel="noopener">{github_url}</a>' if github_url and github_url != url else ''}
            </div>
          </div>
        </td>
      </tr>"""
        )

    total = len(entries)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Awesome Quant</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Crect width='24' height='24' rx='5' fill='%230f172a'/%3E%3Cpath d='M4 16l4-6 4 3 6-9' stroke='%2338bdf8' stroke-width='2.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3Ccircle cx='18' cy='8' r='1.6' fill='%2338bdf8'/%3E%3C/svg%3E">
  <meta name="description" content="A curated list of insanely awesome libraries, packages and resources for Quants (Quantitative Finance).">
  <meta property="og:title" content="Awesome Quant">
  <meta property="og:description" content="A curated list of {total} libraries, packages and resources for Quants (Quantitative Finance).">
  <meta property="og:type" content="website">
  <meta name="theme-color" content="#0f172a">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="static/style.css">
</head>
<body>
  <a href="#content" class="sr-only">Skip to content</a>

  <header class="hero">
    <div class="hero-inner">
      <nav class="nav">
        <span class="nav-brand">awesome-quant</span>
        <div class="nav-links">
          <a href="{REPO_CONTRIBUTING_URL}" class="nav-submit">Submit a Project</a>
          <a href="{REPO_URL}">GitHub</a>
          <button class="theme-toggle" aria-label="Toggle dark mode" title="Toggle dark mode">
            <svg class="icon-sun" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
            <svg class="icon-moon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
          </button>
        </div>
      </nav>
      <div class="hero-content">
        <h1>Awesome Quant</h1>
        <p class="hero-subtitle">A curated list of insanely awesome libraries, packages and resources for Quants.</p>
        <p class="hero-maintained">Maintained by <a href="{MAINTAINER_URL}">{MAINTAINER_NAME}</a></p>
        <div class="hero-stats">
          <span class="stat"><strong>{total}</strong> projects</span>
          <span class="stat-sep"></span>
          <span class="stat"><strong>{len(languages)}</strong> languages</span>
        </div>
        <a href="#content" class="hero-cta">Browse the List</a>
      </div>
    </div>
  </header>

  <main id="content">
    <section class="list-section">
      <div class="shell">
        <div class="controls">
          <div class="search-wrap">
            <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
            <input type="search" id="search" class="search-input" placeholder="Search projects..." autocomplete="off" aria-label="Search projects">
            <kbd class="search-kbd">/</kbd>
          </div>
        </div>

{tag_cloud_html}

        <div class="filter-bar" id="filter-bar" style="display:none">
          <span class="filter-label">Filtered by:</span>
          <span class="filter-value" id="filter-value"></span>
          <button class="filter-clear" id="filter-clear">Clear filter</button>
        </div>

        <div class="table-wrap">
          <table class="table" id="project-table" aria-label="Quantitative finance projects">
            <thead>
              <tr>
                <th class="col-num">#</th>
                <th class="col-name" data-sort="name" tabindex="0" role="button" aria-sort="none">Project <span class="sort-arrow"></span></th>
                <th class="col-stars" data-sort="stars" tabindex="0" role="button" aria-sort="none">Stars <span class="sort-arrow"></span></th>
                <th class="col-update" data-sort="update" tabindex="0" role="button" aria-sort="none">Last Update <span class="sort-arrow"></span></th>
                <th class="col-tags">Tags</th>
                <th class="col-arrow"></th>
              </tr>
            </thead>
            <tbody>
{chr(10).join(rows)}
            </tbody>
          </table>
        </div>

        <div class="no-results" id="no-results" hidden>
          <p>No projects match your search.</p>
        </div>

        <div class="results-count" id="results-count" role="status" aria-live="polite"></div>
      </div>
    </section>

    <section class="cta-section">
      <div class="shell">
        <h2>Know a great project?</h2>
        <p>Contribute to the list by opening a pull request on GitHub.</p>
        <a href="{REPO_URL}" class="btn" target="_blank" rel="noopener">Contribute on GitHub</a>
      </div>
    </section>
  </main>

  <footer class="footer">
    <div class="shell">
      <span>Maintained by <a href="{MAINTAINER_URL}">{MAINTAINER_NAME}</a></span>
      <span class="footer-sep">&middot;</span>
      <a href="{REPO_URL}">GitHub</a>
      <span class="footer-sep">&middot;</span>
      <a href="https://awesome.re">awesome.re</a>
    </div>
  </footer>

  <script src="static/main.js"></script>
</body>
</html>"""


def main():
    root = Path(__file__).resolve().parent.parent
    readme = root / "README.md"
    csv_path = root / "site" / "projects.csv"
    output = root / "site" / "index.html"

    # Prefer CSV if it exists (has stars, last commit from API)
    if csv_path.exists():
        print(f"Loading from {csv_path}")
        entries = load_csv(str(csv_path))
    elif readme.exists():
        print(f"Parsing {readme} (no CSV — stars/dates will be empty)")
        entries = parse_readme(str(readme))
    else:
        print(f"ERROR: neither {csv_path} nor {readme} found", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(entries)} projects")
    html_content = generate_html(entries)
    output.write_text(html_content, encoding="utf-8")
    print(f"Generated {output}")


if __name__ == "__main__":
    main()
