Live Cricket Scraper — README

This project scrapes live cricket matches from radheexch.xyz and enriches them with per-match details by visiting each event page. It outputs a single JSON snapshot you can serve to a frontend or inspect locally.

It collects for each live/scheduled match:

Lobby odds (1 / X / 2)

Per-event “Match Odds / Winner” ladders

“Bookmaker 0 Commission” ladders (when available)

Fancy bets table (Yes/No with sizes)

Sessions (placeholder for now)

Result (placeholder for now)

1) Features at a glance

Headed Playwright (default) so you can watch what’s happening.

API-assisted discovery of event IDs from https://api.radheexch.xyz/delaymarkets/markets/eventtype/4, with robust parsing (handles dict/list shapes).

Concurrent event-page scraping, with polite limits.

Crash-safe output via atomic writes to data/live.json.

Debug artifacts saved to data/ (last API payload, lobby HTML/screenshot, simple log).

2) Requirements

Python 3.10+ (3.11 recommended)

Playwright + browsers

pip and virtualenv (optional but recommended)

Internet access to radheexch.xyz and api.radheexch.xyz

3) Install
# from your project root
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt

# Install browsers for Playwright (first time only)
python -m playwright install

Minimal requirements.txt

playwright>=1.46.0
httpx>=0.27.0
tenacity>=8.2.3
tomli>=2.0.1

4) Configuration

By default, the scraper uses sane settings bundled in code.
If a config.example.toml is present, its values override the defaults.

Optional config.example.toml

[site]
lobby_url   = "https://www.radheexch.xyz/game/4"
event_base  = "https://www.radheexch.xyz/event/4/"
api_eventtype = "https://api.radheexch.xyz/delaymarkets/markets/eventtype/4"

[scrape]
interval_seconds = 20
headless = false         # set true to hide browser
max_lobby = 25
max_events = 20
event_concurrency = 4
navigation_timeout_ms = 45000
selector_timeout_ms = 7000
debug_artifacts = true

[io]
outfile   = "data/live.json"
tempfile  = "data/.live.tmp"
log       = "data/scraper.log"
last_api  = "data/last_api.json"
lobby_html = "data/lobby.html"
lobby_png  = "data/lobby.png"

[http]
timeout = 12
[http.headers]
Accept = "application/json, text/plain, */*"
Referer = "https://www.radheexch.xyz/"
Origin  = "https://www.radheexch.xyz"
User-Agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit(537.36) (KHTML, like Gecko) Chrome/126 Safari/537.36"


5) Run 
python scraper.py

You’ll see periodic logs like:

[2025-10-22 08:24:57] API returned 34 event ids (showing up to 20).
[2025-10-22 08:24:57] Wrote snapshot @ 2025-10-22T02:54:57.604104+00:00 | lobby rows: 9 | events scraped: 8


Artifacts are written to data/:

live.json — the latest combined snapshot (atomic write)

.live.tmp — temp file during writes

scraper.log — simple text log

last_api.json — raw API dump for debugging

lobby.html — captured lobby HTML

lobby.png — lobby screenshot

6) Output format
data/live.json

{
  "fetched_at": "2025-10-22T02:54:57.604104+00:00",
  "lobby": [
    {
      "match_id": "Pakistan-v-South-Africa",
      "title": "20 Oct 10:30 | Pakistan v South Africa",
      "teams": ["Pakistan","South Africa"],
      "starts_at": "20 Oct 10:30",
      "status": "live",
      "one":  [4.0, 4.1],          // left team best_back, best_lay
      "draw": [11.5, 12.0],
      "two":  [1.49, 1.50]         // right team best_back, best_lay
    }
    // ...
  ],
  "events": {
    "34848333": {
      "title": "Pakistan v South Africa - Test Matches",
      "match_time": "20/10/2025 10:30",
      "runners": {
        "Pakistan": {
          "best_back": 1.55,
          "best_lay": 1.56,
          "ladder": [
            {"back":1.53,"back_size":"13.6K","lay":1.56,"lay_size":"16.7"},
            {"back":1.54,"back_size":"1.9K","lay":1.57,"lay_size":"547.3"},
            {"back":1.55,"back_size":"27.1","lay":1.58,"lay_size":"867.7"}
          ]
        },
        "South Africa": { "...": "..." },
        "The Draw": { "...": "..." }
      },
      "bookmaker_zero_commission": {
        "Pakistan": { "best_back": null, "best_lay": null, "ladder": [] },
        "South Africa": { "best_back": null, "best_lay": null, "ladder": [] },
        "The Draw": { "best_back": null, "best_lay": null, "ladder": [] }
      },
      "bookmaker_zero_commission_suspended": true,
      "fancy": [
        {"name":"5th Wkt SA","no":207,"no_size":"110","yes":207,"yes_size":"90","limits":"Max:50K MKT:500K"},
        {"name":"T Stubbs Runs","no":93,"no_size":"110","yes":93,"yes_size":"90","limits":"Max:50K MKT:500K"}
      ],
      "sessions": [],
      "result": null,
      "source_url": "https://www.radheexch.xyz/event/4/34848333"
    }
    // other event ids...
  },
  "live_details": {
    "Pakistan-v-South-Africa": {
      "event_id": "34848333",
      "title": "Pakistan v South Africa - Test Matches",
      "match_time": "20/10/2025 10:30",
      "bookmaker": {
        "Pakistan": {"back": 1.55, "lay": 1.56},
        "South Africa": {"back": 3.6, "lay": 3.7},
        "The Draw": {"back": 11.5, "lay": 12.0}
      },
      "fancy": [ /* same objects as above */ ],
      "sessions": [],
      "result": null
    }
  }
}


Field notes

lobby: extracted from the lobby table (/game/4) — quick scan odds.

events: deep data scraped from each event page:

runners is “Match Odds / Winner” market with three-level ladders for each selection.

bookmaker_zero_commission mirrors the second market when available (including suspension).

fancy entries are from the Fancy table (Yes/No prices + sizes + limits when present).

live_details: a convenient mapping keyed by a slugified title (e.g., Pakistan-v-South-Africa) → merges the most useful per-event fields for consumption.

7) How it works (high level)

Open lobby with Playwright, parse the cricket table rows.

Call the API (/eventtype/4) to discover event IDs.

The response can vary (list/dict); we walk the entire JSON recursively to extract plausible numeric ids.

The last raw response is saved to data/last_api.json.

For each selected event id, open https://www.radheexch.xyz/event/4/<id>:

Parse Match Odds / Winner market ladders.

Parse Bookmaker 0 Commission (and record if suspended).

Parse Fancy table (Yes/No).

(Sessions, Result: placeholders until we see stable DOM examples.)

Write a single snapshot to data/live.json.

8) Troubleshooting

403 from API: Too many requests or geo/CDN rules. The scraper retries automatically. If it persists, slow the interval or add backoff at the config level.

API changed shape: Open data/last_api.json to see what came back. The id collector is resilient, but if no ids are found, adjust the heuristics or temporarily comment event scraping.

Selectors not found: The site may update DOM. Run headed (headless=false) and watch DevTools (PWDEBUG=1 can help). Update CSS selectors inside parse_event_page(...).

“events scraped: 0”: Often means the API returned ids that are not for match pages yet, the pages are loading slowly, or the selector timeout is too low. Increase selector_timeout_ms/navigation_timeout_ms.

Windows path issues: Ensure your working directory is where scraper.py lives so relative data/ paths resolve correctly.

9) Safety & Terms

Respect the target website’s Terms of Service and robots, and ensure you have permission to scrape.

Be considerate with rate limits: tune interval_seconds, event_concurrency.

This code is provided as-is; scraping UIs/APIs can break without notice.

10) Extending

Sessions & Result: Add concrete selectors once you capture example HTML (similar to Fancy parsing).

Data sink: Replace JSON with a DB writer (e.g., Postgres) in run_once(...).

Headless prod: Set headless=true and run under a supervisor (systemd, PM2, Docker, etc.).

11) Quick dev loop

Keep headless=false.

Run python scraper.py.

Inspect:

data/lobby.png to confirm lobby parsing

data/last_api.json to see real API shape

data/live.json for output correctness

Adjust selectors or timeouts as needed.

