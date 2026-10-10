#!/usr/bin/env python3
"""Sports Desk collector.

Same approach as Boyd Wall's collector (../boyd-wall/collect.py): public, no-key ESPN JSON
endpoints, each cached on disk with a fetchedAt stamp and a status of live / stale / unavailable.
Boyd Wall's own cache is used read-only as a fallback seed; nothing is ever written there.
Every number on the page is copied or arithmetically derived from a fetched payload; nothing is
invented. If something can't be found, the field stays null and the page shows a gap.

Stdlib only.  python3 collect.py [--force]   -> writes data/desk.json
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data", "cache")
IMG = os.path.join(HERE, "data", "img")
WALL_CACHE = os.path.join(HERE, "..", "boyd-wall", "data", "cache")  # read-only fallback
CFG = json.load(open(os.path.join(HERE, "config.json")))
ET = ZoneInfo(CFG.get("timezone", "America/New_York"))
UA = "SportsDesk/1.0 (personal sports page; Boyd's TokenMax build)"
ESPN = "https://site.api.espn.com/apis/site/v2/sports"
os.makedirs(CACHE, exist_ok=True)
os.makedirs(IMG, exist_ok=True)


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def iso(t):
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def parse_iso(s):
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    m = re.match(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d)(\+00:00)$", s)
    if m:
        s = m.group(1) + ":00" + m.group(2)
    try:
        t = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def et_label(s, time_valid=True):
    t = parse_iso(s)
    if not t:
        return None
    t = t.astimezone(ET)
    day = t.strftime("%a %b ") + str(t.day)
    if not time_valid:
        return day + " · time TBD"
    return day + " · " + t.strftime("%I:%M %p").lstrip("0") + " ET"


# ----------------------------------------------------------------------------- cache + fetch
def _cpath(name):
    return os.path.join(CACHE, name + ".json")


def cache_read(name):
    try:
        return json.load(open(_cpath(name)))
    except Exception:  # noqa: BLE001
        return None


def cache_write(name, payload):
    tmp = _cpath(name) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    os.replace(tmp, _cpath(name))


def wall_cache(url):
    """Boyd Wall's cached copy of the exact same URL, if it has one (read-only)."""
    try:
        for fn in os.listdir(WALL_CACHE):
            if fn.startswith("espn_") and fn.endswith(".json"):
                c = json.load(open(os.path.join(WALL_CACHE, fn)))
                if c.get("url") == url and c.get("data"):
                    c["from"] = "boyd-wall cache/" + fn
                    return c
    except Exception:  # noqa: BLE001
        pass
    return None


def http_json(url, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} from {url.split('/')[2]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"{url.split('/')[2]} unreachable: {e.reason}")


def cached_fetch(name, url, ttl, force=False):
    """(data, status). Fresh cache -> use it. Stale -> refetch; on failure fall back to the last
    good copy (ours, then Boyd Wall's) and say so."""
    c = cache_read(name)
    if c and c.get("url") != url:
        c = None
    if not c:
        w = wall_cache(url)
        if w:
            c = w
    age = time.time() - c["fetchedAt"] if c else None
    if c and not force and age < ttl:
        return c["data"], {"state": "live", "fetchedAt": iso_ts(c["fetchedAt"]), "url": url, "error": None, "from": c.get("from")}
    try:
        data = http_json(url)
        ts = time.time()
        cache_write(name, {"fetchedAt": ts, "url": url, "data": data})
        return data, {"state": "live", "fetchedAt": iso_ts(ts), "url": url, "error": None, "from": None}
    except Exception as e:  # noqa: BLE001
        if c:
            return c["data"], {"state": "stale", "fetchedAt": iso_ts(c["fetchedAt"]), "url": url, "error": str(e), "from": c.get("from")}
        return None, {"state": "unavailable", "fetchedAt": None, "url": url, "error": str(e), "from": None}


def iso_ts(ts):
    return iso(dt.datetime.fromtimestamp(ts, dt.timezone.utc))


def cache_image(url, max_bytes=400_000):
    if not url:
        return None
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"):
        ext = ".img"
    fn = hashlib.sha1(url.encode()).hexdigest()[:16] + ext
    p = os.path.join(IMG, fn)
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return "/img/" + fn
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            b = r.read(max_bytes + 1)
        if len(b) > max_bytes:
            return None
        open(p, "wb").write(b)
        return "/img/" + fn
    except Exception:  # noqa: BLE001
        return None


def small_logo(href):
    """ESPN serves resized logos through its combiner; 80px is plenty for tables."""
    if not href or "a.espncdn.com/i/teamlogos" not in href:
        return href
    path = href.split("a.espncdn.com", 1)[1]
    return f"https://a.espncdn.com/combiner/i?img={path}&h=80&w=80"


# ----------------------------------------------------------------------------------- events
def _score(c):
    s = c.get("score")
    return s.get("displayValue") if isinstance(s, dict) else s


def parse_event(e, abbr, sport):
    c = e["competitions"][0]
    st = c["status"]["type"]
    comps = c["competitors"]
    me = next((x for x in comps if x["team"].get("abbreviation") == abbr), comps[0])
    opp = next((x for x in comps if x is not me), comps[-1])
    tv = []
    for b in c.get("broadcasts") or []:
        n = (b.get("media") or {}).get("shortName") or ", ".join(b.get("names") or [])
        if n and n not in tv:
            tv.append(n)
    result, ms, os_ = None, _score(me), _score(opp)
    if st.get("completed"):
        try:
            a, b = int(float(ms)), int(float(os_))
            result = "W" if a > b else "L" if a < b else ("D" if sport == "soccer" else "T")
            # soccer cup ties decided on penalties: ESPN marks the winner
            if result == "D" and sport == "soccer" and (me.get("winner") or opp.get("winner")) and "Cup" in ((e.get("league") or {}).get("name") or ""):
                result = "D"
        except (TypeError, ValueError):
            result = "W" if me.get("winner") else "L" if opp.get("winner") else None
    ot = opp["team"]
    venue = c.get("venue") or {}
    return {
        "id": e.get("id"), "date": e.get("date"), "timeValid": c.get("timeValid", True),
        "et": et_label(e.get("date"), c.get("timeValid", True)),
        "home": me.get("homeAway") == "home", "neutral": bool(c.get("neutralSite")),
        "opp": ot.get("displayName"), "oppShort": ot.get("shortDisplayName") or ot.get("displayName"), "oppAbbr": ot.get("abbreviation"),
        "oppLogo": small_logo(((ot.get("logos") or [{}])[0].get("href")) or ot.get("logo")),
        "state": st.get("state"), "status": st.get("shortDetail") or st.get("detail"), "completed": bool(st.get("completed")),
        "score": ms, "oppScore": os_, "result": result, "tv": tv[:3],
        "venue": venue.get("fullName"),
        "competition": (e.get("league") or {}).get("name") or (e.get("seasonType") or {}).get("name"),
        "seasonType": (e.get("seasonType") or {}).get("name"),
        "week": (e.get("week") or {}).get("text"),
        "link": next((l.get("href") for l in e.get("links") or [] if "summary" in (l.get("rel") or []) or "gamecast" in (l.get("rel") or [])), None),
    }


def dedupe_sorted(evs):
    seen, out = set(), []
    for e in sorted(evs, key=lambda e: e["date"] or ""):
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        out.append(e)
    return out


def spark_over500(games, label):
    """Games over .500 after each game, from completed results (W +1, L -1, T/D 0)."""
    pts, run = [], 0
    w = l = t = 0
    for g in games:
        r = g["result"]
        if r == "W":
            run += 1; w += 1
        elif r == "L":
            run -= 1; l += 1
        elif r in ("T", "D"):
            t += 1
        pts.append({"v": run, "r": r, "d": g["date"][:10], "opp": g["oppAbbr"], "s": f"{g['score']}-{g['oppScore']}"})
    return {"label": label, "kind": "over500", "points": pts, "w": w, "l": l, "t": t}


def spark_points(games, label):
    """Cumulative league points (3 W / 1 D / 0 L) after each league match."""
    pts, tot = [], 0
    for g in games:
        tot += {"W": 3, "D": 1}.get(g["result"], 0)
        pts.append({"v": tot, "r": g["result"], "d": g["date"][:10], "opp": g["oppAbbr"], "s": f"{g['score']}-{g['oppScore']}"})
    return {"label": label, "kind": "points", "points": pts}


# -------------------------------------------------------------------------------- standings
def _groups(node, out):
    if "standings" in node:
        out.append({"name": node.get("name"), "entries": node["standings"].get("entries", [])})
    for ch in node.get("children", []) or []:
        _groups(ch, out)


def stat(entry, *names):
    for s in entry.get("stats", []):
        if s.get("name") in names or s.get("abbreviation") in names or s.get("type") in names:
            return s.get("displayValue")
    return None


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


# ------------------------------------------------------------------------------------ news
def pick_headline(articles, t):
    """Pick one story that is actually about this team: team tagged, team word in the headline,
    few other teams tagged, written stories over video clips, newest first."""
    kws = [k.lower() for k in t["keywords"]]
    best, best_score = None, -1e9
    for a in articles:
        href = ((a.get("links") or {}).get("web") or {}).get("href")
        if not href or not a.get("headline"):
            continue
        teams = [c.get("description") for c in a.get("categories", []) if c.get("type") == "team"]
        tagged = any(t["full"].split(" men's")[0] in (d or "") for d in teams)
        h = a["headline"].lower()
        hit = any(k in h for k in kws) or any(k in (a.get("description") or "").lower() for k in kws[:1])
        pub = parse_iso(a.get("published")) or now_utc() - dt.timedelta(days=60)
        age_days = (now_utc() - pub).total_seconds() / 86400
        score = (40 if any(k in h for k in kws) else 0) + (15 if hit else 0) + (10 if tagged else 0)
        score -= max(0, len(set(teams)) - 2) * 1.5
        score += 6 if a.get("type") in ("Story", "HeadlineNews") else -4
        score -= age_days * 1.2
        if "rumor" in h or "rumour" in h:
            score -= 20  # roundup pages: the team is one item among many
        if score > best_score:
            best, best_score = a, score
    if not best:
        return None
    img = next((i.get("url") for i in best.get("images") or [] if i.get("url")), None)
    return {"title": best["headline"], "desc": best.get("description"), "url": best["links"]["web"]["href"],
            "published": best.get("published"), "publishedEt": et_label(best.get("published")),
            "byline": best.get("byline"), "type": best.get("type"), "image": img,
            "source": "ESPN news API (team feed)"}


def http_text(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) " + UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch_rss(name, url, ttl, force=False):
    """RSS -> list of items, cached like the JSON sources."""
    import email.utils
    import xml.etree.ElementTree as XT
    c = cache_read(name)
    if c and c.get("url") == url and not force and time.time() - c["fetchedAt"] < ttl:
        return c["data"], {"state": "live", "fetchedAt": iso_ts(c["fetchedAt"]), "url": url, "error": None, "from": None}
    try:
        root = XT.fromstring(http_text(url).encode("utf-8"))
        items = []
        for it in root.iter("item"):
            g = {ch.tag.split("}")[-1]: (ch.text or "").strip() for ch in it}
            img = None
            for ch in it:
                if ch.tag.split("}")[-1] in ("thumbnail", "content", "enclosure") and ch.get("url"):
                    img = img or ch.get("url")
            m = re.search(r'src="([^"]+)"', g.get("description", ""))
            img = img or (m.group(1) if m else None)
            pub = None
            try:
                raw = g.get("pubDate", "")
                if raw.strip().endswith(" EST"):
                    # Sidearm feeds (umterps.com) stamp local Eastern time as "EST" year-round
                    t0 = email.utils.parsedate_to_datetime(raw.strip()[:-4] + " +0000").replace(tzinfo=ET)
                    pub = iso(t0)
                else:
                    pub = iso(email.utils.parsedate_to_datetime(raw))
            except Exception:  # noqa: BLE001
                pass
            desc = re.sub(r"<[^>]+>", " ", g.get("description", ""))
            desc = re.sub(r"\s+", " ", desc).strip()
            items.append({"title": g.get("title"), "url": g.get("link"), "published": pub, "desc": desc[:280] or None, "image": img})
        items = [i for i in items if i["title"] and i["url"] and i["url"].count("/") > 3]
        ts = time.time()
        cache_write(name, {"fetchedAt": ts, "url": url, "data": items})
        return items, {"state": "live", "fetchedAt": iso_ts(ts), "url": url, "error": None, "from": None}
    except Exception as e:  # noqa: BLE001
        if c and c.get("url") == url:
            return c["data"], {"state": "stale", "fetchedAt": iso_ts(c["fetchedAt"]), "url": url, "error": str(e), "from": None}
        return None, {"state": "unavailable", "fetchedAt": None, "url": url, "error": str(e), "from": None}


# ----------------------------------------------------------------------------------- teams
def collect_ravens(t, force, src):
    ttl = CFG["ttl"]
    sch, s1 = cached_fetch("ravens_schedule", f"{ESPN}/football/nfl/teams/bal/schedule", ttl["schedule"], force); src.append(("Ravens schedule", s1))
    tm, s2 = cached_fetch("ravens_team", f"{ESPN}/football/nfl/teams/bal", ttl["team"], force); src.append(("Ravens team", s2))
    stg, s3 = cached_fetch("nfl_standings", t["standingsUrl"], ttl["standings"], force); src.append(("NFL standings", s3))
    info = (tm or {}).get("team", {})
    evs = dedupe_sorted([parse_event(e, "BAL", "football") for e in (sch or {}).get("events", [])])
    done = [e for e in evs if e["completed"]]
    nxt = [e for e in evs if e["state"] in ("pre", "in")]
    recs = {i.get("type"): i.get("summary") for i in (info.get("record") or {}).get("items", [])}
    groups = []
    _groups(stg or {}, groups)
    div = next((g for g in groups if g["name"] == t["group"]), None)
    rows = []
    for e in (div or {}).get("entries", []):
        rows.append({"abbr": e["team"].get("abbreviation"), "team": e["team"].get("shortDisplayName") or e["team"].get("displayName"),
                     "logo": small_logo(((e["team"].get("logos") or [{}])[0]).get("href")),
                     "w": stat(e, "wins"), "l": stat(e, "losses"), "t": stat(e, "ties"), "pct": stat(e, "winPercent"),
                     "rec": stat(e, "overall"), "div": stat(e, "divisionRecord"), "pf": stat(e, "pointsFor"), "pa": stat(e, "pointsAgainst"),
                     "diff": stat(e, "pointDifferential", "differential"), "strk": stat(e, "streak"), "seed": stat(e, "playoffSeed"),
                     "me": e["team"].get("abbreviation") == "BAL"})
    rows.sort(key=lambda r: int(r["seed"] or 99))
    pos_note = None
    me = next((i for i, r in enumerate(rows) if r["me"]), None)
    if me is not None:
        tied_ahead = [r for r in rows[:me] if r["pct"] == rows[me]["pct"]]
        pos = me + 1 - len(tied_ahead)
        tied = any(r["pct"] == rows[me]["pct"] for j, r in enumerate(rows) if j != me)
        pos_note = f"{'T-' if tied else ''}{ordinal(pos)} in AFC North" + (f" ({rows[0]['abbr']} ahead on ESPN's tiebreak order)" if tied_ahead else "")
    return {
        "record": recs.get("total"), "recordLabel": "2026 regular season",
        "splits": {"Home": recs.get("home"), "Road": recs.get("road")},
        "standing": pos_note or info.get("standingSummary"), "espnStanding": info.get("standingSummary"),
        "last": list(reversed(done[-5:])), "next": nxt[:3],
        "spark": spark_over500(done, "2026 · games over .500 after each game"),
        "table": {"title": "AFC North", "cols": ["W-L", "PCT", "DIV", "PF", "PA", "DIFF", "STRK"], "rows": rows,
                  "note": "Order as ESPN's standings feed lists it (playoff seed)."},
        "logo": small_logo(((info.get("logos") or [{}])[0]).get("href")),
        "facts": [("Points for", next((r["pf"] for r in rows if r["me"]), None)), ("Points against", next((r["pa"] for r in rows if r["me"]), None)),
                  ("Streak", next((r["strk"] for r in rows if r["me"]), None)), ("AFC seed (ESPN)", next((r["seed"] for r in rows if r["me"]), None))],
    }


def collect_chelsea(t, force, src):
    ttl = CFG["ttl"]
    res, s1 = cached_fetch("chelsea_results_all", f"{ESPN}/soccer/all/teams/363/schedule", ttl["schedule"], force); src.append(("Chelsea results (all comps)", s1))
    fix, s2 = cached_fetch("chelsea_fixtures_all", f"{ESPN}/soccer/all/teams/363/schedule?fixture=true", ttl["schedule"], force); src.append(("Chelsea fixtures (all comps)", s2))
    stg, s3 = cached_fetch("epl_standings", t["standingsUrl"], ttl["standings"], force); src.append(("Premier League table", s3))
    tm, s4 = cached_fetch("chelsea_team", f"{ESPN}/soccer/eng.1/teams/363", ttl["team"], force); src.append(("Chelsea team", s4))
    info = (tm or {}).get("team", {})
    evs = dedupe_sorted([parse_event(e, "CHE", "soccer") for e in (res or {}).get("events", []) + (fix or {}).get("events", [])])
    competitive = [e for e in evs if "Friendly" not in (e["competition"] or "")]
    done = [e for e in competitive if e["completed"]]
    nxt = [e for e in competitive if e["state"] in ("pre", "in")]
    league = [e for e in done if "Premier League" in (e["competition"] or "")]
    groups = []
    _groups(stg or {}, groups)
    rows = []
    for e in (groups[0]["entries"] if groups else []):
        rows.append({"rank": int(stat(e, "rank") or 0), "abbr": e["team"].get("abbreviation"),
                     "team": e["team"].get("shortDisplayName") or e["team"].get("displayName"),
                     "logo": small_logo(((e["team"].get("logos") or [{}])[0]).get("href")),
                     "p": stat(e, "gamesPlayed"), "w": stat(e, "wins"), "d": stat(e, "ties"), "l": stat(e, "losses"),
                     "gf": stat(e, "pointsFor"), "ga": stat(e, "pointsAgainst"), "gd": stat(e, "pointDifferential"), "pts": stat(e, "points"),
                     "note": (e.get("note") or {}).get("description"), "noteColor": (e.get("note") or {}).get("color"),
                     "me": e["team"].get("abbreviation") == "CHE"})
    rows.sort(key=lambda r: r["rank"])
    mine = next((r for r in rows if r["me"]), None)
    rec = f"{mine['w']}W {mine['d']}D {mine['l']}L" if mine else None
    return {
        "record": rec, "recordLabel": "Premier League 2026-27",
        "points": mine and mine["pts"], "rank": mine and mine["rank"],
        "standing": (f"{ordinal(mine['rank'])} in the Premier League · {mine['pts']} pts" if mine else info.get("standingSummary")),
        "espnStanding": info.get("standingSummary"),
        "last": list(reversed(done[-5:])), "next": nxt[:3],
        "spark": spark_points(league, "2026-27 · Premier League points after each match"),
        "table": {"title": "Premier League", "cols": ["P", "W", "D", "L", "GF", "GA", "GD", "PTS"], "rows": rows,
                  "note": "Full table from ESPN's standings feed. Last 5 and fixtures are all competitions (friendlies excluded)."},
        "logo": small_logo(((info.get("logos") or [{}])[0]).get("href")),
        "facts": [("Goals for", mine and mine["gf"]), ("Goals against", mine and mine["ga"]), ("Goal difference", mine and mine["gd"]), ("Played", mine and mine["p"])],
    }


def collect_orioles(t, force, src):
    ttl = CFG["ttl"]
    reg, s1 = cached_fetch("orioles_schedule_regular", f"{ESPN}/baseball/mlb/teams/bal/schedule?seasontype=2", ttl["history"], force); src.append(("Orioles 2026 regular-season schedule", s1))
    cur, s0 = cached_fetch("orioles_schedule_current", f"{ESPN}/baseball/mlb/teams/bal/schedule", ttl["schedule"], force); src.append(("Orioles current schedule", s0))
    tm, s2 = cached_fetch("orioles_team", f"{ESPN}/baseball/mlb/teams/bal", ttl["team"], force); src.append(("Orioles team", s2))
    stg, s3 = cached_fetch("mlb_standings", t["standingsUrl"], ttl["history"], force); src.append(("MLB standings", s3))
    info = (tm or {}).get("team", {})
    evs = dedupe_sorted([parse_event(e, "BAL", "baseball") for e in (reg or {}).get("events", [])])
    done = [e for e in evs if e["completed"] and e["result"] in ("W", "L")]
    upcoming = dedupe_sorted([parse_event(e, "BAL", "baseball") for e in (cur or {}).get("events", [])])
    nxt = [e for e in upcoming if e["state"] in ("pre", "in")]
    recs = {i.get("type"): i.get("summary") for i in (info.get("record") or {}).get("items", [])}
    groups = []
    _groups(stg or {}, groups)
    div = next((g for g in groups if g["name"] == t["group"]), None)
    rows = []
    for e in (div or {}).get("entries", []):
        rows.append({"abbr": e["team"].get("abbreviation"), "team": e["team"].get("shortDisplayName") or e["team"].get("displayName"),
                     "logo": small_logo(((e["team"].get("logos") or [{}])[0]).get("href")),
                     "w": stat(e, "wins"), "l": stat(e, "losses"), "pct": stat(e, "winPercent"), "gb": stat(e, "gamesBehind"),
                     "rs": stat(e, "pointsFor"), "ra": stat(e, "pointsAgainst"), "diff": stat(e, "pointDifferential"),
                     "home": stat(e, "Home"), "road": stat(e, "Road"), "l10": stat(e, "Last Ten Games"), "clinch": stat(e, "clincher"),
                     "me": e["team"].get("abbreviation") == "BAL"})
    rows.sort(key=lambda r: -float(r["pct"] or 0))
    mine = next((r for r in rows if r["me"]), {})
    season_over = not nxt and info.get("standingSummary") is not None and (cur or {}).get("season", {}).get("type") == 3
    # Derived season summary (arithmetic on the fetched game list only)
    summary = None
    if done:
        w = sum(1 for g in done if g["result"] == "W")
        l = len(done) - w
        rs = sum(int(g["score"]) for g in done)
        ra = sum(int(g["oppScore"]) for g in done)
        best = cur_run = 0
        bestL = curL = 0
        for g in done:
            if g["result"] == "W":
                cur_run += 1; curL = 0
            else:
                curL += 1; cur_run = 0
            best, bestL = max(best, cur_run), max(bestL, curL)
        months = {}
        for g in done:
            m = (parse_iso(g["date"]).astimezone(ET)).strftime("%b")
            months.setdefault(m, [0, 0])[0 if g["result"] == "W" else 1] += 1
        one_run = [g for g in done if abs(int(g["score"]) - int(g["oppScore"])) == 1]
        vs_div = [g for g in done if g["oppAbbr"] in {r["abbr"] for r in rows if not r["me"]}]
        peak = max(spark_over500(done, "")["points"], key=lambda p: p["v"])
        low = min(spark_over500(done, "")["points"], key=lambda p: p["v"])
        summary = {"w": w, "l": l, "rs": rs, "ra": ra, "diff": rs - ra, "longestWin": best, "longestLoss": bestL,
                   "months": [{"m": k, "w": v[0], "l": v[1]} for k, v in months.items()],
                   "oneRun": f"{sum(1 for g in one_run if g['result']=='W')}-{sum(1 for g in one_run if g['result']=='L')}",
                   "vsDiv": f"{sum(1 for g in vs_div if g['result']=='W')}-{sum(1 for g in vs_div if g['result']=='L')}",
                   "peak": peak, "low": low, "first": done[0]["date"][:10], "lastGame": done[-1]["date"][:10],
                   "games": len(done)}
    return {
        "record": recs.get("total") or (f"{mine.get('w')}-{mine.get('l')}" if mine else None), "recordLabel": "2026 final regular season",
        "splits": {"Home": recs.get("home"), "Road": recs.get("road")},
        "standing": info.get("standingSummary") and info["standingSummary"] + (f" · {mine.get('gb')} GB" if mine.get("gb") else ""),
        "espnStanding": info.get("standingSummary"), "seasonOver": season_over,
        "last": list(reversed(done[-5:])), "next": nxt[:3],
        "spark": spark_over500(done, "2026 · games over .500 after each game"),
        "seasonSummary": summary,
        "table": {"title": "AL East · final", "cols": ["W", "L", "PCT", "GB", "RS", "RA", "DIFF", "L10"], "rows": rows,
                  "note": "Final 2026 regular-season standings from ESPN."},
        "logo": small_logo(((info.get("logos") or [{}])[0]).get("href")),
        "facts": [("Run differential", mine.get("diff")), ("Runs scored", mine.get("rs")), ("Runs allowed", mine.get("ra")), ("Last 10", mine.get("l10"))],
    }


def collect_terps(t, force, src):
    ttl = CFG["ttl"]
    up, s1 = cached_fetch("terps_schedule_2027", f"{ESPN}/basketball/mens-college-basketball/teams/120/schedule?season={t['upcomingSeason']}&seasontype=2", ttl["schedule"], force); src.append(("Terps 2026-27 schedule", s1))
    last, s2 = cached_fetch("terps_schedule_2026", f"{ESPN}/basketball/mens-college-basketball/teams/120/schedule?season={t['lastSeason']}", ttl["history"], force); src.append(("Terps 2025-26 results", s2))
    tm, s3 = cached_fetch("terps_team", f"{ESPN}/basketball/mens-college-basketball/teams/120", ttl["team"], force); src.append(("Terps team", s3))
    info = (tm or {}).get("team", {})
    nxt_all = dedupe_sorted([parse_event(e, "MD", "basketball") for e in (up or {}).get("events", [])])
    nxt = [e for e in nxt_all if e["state"] in ("pre", "in")]
    prev = dedupe_sorted([parse_event(e, "MD", "basketball") for e in (last or {}).get("events", [])])
    done = [e for e in prev if e["completed"] and e["result"] in ("W", "L")]
    w = sum(1 for g in done if g["result"] == "W")
    first = nxt[0] if nxt else None
    days_to = None
    if first and parse_iso(first["date"]):
        days_to = (parse_iso(first["date"]).astimezone(ET).date() - now_utc().astimezone(ET).date()).days
    big_ten = {"ILL", "IND", "IU", "IOWA", "MSU", "MICH", "MINN", "NEB", "NU", "OSU", "PSU", "PUR", "RUTG", "UCLA", "USC", "WASH", "WIS", "ORE"}
    home = sum(1 for e in nxt_all if e["home"] and not e["neutral"])
    tv = {}
    for e in nxt_all:
        for n in e["tv"]:
            tv[n] = tv.get(n, 0) + 1
    pre = {"opener": first, "daysToOpener": days_to, "games": len(nxt_all), "home": home,
           "away": sum(1 for e in nxt_all if not e["home"] and not e["neutral"]), "neutral": sum(1 for e in nxt_all if e["neutral"]),
           "bigTen": sum(1 for e in nxt_all if e["oppAbbr"] in big_ten),
           "tv": sorted(tv.items(), key=lambda kv: -kv[1])[:6],
           "lastSeasonRecord": f"{w}-{len(done) - w}" if done else None, "lastSeasonGames": len(done),
           "lastSeasonFinal": done[-1] if done else None,
           "fullSchedule": [{"et": e["et"], "opp": e["oppShort"], "abbr": e["oppAbbr"], "home": e["home"], "neutral": e["neutral"], "tv": e["tv"], "date": e["date"]} for e in nxt_all]}
    return {
        "record": "0-0", "recordLabel": "2026-27 · season not started", "preseason": pre,
        "standing": f"Opener {first['et'].split(' · ')[0]} vs {first['oppShort']}" if first else None,
        "espnStanding": info.get("standingSummary"),
        "last": list(reversed(done[-5:])), "lastLabel": "Last 5 (end of 2025-26)", "next": nxt[:3],
        "spark": spark_over500(done, "2025-26 · games over .500 after each game"),
        "logo": small_logo(((info.get("logos") or [{}])[0]).get("href")),
        "facts": [("Last season (ESPN results)", pre["lastSeasonRecord"]), ("2026-27 games listed", pre["games"]), ("Big Ten games", pre["bigTen"]), ("Days to tip-off", days_to)],
    }



def weekend_bounds(now_et):
    """Saturday 00:00 through Sunday 23:59:59 of the current ET weekend.
    If today is Mon–Fri, use the upcoming Sat–Sun; if Sat/Sun, use this one."""
    d = now_et.date()
    # weekday: Mon=0 … Sun=6
    if d.weekday() == 5:  # Saturday
        sat = d
    elif d.weekday() == 6:  # Sunday
        sat = d - dt.timedelta(days=1)
    else:
        # days until next Saturday
        sat = d + dt.timedelta(days=(5 - d.weekday()) % 7)
    sun = sat + dt.timedelta(days=1)
    start = dt.datetime.combine(sat, dt.time(0, 0), tzinfo=ET)
    end = dt.datetime.combine(sun, dt.time(23, 59, 59), tzinfo=ET)
    return start, end, sat, sun


def build_sunday_mode(teams, generated_at_iso):
    """Bill-Simmons-style weekend watch cards from fetched fixtures only.
    No invented lines, injuries, or picks — lean is playful UI chrome only."""
    now = parse_iso(generated_at_iso) or now_utc()
    now_et = now.astimezone(ET)
    start, end, sat, sun = weekend_bounds(now_et)
    cards = []
    by_key = {t["key"]: t for t in teams}
    # Priority order for the panel
    for key, tagline in (
        ("ravens", "Sunday Night Football · watch card"),
        ("chelsea", "Premier League · watch card"),
        ("orioles", "MLB · offseason desk"),
        ("terps", "College hoops · tip-off watch"),
    ):
        t = by_key.get(key)
        if not t:
            continue
        # Find next game whose ET local date falls Sat or Sun of this weekend
        weekend_ev = None
        for e in t.get("next") or []:
            tt = parse_iso(e.get("date"))
            if not tt:
                continue
            etd = tt.astimezone(ET)
            if start <= etd <= end:
                weekend_ev = e
                break
        # Also surface the immediate next if it falls just outside but is the featured game
        featured = weekend_ev or ((t.get("next") or [None])[0] if key in ("ravens", "chelsea") else None)
        in_window = weekend_ev is not None
        if key == "orioles" and not (t.get("next") or []):
            cards.append({
                "key": key,
                "team": t["name"],
                "full": t["full"],
                "colors": t["colors"],
                "logoLocal": t.get("logoLocal") or t.get("logo"),
                "inWindow": False,
                "tagline": tagline,
                "record": t.get("record"),
                "standing": t.get("standing"),
                "note": "2026 regular season complete — no weekend fixture in the schedule feed.",
                "facts": [{"label": k, "value": v} for k, v in (t.get("facts") or []) if v is not None][:4],
                "lean": None,
            })
            continue
        if key == "terps" and not in_window:
            opener = (t.get("next") or [None])[0]
            cards.append({
                "key": key,
                "team": t["name"],
                "full": t["full"],
                "colors": t["colors"],
                "logoLocal": t.get("logoLocal") or t.get("logo"),
                "inWindow": False,
                "tagline": tagline,
                "record": t.get("record"),
                "standing": t.get("standing"),
                "note": "No weekend tip — opener listed below when the schedule feed has it.",
                "event": opener and {
                    "opp": opener.get("oppShort") or opener.get("opp"),
                    "oppAbbr": opener.get("oppAbbr"),
                    "oppLogoLocal": opener.get("oppLogoLocal") or opener.get("oppLogo"),
                    "home": opener.get("home"),
                    "neutral": opener.get("neutral"),
                    "et": opener.get("et"),
                    "tv": opener.get("tv") or [],
                    "venue": opener.get("venue"),
                    "week": opener.get("week"),
                    "competition": opener.get("competition"),
                },
                "facts": [{"label": k, "value": v} for k, v in (t.get("facts") or []) if v is not None][:4],
                "lean": None,
            })
            continue
        if not featured and not in_window:
            continue
        e = featured
        where = "vs" if e.get("home") or e.get("neutral") else "at"
        # Playful lean chrome only — no fake lines/injuries. Frame as UI, not a pick.
        lean = None
        if in_window and key in ("ravens", "chelsea"):
            lean = {
                "label": "Desk chrome (not a pick)",
                "text": f"Watch card · {t['name']} {where} {e.get('oppShort') or e.get('opp')}",
                "disclaimer": "No lines, spreads, or injury claims invented here — only kickoff, TV, and records from the source feeds.",
            }
        cards.append({
            "key": key,
            "team": t["name"],
            "full": t["full"],
            "colors": t["colors"],
            "logoLocal": t.get("logoLocal") or t.get("logo"),
            "inWindow": in_window,
            "tagline": tagline if in_window else (tagline + " · upcoming"),
            "record": t.get("record"),
            "standing": t.get("standing"),
            "event": {
                "opp": e.get("oppShort") or e.get("opp"),
                "oppAbbr": e.get("oppAbbr"),
                "oppLogoLocal": e.get("oppLogoLocal") or e.get("oppLogo"),
                "home": e.get("home"),
                "neutral": e.get("neutral"),
                "et": e.get("et"),
                "tv": e.get("tv") or [],
                "venue": e.get("venue"),
                "week": e.get("week"),
                "competition": e.get("competition"),
                "where": where,
            },
            "facts": [{"label": k, "value": v} for k, v in (t.get("facts") or []) if v is not None][:4],
            "lean": lean,
            "note": None if in_window else "Fixture is outside this weekend window; shown as the next listed game.",
        })
    return {
        "title": "Sunday Mode",
        "subtitle": "Bill Simmons–style weekend watch cards · facts from the feeds only",
        "weekend": {
            "sat": sat.isoformat(),
            "sun": sun.isoformat(),
            "label": f"{sat.strftime('%a %b')} {sat.day} – {sun.strftime('%a %b')} {sun.day}, {sun.year}",
        },
        "disclaimer": "Watch cards only. Opponent, kickoff (ET), TV, and records are copied from ESPN/RSS payloads. Any “lean” chrome is playful UI — not a pick, line, or injury report.",
        "cards": cards,
    }


def collect(force=False):
    out = {"generatedAt": iso(now_utc()), "generatedAtEt": now_utc().astimezone(ET).strftime("%a %b %-d, %Y · %-I:%M %p ET"), "teams": []}
    fns = {"ravens": collect_ravens, "chelsea": collect_chelsea, "orioles": collect_orioles, "terps": collect_terps}
    for t in CFG["teams"]:
        src = []
        team = {k: t.get(k) for k in ("key", "name", "full", "abbr", "colors", "sport", "league", "leagueLabel")}
        try:
            team.update(fns[t["key"]](t, force, src))
        except Exception as e:  # noqa: BLE001
            team["error"] = f"{type(e).__name__}: {e}"
        news, sn = cached_fetch(f"{t['key']}_news", t["newsUrl"], CFG["ttl"]["news"], force)
        src.append((f"{t['name']} news", sn))
        team["headline"] = pick_headline((news or {}).get("articles", []), t)
        team["more"] = []
        if t.get("rss"):
            items, sr = fetch_rss(f"{t['key']}_rss", t["rss"]["url"], CFG["ttl"]["news"], force)
            src.append((t["rss"]["label"], sr))
            items = sorted(items or [], key=lambda i: i["published"] or "", reverse=True)
            if items:
                top = items[0]
                espn = team["headline"]
                team["headline"] = {"title": top["title"], "desc": top["desc"], "url": top["url"], "published": top["published"],
                                    "publishedEt": et_label(top["published"]), "image": top["image"], "source": t["rss"]["label"], "type": "Story"}
                if espn:
                    team["more"].append({"title": espn["title"], "url": espn["url"], "publishedEt": espn["publishedEt"], "source": "ESPN"})
                for i in items[1:4]:
                    team["more"].append({"title": i["title"], "url": i["url"], "publishedEt": et_label(i["published"]), "source": t["rss"]["label"].split(" ")[0]})
        else:
            arts = [a for a in (news or {}).get("articles", []) if ((a.get("links") or {}).get("web") or {}).get("href") and a.get("type") != "Media"
                    and (team["headline"] or {}).get("url") != a["links"]["web"]["href"] and any(k.lower() in a["headline"].lower() for k in t["keywords"])]
            for a in arts[:3]:
                team["more"].append({"title": a["headline"], "url": a["links"]["web"]["href"], "publishedEt": et_label(a.get("published")), "source": "ESPN"})
        team["sources"] = [dict(s, name=n) for n, s in src]
        team["logoLocal"] = cache_image(team.get("logo"))
        for e in (team.get("last") or []) + (team.get("next") or []):
            e["oppLogoLocal"] = cache_image(e.get("oppLogo"))
        for r in (team.get("table") or {}).get("rows", []):
            r["logoLocal"] = cache_image(r.get("logo"))
        if team.get("headline") and team["headline"].get("image"):
            team["headline"]["imageLocal"] = cache_image(team["headline"]["image"] + "&w=640" if "?" in team["headline"]["image"] else team["headline"]["image"], 600_000)
        out["teams"].append(team)
    out["sundayMode"] = build_sunday_mode(out["teams"], out["generatedAt"])
    tmp = os.path.join(HERE, "data", "desk.json.tmp")
    json.dump(out, open(tmp, "w"), indent=1)
    os.replace(tmp, os.path.join(HERE, "data", "desk.json"))
    return out


if __name__ == "__main__":
    d = collect(force="--force" in sys.argv)
    for t in d["teams"]:
        print(f"{t['name']:8} {t.get('record')!s:12} {t.get('standing')!s:55} last={[(e['result'], e['score'], e['oppScore'], e['oppAbbr']) for e in t.get('last') or []]}")
        print(f"         next={[(e['et'], e['oppAbbr'], e['tv']) for e in t.get('next') or []]}")
        print(f"         headline={(t.get('headline') or {}).get('title')}  sources={[ (s['name'], s['state']) for s in t['sources']]}")
        if t.get("error"):
            print("   ERROR", t["error"])
