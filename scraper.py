# scraper.py
import asyncio
import contextlib
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx
import tomli
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright, BrowserContext, Page

# =============================================================================
# Config (toml optional)
# =============================================================================

DEFAULT_CFG = {
    "site": {
        "lobby_url": "https://www.radheexch.xyz/game/4",
        "event_base": "https://www.radheexch.xyz/event/4/",
        "api_eventtype": "https://api.radheexch.xyz/delaymarkets/markets/eventtype/4",
    },
    "scrape": {
        "interval_seconds": 20,
        "headless": False,            # show the browser so you can watch
        "max_lobby": 25,
        "max_events": 20,
        "event_concurrency": 4,
        "navigation_timeout_ms": 45000,
        "selector_timeout_ms": 7000,
        "debug_artifacts": True,
    },
    "io": {
        "outfile": "data/live.json",
        "tempfile": "data/.live.tmp",
        "log": "data/scraper.log",
        "last_api": "data/last_api.json",
        "lobby_html": "data/lobby.html",
        "lobby_png": "data/lobby.png",
    },
    "http": {
        "timeout": 12,
        "headers": {
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.radheexch.xyz/",
            "Origin": "https://www.radheexch.xyz",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit(537.36) (KHTML, like Gecko) "
                "Chrome/126 Safari/537.36"
            ),
        },
    },
}

def load_cfg() -> dict:
    path = "config.example.toml"
    if os.path.exists(path):
        with open(path, "rb") as f:
            user = tomli.load(f)
        cfg = DEFAULT_CFG.copy()
        for k, v in user.items():
            if isinstance(v, dict) and k in cfg and isinstance(cfg[k], dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
        return cfg
    return DEFAULT_CFG

# =============================================================================
# Models
# =============================================================================

@dataclass
class BookmakerLadderStep:
    back: Optional[float] = None
    back_size: str = ""
    lay: Optional[float] = None
    lay_size: str = ""

@dataclass
class TeamOdds:
    best_back: Optional[float] = None
    best_lay: Optional[float] = None
    ladder: List[BookmakerLadderStep] = field(default_factory=list)

@dataclass
class EventSnapshot:
    title: Optional[str] = None
    match_time: Optional[str] = None
    bookmaker_odds: Dict[str, TeamOdds] = field(default_factory=dict)
    bookmaker_zero_commission: Dict[str, TeamOdds] = field(default_factory=dict)
    bookmaker_zero_commission_suspended: bool = False
    fancy: List[Dict[str, Any]] = field(default_factory=list)
    sessions: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[str] = None
    source_url: Optional[str] = None

@dataclass
class LobbyRow:
    match_id: str = ""
    title: str = ""
    teams: List[str] = field(default_factory=list)
    starts_at: Optional[str] = None
    status: str = "scheduled"
    one: Tuple[Optional[float], Optional[float]] = (None, None)
    draw: Tuple[Optional[float], Optional[float]] = (None, None)
    two: Tuple[Optional[float], Optional[float]] = (None, None)

# =============================================================================
# Utils
# =============================================================================

NUM = re.compile(r"[0-9]+(?:\.[0-9]+)?")

def first_float(txt: Optional[str]) -> Optional[float]:
    if not txt:
        return None
    m = NUM.search(txt.replace(",", "."))
    return float(m.group(0)) if m else None

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def atomic_write(path: str, tmp_path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp_path, path)

async def text_of(el) -> Optional[str]:
    if not el:
        return None
    try:
        return (await el.inner_text()).strip()
    except Exception:
        return None

def slugify_title(title: str) -> str:
    t = re.sub(r"\s+", "-", title.strip())
    t = re.sub(r"[^A-Za-z0-9\-]+", "-", t)
    t = re.sub(r"-{2,}", "-", t)
    return t.strip("-")

async def screenshot(page: Page, path: str):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        await page.screenshot(path=path, full_page=True)
    except Exception:
        pass

async def save_html(page: Page, path: str):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(await page.content())
    except Exception:
        pass

def log(msg: str, cfg: dict):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(cfg["io"]["log"]), exist_ok=True)
        with open(cfg["io"]["log"], "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

# =============================================================================
# API – event id discovery (robust for dict/list shapes)
# =============================================================================

@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=10))
async def fetch_eventtype_api(cfg: dict) -> Union[Dict[str, Any], List[Any]]:
    url = cfg["site"]["api_eventtype"]
    async with httpx.AsyncClient(timeout=cfg["http"]["timeout"], headers=cfg["http"]["headers"], follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
        # stash last API response for debugging
        try:
            os.makedirs(os.path.dirname(cfg["io"]["last_api"]), exist_ok=True)
            with open(cfg["io"]["last_api"], "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return data

def _maybe_id(value: Any) -> Optional[str]:
    """
    Return a string event id if `value` looks like one (>=5 digits).
    """
    if value is None:
        return None
    s = str(value)
    return s if re.fullmatch(r"\d{5,}", s) else None

def _collect_ids_recursive(node: Any, bucket: set):
    """
    Walk arbitrary JSON to collect plausible event ids.
    Looks for keys: eventId, event_id, eventid, id under 'event', etc.
    """
    if isinstance(node, dict):
        # direct keys that might be ids (e.g., {"34848333": {...}})
        for k in list(node.keys()):
            kid = _maybe_id(k)
            if kid:
                bucket.add(kid)

        # value-based detection
        for k, v in node.items():
            kl = k.lower()
            if kl in ("eventid", "event_id", "event_id_pk", "eventpk", "eventpkid", "id"):
                # prefer when nested under an 'event' object or clearly numeric
                if isinstance(v, (str, int)):
                    vid = _maybe_id(v)
                    if vid:
                        bucket.add(vid)
            # common shapes: {"event": {"id": 34848333, ...}}
            if kl == "event" and isinstance(v, dict):
                inner_id = v.get("id") if "id" in v else v.get("eventId") or v.get("event_id")
                vid = _maybe_id(inner_id)
                if vid:
                    bucket.add(vid)

            # keep walking
            _collect_ids_recursive(v, bucket)

    elif isinstance(node, list):
        for item in node:
            _collect_ids_recursive(item, bucket)

def collect_event_ids(api_json: Union[Dict[str, Any], List[Any]]) -> List[str]:
    ids: set = set()
    _collect_ids_recursive(api_json, ids)

    # specific extra hook for {"events": {...}} dict seen in your earlier sample
    if isinstance(api_json, dict):
        events = api_json.get("events")
        if isinstance(events, dict):
            for k in events.keys():
                kid = _maybe_id(k)
                if kid:
                    ids.add(kid)

    return list(sorted(ids))

# =============================================================================
# Playwright setup
# =============================================================================

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
async def open_context(cfg: dict) -> Tuple[BrowserContext, Page]:
    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        user_data_dir=os.path.abspath("./.pwstate"),
        headless=cfg["scrape"]["headless"] is True and not os.getenv("PWDEBUG"),
        viewport={"width": 1420, "height": 920},
        ignore_https_errors=True,
        user_agent=cfg["http"]["headers"]["User-Agent"],
    )
    page = await context.new_page()
    await page.goto(cfg["site"]["lobby_url"], wait_until="networkidle", timeout=cfg["scrape"]["navigation_timeout_ms"])
    return context, page

# =============================================================================
# Lobby scraping
# =============================================================================

async def _best_from_cell(cell) -> Tuple[Optional[float], Optional[float]]:
    back = None
    for n in await cell.query_selector_all("a.btn-back div"):
        v = first_float(await text_of(n))
        if v is not None:
            back = v
    lay = None
    for n in await cell.query_selector_all("a.btn-lay div"):
        v = first_float(await text_of(n))
        if v is not None:
            lay = v
            break
    return back, lay

async def scrape_lobby(page: Page, cfg: dict) -> List[LobbyRow]:
    await page.goto(cfg["site"]["lobby_url"], wait_until="networkidle", timeout=cfg["scrape"]["navigation_timeout_ms"])
    await asyncio.sleep(0.5)

    rows = await page.query_selector_all("div.cricket table.game-list-col tbody tr")
    out: List[LobbyRow] = []
    for r in rows:
        title_el = await r.query_selector(".event-title")
        if not title_el:
            continue

        dt_el = await title_el.query_selector(".dtime")
        dt = (" ".join(((await text_of(dt_el)) or "").split())).rstrip("|").strip()

        full = " ".join(((await text_of(title_el)) or "").split())
        title_clean = full
        if dt and title_clean.startswith(dt):
            title_clean = title_clean[len(dt):].strip()
            title_clean = title_clean.lstrip("|").strip()

        if " v " not in title_clean:
            continue

        a, b = [t.strip() for t in title_clean.split(" v ", 1)]
        slug = slugify_title(f"{a} v {b}")
        is_live = await r.query_selector(".livenownew, .lvnow") is not None

        visit = await r.query_selector(".col-visit")
        draw  = await r.query_selector(".col-draw")
        home  = await r.query_selector(".col-home")

        one  = await _best_from_cell(visit) if visit else (None, None)
        x    = await _best_from_cell(draw)  if draw  else (None, None)
        two  = await _best_from_cell(home)  if home  else (None, None)

        out.append(LobbyRow(
            match_id=slug,
            title=f"{dt} | {a} v {b}",
            teams=[a, b],
            starts_at=dt or None,
            status="live" if is_live else "scheduled",
            one=one, draw=x, two=two
        ))

        if len(out) >= cfg["scrape"]["max_lobby"]:
            break

    return out

# =============================================================================
# Event page scraping
# =============================================================================

async def _read_ladder_cells(tr) -> Tuple[List[BookmakerLadderStep], Optional[float], Optional[float]]:
    ladder: List[BookmakerLadderStep] = []

    back_as = await tr.query_selector_all("a.btn-back")
    lay_as  = await tr.query_selector_all("a.btn-lay")

    backs: List[Tuple[Optional[float], str]] = []
    lays : List[Tuple[Optional[float], str]] = []

    for a in back_as:
        v = first_float(await text_of(await a.query_selector("div")))
        sz = (await text_of(await a.query_selector(".bid-price-small"))) or ""
        backs.append((v, sz))
    for a in lay_as:
        v = first_float(await text_of(await a.query_selector("div")))
        sz = (await text_of(await a.query_selector(".ask-price-small"))) or ""
        lays.append((v, sz))

    for i in range(max(len(backs), len(lays))):
        b = backs[i] if i < len(backs) else (None, "")
        l = lays[i]  if i < len(lays)  else (None, "")
        ladder.append(BookmakerLadderStep(back=b[0], back_size=b[1], lay=l[0], lay_size=l[1]))

    best_back = max([v for v, _ in backs if v is not None], default=None)
    best_lay  = min([v for v, _ in lays if v is not None], default=None)
    return ladder, best_back, best_lay

async def parse_event_page(page: Page, url: str, cfg: dict) -> Tuple[str, EventSnapshot]:
    snap = EventSnapshot(source_url=url)

    # Title + time
    try:
        hdr = await page.query_selector("div.col-centersdetails.markets .sub_path.center-box.crname p")
        if hdr:
            t1 = await hdr.query_selector("span:nth-of-type(1)")
            t2 = await hdr.query_selector("span:nth-of-type(2)")
            snap.title = (await text_of(t1)) or None
            snap.match_time = (await text_of(t2)) or None
    except Exception:
        pass

    async def find_box(*keywords: str):
        for bx in await page.query_selector_all("div.live-match"):
            h = await bx.query_selector(".sub_path.center-box.crname")
            ht = ((await text_of(h)) or "").lower()
            if any(k in ht for k in keywords):
                return bx
        return None

    # Match Odds / Winner
    winner = await find_box("winner", "match odds", "matchodds")
    if not winner:
        for bx in await page.query_selector_all("div.live-match"):
            if await bx.query_selector("table.eventdetails.bets tbody tr .in-play-title"):
                winner = bx
                break

    if winner:
        for tr in await winner.query_selector_all("table.eventdetails.bets tbody tr"):
            name_el = await tr.query_selector(".in-play-title")
            if not name_el:
                continue
            name = " ".join(((await text_of(name_el)) or "").split())
            if not name:
                continue
            ladder, bb, bl = await _read_ladder_cells(tr)
            snap.bookmaker_odds[name] = TeamOdds(best_back=bb, best_lay=bl, ladder=ladder)

    # Bookmaker 0 Commission
    bm = await find_box("bookmaker 0 commission", "bookmaker")
    if bm:
        snap.bookmaker_zero_commission_suspended = await bm.query_selector(".suspended-event") is not None
        for tr in await bm.query_selector_all("table.eventdetails.bets tbody tr"):
            name_el = await tr.query_selector(".in-play-title")
            if not name_el:
                continue
            name = " ".join(((await text_of(name_el)) or "").split())
            if not name:
                continue
            ladder, bb, bl = await _read_ladder_cells(tr)
            snap.bookmaker_zero_commission[name] = TeamOdds(best_back=bb, best_lay=bl, ladder=ladder)

    # Fancy
    ft = await page.query_selector("table.fancytable")
    if ft:
        for tr in await ft.query_selector_all("tbody > tr"):
            nm_el = await tr.query_selector(".marketnamemobile")
            if not nm_el:
                continue
            nm = " ".join(((await text_of(nm_el)) or "").split())
            if not nm:
                continue

            no_a  = await tr.query_selector("a.btn-lay div")
            no_sz = await tr.query_selector("a.btn-lay .ask-price-small")
            yes_a = await tr.query_selector("a.btn-back div")
            yes_sz= await tr.query_selector("a.btn-back .bid-price-small")
            maxel = await tr.query_selector(".min-max-price")

            rec = {
                "name": nm,
                "no": first_float(await text_of(no_a)),
                "no_size": (await text_of(no_sz)) or "",
                "yes": first_float(await text_of(yes_a)),
                "yes_size": (await text_of(yes_sz)) or "",
            }
            if maxel:
                rec["limits"] = " ".join(((await text_of(maxel)) or "").split())
            snap.fancy.append(rec)

    # Sessions + Result (placeholders; fill when you see them)
    snap.sessions = []
    snap.result = None

    # mapping key from event title (before ' - ')
    key = ""
    if snap.title:
        base = snap.title.split(" - ", 1)[0].strip()
        if base:
            key = slugify_title(base)
    return key, snap

async def scrape_event_by_id(context: BrowserContext, event_id: str, cfg: dict) -> Tuple[str, EventSnapshot]:
    url = cfg["site"]["event_base"] + str(event_id)
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=cfg["scrape"]["navigation_timeout_ms"])
        await page.wait_for_selector(
            "div.col-centersdetails.markets, table.eventdetails.bets, table.fancytable",
            timeout=cfg["scrape"]["selector_timeout_ms"]
        )
        key, snap = await parse_event_page(page, url, cfg)
        return key, snap
    except Exception as e:
        log(f"EVENT {event_id}: parse failed: {e!r}", cfg)
        return "", EventSnapshot(source_url=url)
    finally:
        await page.close()

# =============================================================================
# One cycle
# =============================================================================

async def run_once(context: BrowserContext, page: Page, cfg: dict) -> dict:
    # lobby first
    lobby = await scrape_lobby(page, cfg)

    if cfg["scrape"]["debug_artifacts"]:
        await save_html(page, cfg["io"]["lobby_html"])
        await screenshot(page, cfg["io"]["lobby_png"])

    live_details: Dict[str, Dict[str, Any]] = {}
    events_store: Dict[str, Dict[str, Any]] = {}

    try:
        api_json = await fetch_eventtype_api(cfg)
        ids = collect_event_ids(api_json)
        if ids:
            log(f"API returned {len(ids)} event ids (showing up to {cfg['scrape']['max_events']}).", cfg)
        else:
            log("API returned 0 event ids. See data/last_api.json to inspect the shape.", cfg)

        sem = asyncio.Semaphore(cfg["scrape"]["event_concurrency"])
        picked = ids[: cfg["scrape"]["max_events"]]

        async def worker(eid: str):
            async with sem:
                key, snap = await scrape_event_by_id(context, eid, cfg)
                events_store[eid] = {
                    "title": snap.title,
                    "match_time": snap.match_time,
                    "runners": {
                        name: {
                            "best_back": odds.best_back,
                            "best_lay": odds.best_lay,
                            "ladder": [asdict(step) for step in odds.ladder],
                        } for name, odds in snap.bookmaker_odds.items()
                    },
                    "bookmaker_zero_commission": {
                        name: {
                            "best_back": odds.best_back,
                            "best_lay": odds.best_lay,
                            "ladder": [asdict(step) for step in odds.ladder],
                        } for name, odds in snap.bookmaker_zero_commission.items()
                    },
                    "bookmaker_zero_commission_suspended": snap.bookmaker_zero_commission_suspended,
                    "fancy": snap.fancy,
                    "sessions": snap.sessions,
                    "result": snap.result,
                    "source_url": snap.source_url,
                }
                if key:
                    live_details[key] = {
                        "event_id": eid,
                        "title": snap.title,
                        "match_time": snap.match_time,
                        "bookmaker": {
                            nm: {"back": od.best_back, "lay": od.best_lay}
                            for nm, od in snap.bookmaker_odds.items()
                        },
                        "fancy": snap.fancy,
                        "sessions": snap.sessions,
                        "result": snap.result,
                    }

        await asyncio.gather(*(worker(e) for e in picked))

    except httpx.HTTPStatusError as e:
        log(f"API error: {e!r}", cfg)
    except Exception as e:
        log(f"API fetch/parsing error: {e!r}", cfg)

    payload = {
        "fetched_at": now_iso(),
        "lobby": [asdict(r) for r in lobby],
        "events": events_store,
        "live_details": live_details,
    }
    return payload

# =============================================================================
# Main loop
# =============================================================================

async def main():
    cfg = load_cfg()
    os.makedirs(os.path.dirname(cfg["io"]["outfile"]), exist_ok=True)

    context = None
    page = None
    try:
        context, page = await open_context(cfg)
        page.on("console", lambda m: print("PAGE:", m.type, m.text))

        interval = max(3, int(cfg["scrape"]["interval_seconds"]))

        while True:
            try:
                payload = await run_once(context, page, cfg)
                atomic_write(cfg["io"]["outfile"], cfg["io"]["tempfile"], payload)
                log(
                    f"Wrote snapshot @ {payload['fetched_at']} | "
                    f"lobby rows: {len(payload['lobby'])} | "
                    f"events scraped: {len(payload['events'])}",
                    cfg
                )
            except Exception as e:
                log(f"Scrape error: {e!r}", cfg)
            await asyncio.sleep(interval)

    finally:
        with contextlib.suppress(Exception):
            if page:
                await page.close()
            if context:
                await context.close()
        with contextlib.suppress(Exception):
            await async_playwright().stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
