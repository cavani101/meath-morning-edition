# Meath Morning Edition — To-Do

## High Priority

- [ ] **Move to GitHub Actions** — remove laptop dependency
  - Commit code (generate.py, requirements.txt) to the repo
  - Move secrets from .env to GitHub Secrets
  - Write .github/workflows/generate.yml (daily 7am UTC cron)
  - Test run via GitHub Actions
  - Disable Windows Task Scheduler once confirmed working

- [ ] **Set up Meath Google Alert** — currently 0 articles from this source
  - Alert query: "County Meath" OR "Meath County Council" OR "Ashbourne" OR
    "Oldcastle" OR "Navan" OR "Trim" OR "Trim Circuit Court" OR
    "navan district court" OR "Kells" OR site:meath.ie/notices/ inurl:ie
    -rip.ie -"navan road" -kilkenny
  - Send to shane@shanebreslin.com
  - Will be picked up automatically next morning after first delivery

## Medium Priority

- [ ] **Events — add more venues**
  - **Swift Cultural Centre** — `https://swiftculturalcentre.ie/whats-on/`
    Same HTML structure as Solstice (`section.eventlistblock`), so scraper should
    be a near-copy of `scrape_solstice_events()`
  - **The Venue Ratoath** — `https://thevenueratoath.ticketsolve.com/ticketbooth/shows`
    Uses Ticketsolve platform — inspect for JSON-LD or structured listing HTML
  - Consider a shared `scrape_solstice_style(url, venue_name)` helper once Swift
    is confirmed to use the same markup

- [ ] **Events — Meetup.com**
  - Meetup increasingly requires login for search results; skip for now
  - Revisit if a public Meath group URL can be accessed without auth
  
- [ ] **Fix Copypaste - what's on still appearing on top**
  - Change copypaste export so that what's on content appears at the bottom like the web version

- [ ] **Meath Chronicle — improve scraping**
  - Currently scraping HTML; consider RSS builder (Feedity/PolitePol ~$5-10/mo)
    if content quality is inconsistent

- [ ] **Beehiiv copy-paste — improve header**
  - Add proper masthead (green bar, "Meath Morning Edition" title)
  - Currently starts with plain weather line

- [ ] **Beehiiv RSS-to-Send ($43/mo trial)**
  - RSS feed is already being generated at newsletters/rss.xml
  - Push rss.xml to GitHub Pages so Beehiiv can poll it
  - Test one-month trial when ready to send to real subscribers

- [ ] **Subscriber list** — decide on delivery platform before launch
  - Option A: Stay custom (Gmail SMTP + CSV list)
  - Option B: Beehiiv Scale ($43/mo) with RSS-to-Send
  - Decision pending content quality validation

- [ ] **Events — curated festivals & recurring events list**
  - Maintain a small static JSON file of known annual events (Fleadh Cheoil,
    Trim Swift Festival, Navan Food & Culture Festival, etc.)
  - Feed into events curation so they surface in the right week each year

## Nice to Have

- [ ] **Events — time display**
  - Currently omitted due to inconsistency across sources (Solstice has times,
    Eventbrite often doesn't). Restore once all sources reliably provide times.

- [ ] **Move to branded GitHub account** — when ready to launch publicly
  - New account (e.g. meathdaily) gives cleaner URL
  - Currently on cavani101 for MVP testing

- [ ] **Second Google Alert** — broader coverage
  - Without inurl:ie to catch irishtimes.com, Bloomberg, Reuters with Meath angle

- [ ] **Story clustering** — group same event covered by multiple sources
  - Detect near-duplicate stories (same subject, different outlets)
  - Show as a single card with "Also: Meath Chronicle, Meath Live" attribution

- [ ] **Claude model upgrade path**
  - Currently on claude-opus-4-6; revisit model choice vs cost as usage scales

## Done

- [x] Daily scraping — Meath Live (RSS), Meath Chronicle (HTML scrape)
- [x] Weather widget via Open-Meteo — 6 Co. Meath locations
- [x] Claude Opus 4.6 curation (top 8 stories)
- [x] HTML newsletter with Meath green/gold design
- [x] Copy-paste HTML output for Beehiiv free editor
- [x] RSS feed generation (rss.xml)
- [x] GitHub Pages publishing
- [x] Gmail SMTP email delivery
- [x] Deduplication — seen_urls.json stored on GitHub
- [x] Windows Task Scheduler — runs daily at 7am
- [x] Multi-town weather bar — Navan, Trim, Kells, Oldcastle, Enfield, Dunshaughlin
- [x] Events section — Solstice Arts Centre + Eventbrite, curated by Claude
- [x] Events — section headings (Weather / News / What's On) consistent across newsletter
