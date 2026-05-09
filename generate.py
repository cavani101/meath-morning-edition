"""
Meath Morning Edition -- daily newsletter generator
Fetches local news for County Meath, curates with Claude, renders HTML + RSS.
"""

import os
import json
import datetime
import re
import sys
import smtplib
import imaplib
import email as email_lib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, parse_qs, urljoin

import requests
from bs4 import BeautifulSoup
import anthropic

# ── Load .env ────────────────────────────────────────────────────────────────
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ[_k.strip()] = _v.strip().strip('"').strip("'")

NEWSLETTERS_DIR = Path(__file__).parent / "newsletters"
NEWSLETTERS_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IE,en;q=0.9",
}

# Weather locations across Co. Meath (name, lat, lon)
WEATHER_LOCATIONS = [
    ("Navan",          53.6528, -6.6803),
    ("Trim",           53.5546, -6.7896),
    ("Kells",          53.7283, -6.8781),
    ("Oldcastle",      53.7739, -7.1618),
    ("Enfield",        53.4160, -6.8330),
    ("Dunshaughlin",   53.5148, -6.5395),
]

WMO_CODES = {
    0: "Clear skies", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Icy fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow",
    77: "Snow grains", 80: "Light showers", 81: "Showers", 82: "Heavy showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm",
}


# ── Weather ──────────────────────────────────────────────────────────────────

def _fetch_weather_one(name: str, lat: float, lon: float) -> dict:
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode"
            f"&timezone=Europe%2FDublin&forecast_days=1"
        )
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        d = r.json()["daily"]
        code = d["weathercode"][0]
        return {
            "name": name,
            "description": WMO_CODES.get(code, "Variable"),
            "temp_max": round(d["temperature_2m_max"][0]),
            "temp_min": round(d["temperature_2m_min"][0]),
            "rain_mm": round(d["precipitation_sum"][0], 1),
        }
    except Exception as e:
        print(f"  [!] Weather ({name}): {e}")
        return {"name": name, "description": "Unavailable", "temp_max": "--", "temp_min": "--", "rain_mm": "--"}


def get_weather() -> list[dict]:
    """Fetch today's forecast for all Co. Meath locations via Open-Meteo."""
    return [_fetch_weather_one(name, lat, lon) for name, lat, lon in WEATHER_LOCATIONS]


# ── Scraping ──────────────────────────────────────────────────────────────────

def scrape_rss(source_name: str, rss_url: str, max_age_days: int = 7) -> list[dict]:
    """Parse an RSS feed and return recent article dicts."""
    try:
        r = requests.get(rss_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  [!] {source_name} (RSS): {e}")
        return []

    soup = BeautifulSoup(r.text, "xml")
    articles = []
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_age_days)

    for item in soup.find_all("item")[:50]:
        title_tag = item.find("title")
        link_tag  = item.find("link")
        desc_tag  = item.find("description") or item.find("summary")
        pub_tag   = item.find("pubDate") or item.find("published")

        if not title_tag or not link_tag:
            continue

        if pub_tag:
            try:
                pub_dt = parsedate_to_datetime(pub_tag.get_text(strip=True))
                if pub_dt < cutoff:
                    continue
            except Exception:
                pass

        title   = title_tag.get_text(strip=True)
        url     = link_tag.get_text(strip=True)
        raw     = desc_tag.get_text(strip=True) if desc_tag else ""
        snippet = BeautifulSoup(raw, "lxml").get_text()[:200].strip()

        articles.append({"source": source_name, "title": title, "url": url, "snippet": snippet})

    print(f"  [ok] {source_name}: {len(articles)} articles found")
    return articles


def scrape_meath_chronicle() -> list[dict]:
    """Scrape Meath Chronicle news page."""
    source_name = "Meath Chronicle"
    url = "https://www.meathchronicle.ie/news/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  [!] {source_name}: {e}")
        return []

    soup = BeautifulSoup(r.text, "lxml")
    articles = []
    seen = set()

    items = soup.find_all("article") or []
    if not items:
        items = [t for t in soup.find_all(["h2", "h3"]) if t.find("a", href=True)]

    for item in items[:40]:
        link = item.find("a", href=True)
        if not link:
            continue
        title = link.get_text(strip=True)
        if not title or title in seen or len(title) < 15:
            continue
        seen.add(title)

        href = link["href"]
        if href.startswith("/"):
            href = urljoin(url, href)

        snippet = ""
        parent = item if item.name == "article" else item.parent
        if parent:
            p = parent.find("p")
            if p:
                snippet = p.get_text(strip=True)[:200]

        articles.append({"source": source_name, "title": title, "url": href, "snippet": snippet})

    print(f"  [ok] {source_name}: {len(articles)} articles found")
    return articles


def fetch_meath_google_alert() -> list[dict]:
    """
    Read yesterday's Meath Google Alert digest from Gmail via IMAP.
    Filters by subject containing 'Meath' to avoid picking up the golf alerts.
    """
    gmail_user = os.environ.get("GMAIL_ADDRESS")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_pass:
        return []

    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    since_str = yesterday.strftime("%d-%b-%Y")

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(gmail_user, gmail_pass)
        mail.select('"[Gmail]/All Mail"')

        _, msg_ids = mail.search(
            None,
            f'FROM "googlealerts-noreply@google.com" SUBJECT "Meath" SINCE {since_str}'
        )
        ids = msg_ids[0].split()
        if not ids:
            print("  [!] Google Alert (Meath): no alert email found from yesterday")
            mail.logout()
            return []

        all_html_bodies = []
        for mid in ids:
            _, msg_data = mail.fetch(mid, "(RFC822)")
            msg = email_lib.message_from_bytes(msg_data[0][1])
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        all_html_bodies.append(
                            part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        )
                        break
            elif msg.get_content_type() == "text/html":
                all_html_bodies.append(
                    msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                )
        mail.logout()

        if not all_html_bodies:
            print("  [!] Google Alert (Meath): no HTML body found")
            return []

        articles = []
        seen_urls = set()

        for html_body in all_html_bodies:
            soup = BeautifulSoup(html_body, "lxml")
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                if "google.com/url" not in href:
                    continue
                params   = parse_qs(urlparse(href).query)
                real_url = params.get("url", [None])[0]
                if not real_url or real_url in seen_urls:
                    continue
                title = a_tag.get_text(strip=True)
                if not title or len(title) < 15:
                    continue
                seen_urls.add(real_url)

                source = "Google Alert"
                container = a_tag.find_parent("td") or a_tag.find_parent("div")
                if container:
                    for sib in a_tag.next_siblings:
                        text = sib.get_text(strip=True) if hasattr(sib, "get_text") else str(sib).strip()
                        if text and len(text) < 80 and text != title:
                            source = text
                            break

                snippet = ""
                if container:
                    for text in container.find_all(string=True):
                        t = text.strip()
                        if t and t != title and t != source and len(t) > 40:
                            snippet = t[:200]
                            break

                articles.append({"source": source, "title": title, "url": real_url, "snippet": snippet})

        print(f"  [ok] Google Alert (Meath): {len(articles)} articles found")
        return articles

    except Exception as e:
        print(f"  [!] Google Alert (Meath): {e}")
        return []


def fetch_all_stories() -> list[dict]:
    print("Fetching stories...")
    articles = []
    articles.extend(scrape_rss("Meath Live", "https://meathlive.net/feed/"))
    articles.extend(scrape_meath_chronicle())
    articles.extend(fetch_meath_google_alert())
    print(f"  Total raw: {len(articles)} articles\n")
    return articles


# ── Events scraping ───────────────────────────────────────────────────────────

def _parse_json_ld_events(soup, fallback_url: str, source: str) -> list[dict]:
    """Extract events from JSON-LD structured data in a page."""
    events = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if not isinstance(data, list):
                data = [data]
            for item in data:
                if item.get("@type") in ("Event", "MusicEvent", "TheaterEvent",
                                          "ScreeningEvent", "VisualArtsEvent",
                                          "ComedyEvent", "DanceEvent"):
                    loc = item.get("location", {})
                    venue = loc.get("name", "") if isinstance(loc, dict) else ""
                    events.append({
                        "title": item.get("name", ""),
                        "date_raw": item.get("startDate", ""),
                        "venue": venue,
                        "location": "Co. Meath",
                        "url": item.get("url", fallback_url),
                        "description": item.get("description", "")[:250],
                        "source": source,
                    })
        except Exception:
            pass
    return events


def scrape_solstice_events() -> list[dict]:
    """Scrape upcoming events from Solstice Arts Centre, Navan.

    Each card is <section class="eventlistblock"> containing a .toplink anchor
    with an <h3> title, <span class="date"> (single date or date range), and <p> blurb.
    Date ranges cover exhibitions; single dates are performances/events.
    """
    url = "https://solsticeartscentre.ie/whats-on/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  [!] Solstice events: {e}")
        return []

    soup = BeautifulSoup(r.text, "lxml")
    events = []

    for section in soup.find_all("section", class_="eventlistblock"):
        link = section.find("a", class_="toplink", href=True)
        if not link:
            continue
        h3 = link.find("h3")
        title = h3.get_text(strip=True) if h3 else link.get_text(strip=True)
        if not title:
            continue
        href = link["href"]
        if not href.startswith("http"):
            href = urljoin(url, href)
        date_span = link.find("span", class_="date")
        date_raw = " ".join(date_span.get_text().split()) if date_span else ""
        p = link.find("p")
        desc = p.get_text(strip=True)[:250] if p else ""
        events.append({
            "title": title,
            "date_raw": date_raw,
            "venue": "Solstice Arts Centre",
            "location": "Navan, Co. Meath",
            "url": href,
            "description": desc,
            "source": "Solstice Arts Centre",
        })

    print(f"  [ok] Solstice Arts Centre: {len(events)} events found")
    return events[:25]


def scrape_eventbrite_events() -> list[dict]:
    """Scrape upcoming Co. Meath events from Eventbrite via embedded SERVER_DATA JSON-LD."""
    url = "https://www.eventbrite.ie/d/ireland--county-meath/events/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  [!] Eventbrite events: {e}")
        return []

    soup = BeautifulSoup(r.text, "lxml")
    events = []

    # Eventbrite embeds an ItemList inside window.__SERVER_DATA__ on the page
    for script in soup.find_all("script"):
        raw = script.string or ""
        if "window.__SERVER_DATA__" not in raw:
            continue
        try:
            idx = raw.index("window.__SERVER_DATA__") + len("window.__SERVER_DATA__")
            while idx < len(raw) and raw[idx] in " \t\n=":
                idx += 1
            end = raw.rindex(";")
            data = json.loads(raw[idx:end])
            for block in data.get("jsonld", []):
                if block.get("@type") != "ItemList":
                    continue
                for item_wrap in block.get("itemListElement", []):
                    ev = item_wrap.get("item", {})
                    if not ev.get("name"):
                        continue
                    loc   = ev.get("location", {})
                    venue = loc.get("name", "") if isinstance(loc, dict) else ""
                    addr  = loc.get("address", {}) if isinstance(loc, dict) else {}
                    place = (addr.get("addressLocality", "") if isinstance(addr, dict) else "") or "Co. Meath"
                    events.append({
                        "title": ev.get("name", ""),
                        "date_raw": ev.get("startDate", ""),
                        "venue": venue,
                        "location": place,
                        "url": ev.get("url", url),
                        "description": ev.get("description", "")[:250],
                        "source": "Eventbrite",
                    })
        except Exception:
            pass
        break  # only one SERVER_DATA script

    print(f"  [ok] Eventbrite: {len(events)} events found")
    return events[:30]


def fetch_all_events() -> list[dict]:
    print("Fetching events...")
    events = []
    events.extend(scrape_solstice_events())
    events.extend(scrape_eventbrite_events())
    print(f"  Total raw events: {len(events)}\n")
    return events


# ── Claude curation ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are the editor of a daily local newsletter called "Meath Morning Edition",
covering County Meath, Ireland. The newsletter is delivered at 7am each morning.

Your reader is a general local audience — residents, business owners, commuters, and community members.

Content filter:
INCLUDE: local news, planning applications and decisions, council announcements, business openings
  and closures, jobs, community events, local sport, crime (court reports), infrastructure,
  transport, schools, health services, local politics, notable appointments.
SKIP: national news with no Meath angle, celebrity gossip, clickbait, sponsored content,
  generic lifestyle pieces, obituaries.

SOURCE DIVERSITY: No more than 3 stories from any single source. If Meath Chronicle
dominates the candidate pool, be selective — prefer Chronicle stories that cover
events not already reported by other sources, and prioritise variety.

KEY STORY FLAG: Mark a story as key_story=true only if it describes something with
ongoing practical importance that residents will still need to know at 7am tomorrow —
e.g. a major planning decision, a new service change, a significant council announcement.
Do NOT flag road closures, accidents, or incidents that are likely to be resolved
by the following morning.

Return ONLY valid JSON — no markdown fences, no commentary."""

CURATION_PROMPT = """Here are today's raw article candidates from Meath news sources.
Select the 8 best stories that are genuinely relevant to a County Meath local audience.

For each story provide:
- rank (1-8)
- title (clean, clear — rewrite if needed, max 90 chars)
- source
- url
- category (one of: Local News | Planning & Development | Business & Jobs |
  Community & Events | Sport | Council & Politics | Courts & Crime | Transport & Infrastructure)
- teaser (2-3 sentences — specific and factual, no fluff)
- key_story (true/false — true = ongoing practical importance residents need to know tomorrow)
- key_story_reason (if key_story=true: one line explaining the lasting significance)

Articles:
{articles_json}

Return JSON array of 8 objects with the fields above."""


EVENTS_SYSTEM_PROMPT = """You are the events editor for "Meath Morning Edition", a daily local newsletter for County Meath, Ireland.

Your task is to select events starting within the next four days that are worth telling readers about.

Rules:
- Use the START date from date_raw to decide eligibility. Only include events whose START date
  falls between today and four days from now.
- This means: if a date range shows "Sat 11 Apr 2026 - Sat 6 Jun 2026", the start date is
  11 April — which is in the past, so EXCLUDE it regardless of whether it is still running.
- Only surface an ongoing exhibition if it literally opens (starts) within the next four days.
- Skip events with no usable date or clearly outside County Meath.
- Prefer: theatre, music, comedy, talks, screenings, sport, community.
- Return an empty array [] if nothing qualifies.

Return ONLY valid JSON — no markdown fences, no commentary."""

EVENTS_PROMPT = """Today is {today}. Include only events whose START date is between {today} and {day3}.

Select up to 6 items from the raw listings below.

For each return:
- title (clean, max 80 chars)
- date (YYYY-MM-DD — the event's start date)
- time (HH:MM 24-hour if known, else "")
- venue
- location
- url
- description (1-2 sentences, factual)
- source

Raw listings:
{events_json}

Return a JSON array (may be empty [])."""


def curate_events_with_claude(raw_events: list[dict]) -> list[dict]:
    if not raw_events:
        return []
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return []
    client = anthropic.Anthropic(api_key=api_key)
    today = datetime.date.today()
    day3  = (today + datetime.timedelta(days=3)).isoformat()
    prompt = EVENTS_PROMPT.format(
        today=today.isoformat(), day3=day3,
        events_json=json.dumps(raw_events, indent=2),
    )
    print("Sending events to Claude for curation...")
    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=3000,
            system=EVENTS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
        start = text.find("[")
        end   = text.rfind("]") + 1
        if start >= 0 and end > start:
            text = text[start:end]
        curated = json.loads(text)
        print(f"  [ok] Events: Claude selected {len(curated)}\n")
        return curated
    except Exception as e:
        print(f"  [!] Events curation failed: {e}")
        return []


def curate_with_claude(articles: list[dict]) -> list[dict]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)
    client = anthropic.Anthropic(api_key=api_key)

    articles_json = json.dumps(articles, indent=2)
    print("Sending to Claude for curation...")
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=6000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": CURATION_PROMPT.format(articles_json=articles_json)}],
    )

    text = next((b.text for b in response.content if b.type == "text"), "")
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    start = text.find("[")
    end   = text.rfind("]") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    try:
        curated = json.loads(text)
        print(f"  [ok] Claude selected {len(curated)} stories\n")
        return curated
    except json.JSONDecodeError as e:
        print(f"  [x] JSON parse error: {e}\nRaw:\n{text[:500]}")
        sys.exit(1)


# ── Deduplication ─────────────────────────────────────────────────────────────

SEEN_URLS_FILE = "seen_urls.json"
_LOCAL_SEEN = Path(__file__).parent / SEEN_URLS_FILE


def _gh_headers(token: str) -> dict:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"}


def load_seen_urls() -> set:
    """Load seen URLs from GitHub repo, falling back to local file."""
    import base64
    token = os.environ.get("GITHUB_TOKEN")
    repo  = os.environ.get("GITHUB_REPO_MEATH")
    if token and repo:
        r = requests.get(
            f"https://api.github.com/repos/{repo}/contents/{SEEN_URLS_FILE}",
            headers=_gh_headers(token), timeout=15
        )
        if r.status_code == 200:
            content = base64.b64decode(r.json()["content"]).decode("utf-8")
            return set(json.loads(content).get("urls", []))
        return set()
    if _LOCAL_SEEN.exists():
        return set(json.loads(_LOCAL_SEEN.read_text()).get("urls", []))
    return set()


def save_seen_urls(seen: set, date_str: str):
    """Persist seen URLs to GitHub repo (or local fallback)."""
    import base64
    data = json.dumps({"urls": sorted(seen), "last_updated": date_str}, indent=2)
    token = os.environ.get("GITHUB_TOKEN")
    repo  = os.environ.get("GITHUB_REPO_MEATH")
    if token and repo:
        url = f"https://api.github.com/repos/{repo}/contents/{SEEN_URLS_FILE}"
        sha = None
        r = requests.get(url, headers=_gh_headers(token), timeout=15)
        if r.status_code == 200:
            sha = r.json().get("sha")
        payload: dict = {"message": f"Update seen URLs {date_str}",
                         "content": base64.b64encode(data.encode()).decode()}
        if sha:
            payload["sha"] = sha
        r = requests.put(url, headers=_gh_headers(token), json=payload, timeout=30)
        if r.status_code in (200, 201):
            print(f"  [ok] Dedup: seen_urls.json saved to GitHub ({len(seen)} URLs)")
        else:
            print(f"  [!] Dedup: GitHub save failed {r.status_code}")
    else:
        _LOCAL_SEEN.write_text(data, encoding="utf-8")
        print(f"  [ok] Dedup: seen_urls.json saved locally ({len(seen)} URLs)")


def filter_seen(articles: list[dict], seen: set) -> list[dict]:
    """Remove articles whose URLs have already appeared in a past edition."""
    fresh   = [a for a in articles if a.get("url") not in seen]
    skipped = len(articles) - len(fresh)
    if skipped:
        print(f"  [ok] Dedup: removed {skipped} already-used articles ({len(fresh)} fresh)")
    return fresh


# ── HTML generation ───────────────────────────────────────────────────────────

def key_story_badge_html(story: dict) -> str:
    if not story.get("key_story"):
        return ""
    reason = story.get("key_story_reason", "")
    return f"""
    <div class="key_story-badge">
      <span class="key_story-label">&#9733; Key Story</span>
      {f'<span class="key_story-reason">{reason}</span>' if reason else ""}
    </div>"""


def _fmt_day(d: datetime.date) -> str:
    """Return 'Today', 'Tomorrow', or 'Wednesday, May 7'."""
    today = datetime.date.today()
    if d == today:
        return "Today"
    if d == today + datetime.timedelta(days=1):
        return "Tomorrow"
    try:
        return d.strftime("%A, %B %-d")
    except ValueError:
        return d.strftime("%A, %B %d").replace(" 0", " ")


def build_events_section_html(events: list[dict]) -> str:
    if not events:
        return ""
    cards = ""
    for ev in events:
        title   = ev.get("title", "")
        url     = ev.get("url", "#")
        venue   = ev.get("venue", "")
        location = ev.get("location", "")
        desc    = ev.get("description", "")
        source  = ev.get("source", "")
        date_str_ev = ev.get("date", "")
        time_str = ev.get("time", "")

        date_label = ""
        if date_str_ev:
            try:
                date_label = _fmt_day(datetime.date.fromisoformat(date_str_ev))
            except ValueError:
                date_label = date_str_ev

        venue_parts = [v for v in [venue, location] if v]
        venue_display = ", ".join(dict.fromkeys(venue_parts))

        cards += f"""
  <div class="event-card">
    <div class="event-when">{date_label}</div>
    <div class="event-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></div>
    {f'<div class="event-venue">{venue_display}</div>' if venue_display else ""}
    {f'<div class="event-desc">{desc}</div>' if desc else ""}
    <a class="event-link" href="{url}" target="_blank" rel="noopener">See more &rarr;</a>
  </div>"""

    return f"""<section class="events-section">
  <div class="section-header">
    <span class="section-heading">What&#8217;s On</span>
    <span class="section-sub">Next 3 days &middot; Co. Meath</span>
  </div>
  <div class="events-list">{cards}
  </div>
</section>"""


def build_html(stories: list[dict], date_str: str, weather: list[dict],
               events: list[dict] | None = None) -> str:
    today = datetime.date.fromisoformat(date_str)
    try:
        day_long = today.strftime("%A, %B %-d, %Y")
    except ValueError:
        day_long = today.strftime("%A, %B %d, %Y").replace(" 0", " ")

    key_story_count = sum(1 for s in stories if s.get("key_story"))
    key_story_note  = (
        f'<span class="key_story-count">&#9733; {key_story_count} key {"stories" if key_story_count != 1 else "story"} today</span>'
        if key_story_count else ""
    )

    weather_items = ""
    for w in weather:
        rain_part = (
            f'<span class="weather-rain">{w["rain_mm"]}mm</span>'
            if w["rain_mm"] not in ("--", 0, 0.0) else ""
        )
        weather_items += f"""
    <div class="weather-item">
      <span class="weather-place">{w["name"]}</span>
      <span class="weather-desc">{w["description"]}</span>
      <span class="weather-temps">{w["temp_min"]}–{w["temp_max"]}°C</span>
      {rain_part}
    </div>"""
    weather_html = f"""<div class="weather-bar">
  <div class="section-header">
    <span class="section-heading">Weather</span>
    <span class="section-sub">Today &middot; Co. Meath</span>
  </div>
  <div class="weather-grid">{weather_items}
  </div>
</div>"""

    # Build story cards
    cards_html = ""
    for i, story in enumerate(stories):
        rank     = story.get("rank", i + 1)
        title    = story.get("title", "Untitled")
        source   = story.get("source", "")
        url      = story.get("url", "#")
        category = story.get("category", "")
        teaser   = story.get("teaser", "")
        badge    = key_story_badge_html(story)
        zebra    = "card-alt" if i % 2 == 1 else ""

        cards_html += f"""
  <article class="story-card {zebra}">
    <div class="card-rank">{rank:02d}</div>
    <div class="card-body">
      <div class="card-meta">
        <span class="card-category">{category}</span>
        <span class="card-source">{source}</span>
      </div>
      <h2 class="card-title">
        <a href="{url}" target="_blank" rel="noopener">{title}</a>
      </h2>
      {badge}
      <p class="card-teaser">{teaser}</p>
      <a class="card-link" href="{url}" target="_blank" rel="noopener">Read more &rarr;</a>
    </div>
  </article>"""

    events_html = build_events_section_html(events or [])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Meath Morning Edition — {date_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,700;0,9..144,900;1,9..144,400&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --green: #1A4731;
  --gold:  #B8860B;
  --cream: #FAF7F0;
  --ink:   #1A1A1A;
  --mid:   #555;
  --light: #888;
  --sans:  'Inter', system-ui, sans-serif;
  --serif: 'Fraunces', Georgia, serif;
}}
body {{ font-family: var(--sans); background: var(--cream); color: var(--ink); -webkit-font-smoothing: antialiased; }}

/* ── Masthead ── */
.masthead {{
  background: var(--green);
  color: #fff;
  padding: 2.5rem 2rem 2rem;
  text-align: center;
  border-bottom: 4px solid var(--gold);
}}
.masthead-kicker {{
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.25em;
  text-transform: uppercase;
  color: var(--gold);
  margin-bottom: 0.75rem;
}}
.masthead-title {{
  font-family: var(--serif);
  font-size: clamp(2.5rem, 8vw, 5rem);
  font-weight: 900;
  line-height: 1;
  color: #fff;
  margin-bottom: 0.3em;
}}
.masthead-title em {{
  font-style: italic;
  color: var(--gold);
}}
.masthead-date {{
  font-size: 0.9rem;
  font-weight: 300;
  color: rgba(255,255,255,0.7);
  margin-bottom: 1rem;
}}
.key_story-count {{
  display: inline-block;
  background: #C0392B;
  color: #fff;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 0.3em 0.9em;
  border-radius: 2px;
  margin-bottom: 0.5rem;
}}

/* ── Shared section heading ── */
.section-header {{
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  padding-top: 1.5rem;
  border-top: 2px solid var(--green);
}}
.section-heading {{
  font-family: var(--serif);
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--green);
}}
.section-sub {{
  font-size: 0.68rem;
  color: var(--light);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}}

/* ── Weather bar ── */
.weather-bar {{
  background: #fff;
  border-bottom: 1px solid #e0dbd0;
  padding: 0.5rem 2rem 0.85rem;
}}
.weather-bar .section-header {{
  padding-top: 0.4rem;
  border-top: none;
  margin-bottom: 0.5rem;
}}
.weather-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.4rem 1.25rem;
}}
.weather-item {{
  display: flex;
  flex-direction: column;
  gap: 0.05rem;
  font-size: 0.78rem;
}}
.weather-place {{ font-weight: 600; color: var(--green); font-size: 0.78rem; }}
.weather-desc  {{ color: var(--mid); font-size: 0.73rem; }}
.weather-temps {{ font-weight: 500; }}
.weather-rain  {{ color: #2980b9; font-size: 0.73rem; }}

/* ── Events section ── */
.events-section {{
  max-width: 860px;
  margin: 0 auto 2rem;
  padding: 0 1.5rem;
}}
.events-list {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 1rem;
}}
.event-card {{
  background: #fff;
  border: 1px solid #e0dbd0;
  border-top: 3px solid var(--green);
  padding: 0.9rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-height: 180px;
}}
.event-when {{
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--green);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 0.2rem;
}}
.event-title {{
  font-family: var(--serif);
  font-size: 1.15rem;
  font-weight: 700;
  line-height: 1.25;
}}
.event-title a {{ color: var(--ink); text-decoration: none; }}
.event-title a:hover {{ color: var(--green); }}
.event-venue {{
  font-size: 0.8rem;
  color: var(--light);
}}
.event-desc {{
  font-size: 0.88rem;
  color: var(--mid);
  line-height: 1.55;
  margin-top: 0.25rem;
  flex: 1;
}}
.event-link {{
  display: inline-block;
  margin-top: 0.75rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--green);
  text-decoration: none;
  border-bottom: 1px solid var(--green);
  padding-bottom: 0.05em;
  align-self: flex-start;
}}
.event-link:hover {{ opacity: 0.7; }}

/* ── Story cards ── */
.stories {{
  max-width: 860px;
  margin: 2rem auto;
  padding: 0 1.5rem;
}}
.story-card {{
  display: flex;
  gap: 1.5rem;
  padding: 1.75rem 0;
  border-bottom: 1px solid #e0dbd0;
  align-items: flex-start;
}}
.card-alt {{ background: transparent; }}
.card-rank {{
  font-family: var(--serif);
  font-size: 2.5rem;
  font-weight: 900;
  color: rgba(26,71,49,0.12);
  min-width: 3rem;
  text-align: right;
  line-height: 1;
  padding-top: 0.15em;
  flex-shrink: 0;
}}
.card-body {{ flex: 1; }}
.card-meta {{
  display: flex;
  gap: 0.75rem;
  align-items: center;
  margin-bottom: 0.5rem;
  flex-wrap: wrap;
}}
.card-category {{
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  background: var(--green);
  color: #fff;
  padding: 0.25em 0.7em;
  border-radius: 2px;
}}
.card-source {{
  font-size: 0.72rem;
  color: var(--light);
  font-weight: 500;
}}
.card-title {{
  font-family: var(--serif);
  font-size: clamp(1.2rem, 3vw, 1.6rem);
  font-weight: 700;
  line-height: 1.2;
  margin-bottom: 0.6rem;
}}
.card-title a {{
  color: var(--ink);
  text-decoration: none;
}}
.card-title a:hover {{ color: var(--green); }}
.key_story-badge {{
  display: inline-flex;
  flex-direction: column;
  gap: 0.2rem;
  border-left: 3px solid #C0392B;
  padding: 0.4rem 0.8rem;
  margin-bottom: 0.75rem;
  background: #fdf0ee;
}}
.key_story-label {{
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #C0392B;
}}
.key_story-reason {{
  font-size: 0.8rem;
  color: #C0392B;
  line-height: 1.4;
}}
.card-teaser {{
  font-size: 0.95rem;
  line-height: 1.65;
  color: var(--mid);
  margin-bottom: 0.75rem;
}}
.card-link {{
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--green);
  text-decoration: none;
  border-bottom: 1px solid var(--green);
  padding-bottom: 0.05em;
}}
.card-link:hover {{ opacity: 0.7; }}

/* ── Footer ── */
.footer {{
  text-align: center;
  padding: 2.5rem 1rem;
  font-size: 0.75rem;
  color: var(--light);
  border-top: 1px solid #e0dbd0;
  margin-top: 1rem;
}}

@media (max-width: 560px) {{
  .card-rank {{ display: none; }}
  .story-card {{ padding: 1.25rem 0; }}
}}
</style>
</head>
<body>

<header class="masthead">
  <div class="masthead-kicker">County Meath &nbsp;·&nbsp; Local Intelligence</div>
  <h1 class="masthead-title">Meath <em>Morning</em><br>Edition</h1>
  <div class="masthead-date">{day_long}</div>
  {key_story_note}
</header>

{weather_html}

<main class="stories">
  <div class="section-header">
    <span class="section-heading">News</span>
    <span class="section-sub">Today&rsquo;s edition</span>
  </div>
{cards_html}
</main>

{events_html}

<footer class="footer">
  <p>Meath Morning Edition &nbsp;·&nbsp; {date_str}</p>
  <p style="margin-top:0.4rem;">Sources: Meath Live &nbsp;·&nbsp; Meath Chronicle &nbsp;·&nbsp; Google Alert</p>
</footer>

</body>
</html>"""


# ── Copy-paste HTML (for Beehiiv free editor) ─────────────────────────────────

def build_copypaste_html(stories: list[dict], date_str: str, weather: list[dict],
                         events: list[dict] | None = None) -> str:
    """Minimal inline-styled HTML for pasting into Beehiiv's free editor."""
    today = datetime.date.fromisoformat(date_str)
    try:
        day_long = today.strftime("%A, %B %-d, %Y")
    except ValueError:
        day_long = today.strftime("%A, %B %d, %Y").replace(" 0", " ")

    lines = []
    lines.append(f'<p style="color:#888;font-size:13px;font-family:sans-serif;">Meath Morning Edition &nbsp;·&nbsp; {day_long}</p>')

    # Weather — compact one-liner per town
    weather_parts = [
        f"{w['name']}: {w['description']}, {w['temp_min']}–{w['temp_max']}°C"
        for w in weather
    ]
    lines.append(f'<p style="font-size:12px;font-family:sans-serif;color:#555;">'
                 f'<strong>Weather:</strong> {" &nbsp;|&nbsp; ".join(weather_parts)}</p>')
    lines.append('<hr style="border:none;border-top:2px solid #1A4731;margin:16px 0;">')

    # Events section
    if events:
        lines.append('<p style="font-size:13px;font-family:Georgia,serif;font-weight:700;color:#1A4731;margin:0 0 8px;">What\'s On — Next 3 Days</p>')
        for ev in events:
            title = ev.get("title", "")
            url   = ev.get("url", "#")
            date_ev = ev.get("date", "")
            time_ev = ev.get("time", "")
            venue   = ev.get("venue", "")
            location = ev.get("location", "")
            desc  = ev.get("description", "")
            when  = ""
            if date_ev:
                try:
                    when = _fmt_day(datetime.date.fromisoformat(date_ev))
                except ValueError:
                    when = date_ev
            venue_parts = [v for v in [venue, location] if v]
            venue_display = ", ".join(dict.fromkeys(venue_parts))
            lines.append(f'<p style="font-size:11px;color:#1A4731;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin:8px 0 2px;">{when}</p>')
            lines.append(f'<p style="font-family:Georgia,serif;font-size:15px;margin:0 0 4px;"><a href="{url}" style="color:#1A1A1A;text-decoration:none;">{title}</a></p>')
            if venue_display:
                lines.append(f'<p style="font-size:11px;color:#888;margin:0 0 4px;">{venue_display}</p>')
            if desc:
                lines.append(f'<p style="font-size:13px;color:#555;margin:0 0 6px;">{desc}</p>')
        lines.append('<hr style="border:none;border-top:2px solid #1A4731;margin:16px 0;">')

    for story in stories:
        title    = story.get("title", "")
        url      = story.get("url", "#")
        source   = story.get("source", "")
        category = story.get("category", "")
        teaser   = story.get("teaser", "")
        key_story   = story.get("key_story", False)
        reason   = story.get("key_story_reason", "")

        lines.append(f'<p style="font-size:11px;font-family:sans-serif;color:#1A4731;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:4px;">{category} &nbsp;·&nbsp; {source}</p>')
        lines.append(f'<h3 style="font-family:Georgia,serif;font-size:20px;margin:0 0 8px;"><a href="{url}" style="color:#1A1A1A;text-decoration:none;">{title}</a></h3>')
        if key_story and reason:
            lines.append(f'<p style="font-size:12px;color:#1A4731;border-left:3px solid #1A4731;padding-left:8px;margin:6px 0;">&#9733; Key Story: {reason}</p>')
        lines.append(f'<p style="font-family:sans-serif;font-size:14px;color:#555;line-height:1.6;margin:0 0 6px;">{teaser}</p>')
        lines.append(f'<p style="margin:0 0 20px;"><a href="{url}" style="font-size:13px;color:#1A4731;font-weight:600;">Read more &rarr;</a></p>')
        lines.append('<hr style="border:none;border-top:1px solid #e0dbd0;margin:0 0 20px;">')

    lines.append('<p style="font-size:11px;color:#aaa;font-family:sans-serif;">Sources: Meath Live · Meath Chronicle · Google Alert</p>')

    return "\n".join(lines)


# ── RSS feed ──────────────────────────────────────────────────────────────────

def update_rss(stories: list[dict], date_str: str, pages_url: str | None,
               copypaste_html: str):
    """
    Maintain an RSS feed file (rss.xml) in the newsletters dir.
    Keeps the last 30 issues. Suitable for Beehiiv RSS-to-Send.
    """
    rss_path = NEWSLETTERS_DIR / "rss.xml"
    today = datetime.date.fromisoformat(date_str)
    try:
        day_long = today.strftime("%A, %B %-d, %Y")
    except ValueError:
        day_long = today.strftime("%A, %B %d, %Y").replace(" 0", " ")

    pub_date = datetime.datetime.now().strftime("%a, %d %b %Y 07:00:00 +0100")

    github_repo = os.environ.get("GITHUB_REPO_MEATH", "")
    if github_repo:
        username, reponame = github_repo.split("/", 1)
        base_url  = f"https://{username}.github.io/{reponame}"
        issue_url = pages_url or f"{base_url}/issues/{date_str}.html"
        feed_url  = f"{base_url}/rss.xml"
    else:
        issue_url = f"file:///{(NEWSLETTERS_DIR / f'{date_str}.html').as_posix()}"
        feed_url  = "http://localhost/rss.xml"

    # Build new item (content = copy-paste HTML for Beehiiv)
    import xml.sax.saxutils as saxutils
    escaped_content = saxutils.escape(copypaste_html)

    new_item = f"""    <item>
      <title>Meath Morning Edition — {day_long}</title>
      <link>{issue_url}</link>
      <guid isPermaLink="true">{issue_url}</guid>
      <pubDate>{pub_date}</pubDate>
      <description>Your daily County Meath news briefing for {day_long}.</description>
      <content:encoded><![CDATA[{copypaste_html}]]></content:encoded>
    </item>"""

    # Read existing items or start fresh
    existing_items = []
    if rss_path.exists():
        raw = rss_path.read_text(encoding="utf-8")
        existing_items = re.findall(r"<item>.*?</item>", raw, re.DOTALL)

    # Prepend new item, keep last 30
    all_items = [new_item] + [i for i in existing_items if date_str not in i]
    all_items = all_items[:30]

    rss_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Meath Morning Edition</title>
    <link>{feed_url}</link>
    <description>Daily curated local news for County Meath, Ireland.</description>
    <language>en-ie</language>
    <lastBuildDate>{pub_date}</lastBuildDate>
{chr(10).join(all_items)}
  </channel>
</rss>"""

    rss_path.write_text(rss_xml, encoding="utf-8")
    print(f"  [ok] RSS feed updated: {rss_path}")
    return rss_path


# ── GitHub Pages publishing ───────────────────────────────────────────────────

def publish_to_github(html: str, date_str: str, rss_path: Path | None = None) -> str | None:
    token = os.environ.get("GITHUB_TOKEN_MEATH") or os.environ.get("GITHUB_TOKEN")
    repo  = os.environ.get("GITHUB_REPO_MEATH")
    if not token or not repo:
        return None

    import base64
    api = "https://api.github.com"
    gh_headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }

    def put_file(file_path: str, content_bytes: bytes, message: str):
        url = f"{api}/repos/{repo}/contents/{file_path}"
        sha = None
        r = requests.get(url, headers=gh_headers, timeout=15)
        if r.status_code == 200:
            sha = r.json().get("sha")
        payload: dict = {"message": message, "content": base64.b64encode(content_bytes).decode()}
        if sha:
            payload["sha"] = sha
        r = requests.put(url, headers=gh_headers, json=payload, timeout=30)
        return r.status_code in (200, 201)

    # Push HTML issue
    ok = put_file(f"issues/{date_str}.html", html.encode(), f"Add Morning Edition {date_str}")
    if not ok:
        print(f"  [!] GitHub publish failed for HTML")
        return None

    username, reponame = repo.split("/", 1)
    pages_url = f"https://{username}.github.io/{reponame}/issues/{date_str}.html"

    # Push RSS feed
    if rss_path and rss_path.exists():
        put_file("rss.xml", rss_path.read_bytes(), f"Update RSS feed {date_str}")

    # Update index redirect
    index_html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Meath Morning Edition</title>
<meta http-equiv="refresh" content="0; url={pages_url}">
</head><body><p>Redirecting to <a href="{pages_url}">latest edition</a>...</p></body></html>"""
    put_file("index.html", index_html.encode(), f"Update index to {date_str}")

    print(f"  [ok] Published to GitHub Pages: {pages_url}")
    return pages_url


# ── Email delivery ────────────────────────────────────────────────────────────

def send_email(date_str: str, pages_url: str | None, output_path: Path):
    gmail_user = os.environ.get("GMAIL_ADDRESS")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_pass:
        return

    email_to = os.environ.get("EMAIL_TO", gmail_user)
    today = datetime.date.fromisoformat(date_str)
    try:
        day_long = today.strftime("%A, %B %-d, %Y")
    except ValueError:
        day_long = today.strftime("%A, %B %d, %Y").replace(" 0", " ")

    link = pages_url or f"file:///{output_path.as_posix()}"
    body_html = f"""
    <div style="font-family:Georgia,serif;max-width:600px;margin:0 auto;padding:2rem;">
      <p style="font-size:0.8rem;color:#888;letter-spacing:0.1em;text-transform:uppercase;">
        Meath Morning Edition
      </p>
      <h1 style="font-size:2rem;margin:0.5rem 0 1rem;color:#1A4731;">Your Meath briefing is ready</h1>
      <p style="font-size:1rem;color:#555;">{day_long}</p>
      <a href="{link}"
         style="display:inline-block;margin:1.5rem 0;padding:0.85rem 2rem;
                background:#1A4731;color:#fff;text-decoration:none;
                font-family:sans-serif;font-size:0.9rem;letter-spacing:0.05em;">
        Read Meath Morning Edition &rarr;
      </a>
      <p style="font-size:0.8rem;color:#aaa;">
        Curated from Meath Live, Meath Chronicle &amp; Google Alert.
      </p>
    </div>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Meath Morning Edition — {day_long}"
    msg["From"]    = gmail_user
    msg["To"]      = email_to
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(gmail_user, gmail_pass)
            smtp.sendmail(gmail_user, email_to, msg.as_string())
        print(f"  [ok] Email sent to {email_to}")
    except Exception as e:
        print(f"  [!] Email failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    date_str    = datetime.date.today().isoformat()
    output_path = NEWSLETTERS_DIR / f"{date_str}.html"
    copypaste_path = NEWSLETTERS_DIR / f"{date_str}-copypaste.html"

    if "--force" not in sys.argv and output_path.exists():
        print(f"Today's edition already exists: {output_path}")
        print("Pass --force to regenerate.")
        return

    print(f"\nMeath Morning Edition -- {date_str}\n" + "-" * 50)

    seen = load_seen_urls()

    weather = get_weather()
    navan = weather[0]
    print(f"  [ok] Weather: {navan['description']}, {navan['temp_min']}-{navan['temp_max']}C ({len(weather)} locations)\n")

    raw_articles = fetch_all_stories()
    if not raw_articles:
        print("No articles fetched -- aborting.")
        sys.exit(1)

    if "--force" not in sys.argv:
        raw_articles = filter_seen(raw_articles, seen)
        if not raw_articles:
            print("No fresh articles after deduplication -- aborting.")
            sys.exit(1)
    else:
        print("  [--force] Skipping deduplication filter.")

    stories = curate_with_claude(raw_articles)
    seen.update(s["url"] for s in stories if s.get("url"))
    save_seen_urls(seen, date_str)

    raw_events = fetch_all_events()
    events = curate_events_with_claude(raw_events)

    html          = build_html(stories, date_str, weather, events)
    copypaste_html = build_copypaste_html(stories, date_str, weather, events)

    output_path.write_text(html, encoding="utf-8")
    copypaste_path.write_text(copypaste_html, encoding="utf-8")
    print(f"[DONE]  Saved: {output_path}")
    print(f"        Copy-paste: {copypaste_path}")

    pages_url = publish_to_github(html, date_str)

    rss_path = update_rss(stories, date_str, pages_url, copypaste_html)

    if pages_url:
        # Push RSS after page is live
        pass  # already pushed inside publish_to_github

    send_email(date_str, pages_url, output_path)

    if pages_url:
        print(f"   URL:  {pages_url}")
    else:
        print(f"   Open: file:///{output_path.as_posix()}")


if __name__ == "__main__":
    main()
