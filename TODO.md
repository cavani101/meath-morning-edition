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

- [ ] **Notable Meath People — dedicated session needed**
  - First draft list at `meath_people.json` (30 names across sport, music, comedy, politics, literature)
  - Needs community review + expansion to 50+ names; flag `"verify": true` entries especially
  - Implementation plan: dedicated Google Alert (`"CMAT" OR "Tommy Tiernan" OR ...` from the JSON)
    feeding into a separate Gmail label; script fetches it alongside the main Meath alert
  - Claude curation prompt gets a hint: "if any article features a person from MEATH_PEOPLE,
    treat this as a strong positive signal even if the article doesn't mention Meath"
  - Needs dedicated session to scope fully end-to-end

- [ ] **Community Notice Board — dedicated session needed**
  - Intake: Google Form → Google Sheet (reader submits a notice)
  - Moderation: "approved" column in Sheet; script only surfaces approved items
  - Processing: Claude categorises and writes a short summary line
  - Display: separate "Community Notices" section at bottom of newsletter
  - Needs dedicated session to scope storage, moderation workflow, and spam prevention

- [ ] **Planning Decisions weekly digest (Friday)**
  - URL investigation done: Meath Council site has SSL cert issues; ePlanning.ie requires
    form submission (not directly scrapeable via requests)
  - Weekly decisions listed at (needs SSL bypass or alternative):
    https://www.meath.ie/council/council-services/planning-and-building/planning-permission/view-or-search-planning-applications/weekly-planning-permissions-list
  - Fallback: extend Google Alert to catch "Meath planning" decisions via news sources
  - Friday-only section; Claude selects 3–5 notable decisions (commercial, large residential,
    refusals) from the week's list
  - Needs further investigation of scraping approach before implementation

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

- [ ] **"On this day in Meath" — local history file**
  - Feature is live and pulls from Wikipedia (Irish/global filter via Claude)
  - User building `meath_history.json` separately — upload to repo root when ready
  - Format: `{"MM-DD": [{"year": 1690, "text": "Battle of the Boyne fought..."}]}`
  - Meath entries always take priority over Wikipedia results

- [ ] **"On this day" — tone refinement**
  - Currently picks "most interesting" event globally when nothing Irish exists
  - Consider adding a minimum relevance bar (Irish/European only, skip US/Asia events)
  - Review after a week of real editions to calibrate

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
- [x] What's On moved above News section
- [x] Editorial tone — good news bias, hard news deprioritised in Claude prompt
- [x] Email teasers — "Inside today" bullet points from top stories + first event
- [x] On this day — Wikipedia API + local meath_history.json hook (file to be uploaded)
- [x] Notable Meath People — first draft list at meath_people.json (30 names, needs expansion)
