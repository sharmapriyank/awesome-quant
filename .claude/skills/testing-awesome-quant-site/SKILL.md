---
name: testing-awesome-quant-site
description: How to E2E-test the awesome-quant generated static site (site/index.html) locally — serve command, where expected values come from, link conventions, and known benign 404s.
---

# Testing the awesome-quant generated static site

## Setup
- No backend, auth, or install needed for UI testing. Serve the prebuilt site:
  `cd site && python3 -m http.server <port>` then open `http://localhost:<port>/`.
- Regeneration check: `site/generate.py` reads `site/projects.csv` and rewrites `site/index.html`.
  Run `<repo>/.venv/bin/python site/generate.py` (or `uv run python site/generate.py`) and `git diff` —
  output should be byte-for-byte identical if the checked-in site is in sync.
- `parse.py` (README.md -> projects.csv) needs network (GitHub/CRAN/PyPI); it uses the GitHub API
  when `GITHUB_ACCESS_TOKEN` is set and falls back to token-free HTML/Atom scraping otherwise
  (slower, throttled to 4 concurrent requests with retry/backoff). Either way,
  do NOT run it just to test the site — verify README entry count offline instead:
  `README.md` entries match regex `^\s*- \[(.*)\]\((.*)\) - (.*)$`; compare to `wc -l site/projects.csv - 1`.
  If CSV count < README count, the committed CSV is stale (drift is normal because CI that regenerates
  it lives in `ci/workflows/` and is vendored, not active — there is no `.github/` dir on this fork).
  `generate.py` falls back to parsing README directly when projects.csv is absent — useful to quantify
  the drift without a token.

## What to verify (golden path)
- Hero stats = projects.csv row count / distinct `languages` values (compute both from the CSV first;
  do not trust hardcoded numbers).
- Structural links (nav "Submit a Project"/"GitHub", CTA "Contribute on GitHub", footer "GitHub",
  "Maintained by") must point to `github.com/sharmapriyank[/awesome-quant]`. wilsonfreitas may
  legitimately appear ONLY inside project rows (his repos are list entries) — check structural links
  specifically, e.g. `[...document.querySelectorAll('nav a, .footer a, .cta-section a')].filter(a => a.href.includes('wilsonfreitas'))` should be `[]`.
- Search input filters live (120ms debounce), syncs `?q=` via history.replaceState, and `?q=` is
  restored on load. `?filter_type=language|category&filter=<v>` also restores.
- Tag-cloud chips and in-row tag pills apply a single active filter (new chip replaces, same chip
  toggles off, "Clear filter" resets). Match counts against CSV group counts.
- Sort headers: name cycles asc->desc->default; stars/update cycle desc->asc (never reset to default).
  Sortable th`s are keyboard-operable (tabindex=0, role=button, aria-sort): Enter/Space on a focused
  header runs the same cycle as click and sets aria-sort=ascending/descending (none on inactive).
  Tab order: search input -> tag-cloud chips (~14) -> Project th -> Stars th -> Last Update th, then
  the first visible row (roving tabindex), then in-row links/pills. Shift+Tab moves back between
  headers. :focus-visible draws a 2px accent outline on th AND on .row tr.
- Rows use roving tabindex: all render tabindex="-1" aria-expanded="false"; main.js seeds
  rows[0].tabindex="0" at init and after each applyFilters seeds the FIRST VISIBLE row with "0"
  only when NO visible row already has 0. Arrows/Home/End move focus between visible rows
  (skipping hidden/expand rows); Enter/Space on a focused row = row.click() (expand/collapse).
  #results-count has role="status" aria-live="polite" and renders "Showing N projects".
  ALL PRIOR DEFECTS FIXED (PR #14, verified): (a) roving entry reseeds unconditionally — every
  applyFilters clears ALL rows to -1 then sets vr[0]=0, so the repro `?q=backtrader` -> clear ->
  T&B chip now leaves Crypto Pump Scanner (first visible) as the ONLY tabindex=0 and Tab lands
  on the ROW (backtrader=-1); verify with `[...document.querySelectorAll('tbody tr.row')]
  .filter(r=>!r.hidden && r.tabindex==='0')` — should be exactly vis[0]; (b) Enter/Space on
  in-row pill applies its filter (guard `e.target !== row`); (c) unknown filter_type via URL is
  discarded by a FILTER_TYPES allowlist (language/category/source) — `?filter_type=<svg>&filter=X`
  yields bar display:none, 0 pressed/active, all rows, AND syncURL cleans the URL to bare `/`.
- Row click expands an accordion (one open at a time) showing description + URL; clicks on tags/links
  inside a row do NOT expand.
- Theme toggle sets `<html data-theme>` and persists via localStorage `theme` (per-origin! a different
  port = different stored theme; also prefers-color-scheme is the default).
- `/` focuses search; Escape clears/blurs.

## Gotchas
- `python3 -m http.server` serves per-request from disk — a running server picks up regenerated files,
  but an open browser tab keeps the STALE rendered DOM until reloaded. If the page shows old branding,
  reload before concluding anything.
- Favicon is an inline SVG `data:` URI (`<link rel="icon" href="data:image/svg+xml,...">`) — the browser
  makes NO /favicon.ico request, so check the server log for a favicon 404 only on pre-fix builds.
- "archived" is a SOURCE tag (like `github`/`commercial`): archived rows carry `data-sources="github
  archived"` and a gray `.tag-archived` pill; filtering by it is `?filter_type=source&filter=archived`.
  Archived projects sit in the "Historical & Archived Projects" category and also carry a `Historical`
  language tag — so the "historical" chip is a superset of the archived set (15 vs 12 at last check).
- The hero "languages" count = ALL distinct tokens in the CSV `languages` column, which now includes
  non-language topic tags (SEC EDGAR, MCP, Historical, A-shares...) — verify against the CSV and treat
  as a data-semantics issue, not a render bug.
- Google Fonts (Inter) load from fonts.googleapis.com — if the sandbox has no external network, expect
  a failed-request console warning with system-font fallback; the site still works.
- Expected star counts/dates come from projects.csv — verify sort assertions against the CSV
  (`csv.DictReader`, sort by `stars`), not memory. Same for filter counts: group the CSV by
  category/languages/source flags first, then assert the exact "Showing N projects" text.
  When counting tag pills in index.html instead, remember the tag-cloud emits ONE extra pill
  for each of its ~14 chips — grep counts can be off-by-one vs actual row counts; CSV is truth.
- `data-languages` is `|`-separated (multi-language rows + tags containing spaces like "Pine
  Script", "SEC EDGAR"). main.js splits on `|`. If you ever see space-joined values resurface,
  spaced-tag pill clicks will silently match 0 rows — that's the regression signature.
- The hero uses a dark navy background in BOTH themes — judge dark mode by the content/table area, not
  the hero.
- Pressing End/Home while the search input is focused edits the text, not the page — Escape (or click
  elsewhere) first to scroll the page.

## Devin Secrets Needed
- None for serving/testing the generated site. `GITHUB_ACCESS_TOKEN` only if parse.py itself is under test.
