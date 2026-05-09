# Meath Morning Edition — Project Context

## What this is
A daily automated newsletter covering County Meath, Ireland. Runs at 7am via Windows
Task Scheduler, scrapes local news sources, curates 8 stories with Claude Opus 4.6,
renders an HTML newsletter + a Beehiiv-ready copy-paste version + an RSS feed, then
publishes to GitHub Pages and emails to shane@shanebreslin.com.

This is a **separate project** from the Golf Morning Edition (which lives in
`../golf-morning-edition/`). They share the same Gmail account and GitHub token but
have different GitHub repos and different generate.py files.

## Directory layout
```
meath-morning-edition/
├── generate.py               # Main script — runs everything
├── .env                      # Secrets (never commit)
├── run_morning_edition.bat   # Batch launcher for Task Scheduler
├── task.xml                  # Windows Task Scheduler XML
├── TODO.md                   # Outstanding tasks
├── CLAUDE.md                 # This file
├── newsletters/
│   ├── YYYY-MM-DD.html       # Full HTML edition (published to GitHub Pages)
│   ├── YYYY-MM-DD-copypaste.html  # Minimal inline-styled HTML for Beehiiv paste
│   └── rss.xml               # RSS feed (last 30 issues, pushed to GitHub Pages)
└── logs/                     # Task Scheduler log output
```

## .env variables
```
ANTHROPIC_API_KEY=...
GITHUB_TOKEN=...
GITHUB_REPO_MEATH=cavani101/meath-morning-edition
GMAIL_ADDRESS=shane@shanebreslin.com
GMAIL_APP_PASSWORD=...
EMAIL_TO=shane@shanebreslin.com
```

## Sources
1. **Meath Live** — RSS feed at `https://meathlive.net/feed/` (reliable)
2. **Meath Chronicle** — HTML scrape of `meathchronicle.ie/news/` (sometimes fragile)
3. **Google Alert** — Gmail IMAP on `[Gmail]/All Mail`, filtered by
   `FROM "googlealerts-noreply@google.com" SUBJECT "Meath" SINCE {yesterday}`
   The SUBJECT "Meath" filter is critical — same Gmail account also receives golf
   alerts, so without this filter AI/golf stories bleed into Meath editions.
   The Meath Google Alert IS set up and running — delivers most days (some days
   nothing matches). Alert query covers: "County Meath", "Meath County Council",
   Ashbourne, Oldcastle, Navan, Trim, Dunshaughlin, Dunboyne, Trim Circuit Court, navan district court,
   Kells, site:meath.ie/notices/ inurl:ie — excludes rip.ie, "navan road", kilkenny.

## Deduplication
Uses GitHub-hosted JSON (`seen_urls.json` in the GitHub repo root).
`load_seen_urls()` fetches via GitHub Contents API on each run.
`save_seen_urls()` commits the updated set back after curation.
Falls back to a local `seen_urls.json` if GitHub vars aren't set.

**Note:** The golf edition uses the same approach but a different repo
(`GITHUB_REPO` vs `GITHUB_REPO_MEATH`). They have separate dedup stores.

## Claude curation
- Model: `claude-opus-4-6`
- Selects **8 stories** (not 10 — smaller local pool)
- Categories: Local News | Planning & Development | Business & Jobs |
  Community & Events | Sport | Council & Politics | Courts & Crime |
  Transport & Infrastructure
- Flags stories of lasting practical importance with `key_story: true` + `key_story_reason`
  Criteria: still relevant/actionable at 7am next morning — major planning decisions,
  service changes, significant council announcements. NOT road closures or incidents
  that will be resolved overnight.
- JSON parsing uses `rfind("]")` — less robust than the golf edition's bracket-counting
  parser. If Claude starts returning empty arrays + commentary, upgrade to the
  bracket-counting approach used in golf edition's `curate_with_claude()`.

## HTML outputs
`build_html()` — Full newsletter: green (#1A4731) and gold (#B8860B) Meath colour
scheme, weather widget at top (Navan coordinates via Open-Meteo), newspaper card
layout. Published to GitHub Pages.

`build_copypaste_html()` — Minimal inline-styled version for pasting into
Beehiiv's free editor. Starts with the weather line (no masthead yet — see TODO).

`update_rss()` — Maintains `newsletters/rss.xml` with last 30 issues.
Uses `<content:encoded>` containing the copypaste HTML so Beehiiv RSS-to-Send
can pick it up when/if that feature is enabled ($43/mo Scale plan).

## GitHub Pages
Repo: `https://github.com/cavani101/meath-morning-edition`
Pages URL: `https://cavani101.github.io/meath-morning-edition/`
Published path: `newsletters/YYYY-MM-DD.html`
RSS: `newsletters/rss.xml`

## Windows Task Scheduler
Task name: `MeathMorningEdition`
Runs: daily 7am, `run_morning_edition.bat` → `python generate.py`
Registered via: `schtasks /Create /TN "MeathMorningEdition" /XML task.xml /F`

## Key decisions made
- **JSON dedup over SQLite** — original code used local `seen_urls.db` (SQLite).
  Migrated to GitHub-hosted `seen_urls.json` so the dedup state survives across
  machines and is visible in the repo.
- **Separate IMAP filter from golf** — both projects use the same Gmail account.
  Golf fetches `SUBJECT "golf"` alerts; Meath fetches `SUBJECT "Meath"` alerts.
- **Beehiiv copy-paste approach** — free Beehiiv tier doesn't support RSS-to-Send.
  The copypaste HTML is a workaround: Shane pastes it manually into the Beehiiv editor.
  When ready to send to real subscribers, upgrade to Scale ($43/mo) and use RSS feed.

## What's NOT in this project (but is in golf edition)
- Within-day story clustering (groups articles about the same event)
- `additional_sources` field (links to other outlets covering the same story)
- `and_finally` lighter story segment
- `--rebuild-html` flag (rebuild HTML from cached stories JSON without re-running Claude)
- `--force` flag behaviour already exists but stories aren't cached to JSON

These features were built into the golf edition after Meath was set up. Worth porting
when there's time — especially clustering, since Meath Chronicle and Meath Live
sometimes cover the same planning decision or council story.

## Outstanding work (see TODO.md for full list)
- **High:** Move to GitHub Actions (remove laptop dependency)
- **Medium:** Meath Chronicle scraping is HTML — consider RSS builder if quality drops
- **Medium:** Beehiiv copy-paste header needs a proper masthead (currently just weather)
- **Nice to have:** Story clustering (same as golf edition) — Meath Chronicle and
  Meath Live sometimes cover the same planning decision; clustering would fold them
- **Nice to have:** Cross-day story follow-up awareness (same problem as golf edition)
- **Nice to have:** Branded GitHub account (e.g. meathdaily) when ready to launch publicly

## Recent changes
- `urgent` field renamed to `key_story` / `key_story_reason` — "urgent" implied
  time-sensitivity that may have passed by 7am. `key_story` means lasting practical
  importance (planning decisions, service changes) not one-off incidents.
- Source diversity cap added to SYSTEM_PROMPT: max 3 stories from any single source,
  specifically to prevent Meath Chronicle dominating the 8-story selection.
