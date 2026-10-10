#!/usr/bin/env python3
"""Sports Desk smoke test.

Renders dist/sports-desk-snapshot.html in headless Chrome, reads every number the page shows
(elements tagged data-check), and re-derives each one independently from the *raw* cached
source payloads in data/cache (not from desk.json). Also checks the live server on :4244,
that headline links come from the fetched feeds, that the snapshot has no remote images, and
that every source shows a fetched-at time.   python3 tests/smoke_test.py
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(HERE, "data", "cache")
ET = ZoneInfo("America/New_York")
FAILS, PASSES = [], []


def ok(cond, msg):
    (PASSES if cond else FAILS).append(msg)
    print(("PASS " if cond else "FAIL ") + msg)


def raw(name):
    return json.load(open(os.path.join(CACHE, name + ".json")))["data"]


class Grab(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.vals, self.imgs = [], {}, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "img":
            self.imgs.append(a.get("src") or "")
        self.stack.append([a.get("data-check"), ""])
        if tag in ("img", "br", "circle", "line", "path", "rect", "i", "input", "meta", "link"):
            self.stack.pop()

    def handle_startendtag(self, tag, attrs):
        if tag == "img":
            self.imgs.append(dict(attrs).get("src") or "")

    def handle_endtag(self, tag):
        if not self.stack:
            return
        key, text = self.stack.pop()
        if key:
            self.vals[key] = " ".join(text.split())
        if self.stack:
            self.stack[-1][1] += text

    def handle_data(self, d):
        if self.stack:
            self.stack[-1][1] += d


def render_dom():
    snap = os.path.join(HERE, "dist", "sports-desk-snapshot.html")
    with tempfile.TemporaryDirectory() as d:
        out = subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", f"--user-data-dir={d}",
                              "--virtual-time-budget=6000", "--dump-dom", "file://" + snap], capture_output=True, text=True, timeout=120)
    return out.stdout


def et_label(s):
    t = dt.datetime.fromisoformat(s.replace("Z", "+00:00") if len(s) > 17 else s.replace("Z", ":00+00:00")).astimezone(ET)
    return t.strftime("%a %b ") + str(t.day) + " · " + t.strftime("%I:%M %p").lstrip("0") + " ET"


def events(payload, abbr):
    out = []
    for e in payload.get("events", []):
        c = e["competitions"][0]
        me = next(x for x in c["competitors"] if x["team"]["abbreviation"] == abbr)
        op = next(x for x in c["competitors"] if x is not me)
        sc = lambda x: (x.get("score") or {}).get("displayValue") if isinstance(x.get("score"), dict) else x.get("score")
        out.append({"id": e["id"], "date": e["date"], "done": c["status"]["type"].get("completed"), "state": c["status"]["type"]["state"],
                    "me": sc(me), "op": sc(op), "opp": op["team"]["abbreviation"], "league": (e.get("league") or {}).get("name") or ""})
    seen, res = set(), []
    for e in sorted(out, key=lambda e: e["date"]):
        if e["id"] not in seen:
            seen.add(e["id"]); res.append(e)
    return res


def result(e):
    a, b = int(e["me"]), int(e["op"])
    return "W" if a > b else "L" if a < b else "D"


def standings_entries(payload, group=None):
    out = []

    def walk(n):
        if "standings" in n:
            out.append((n.get("name"), n["standings"]["entries"]))
        for ch in n.get("children", []) or []:
            walk(ch)
    walk(payload)
    if group:
        return next(e for g, e in out if g == group)
    return out[0][1]


def st(entry, name):
    return next((s["displayValue"] for s in entry["stats"] if s.get("name") == name), None)


def main():
    dom = render_dom()
    ok(len(dom) > 50000 and 'data-ready="1"' in dom, "snapshot renders in headless Chrome (offline, data-ready)")
    g = Grab()
    g.feed(dom)
    V = g.vals
    print(f"     {len(V)} data-check values on the page")

    # ---------------- Ravens
    tm = raw("ravens_team")["team"]
    rec = next(i["summary"] for i in tm["record"]["items"] if i["type"] == "total")
    ok(V.get("ravens.record") == rec, f"Ravens record {V.get('ravens.record')} == ESPN team record {rec}")
    afcn = standings_entries(raw("nfl_standings"), "AFC North")
    bal = next(e for e in afcn if e["team"]["abbreviation"] == "BAL")
    ok(V.get("ravens.table.rec") == st(bal, "overall"), f"AFC North table BAL {V.get('ravens.table.rec')} == standings feed {st(bal, 'overall')}")
    ok("AFC North" in (V.get("ravens.standing") or ""), f"Ravens standing line present: {V.get('ravens.standing')}")
    ev = events(raw("ravens_schedule"), "BAL")
    done = [e for e in ev if e["done"]]
    w = sum(result(e) == "W" for e in done); l = sum(result(e) == "L" for e in done)
    ok(f"{w}-{l}" == rec, f"Ravens W-L recomputed from schedule {w}-{l} == {rec}")
    for i, e in enumerate(list(reversed(done[-5:]))):
        ok(V.get(f"ravens.last.{i}.result") == result(e) and V.get(f"ravens.last.{i}.score") == f"{e['me']}–{e['op']}",
           f"Ravens last[{i}] {V.get(f'ravens.last.{i}.result')} {V.get(f'ravens.last.{i}.score')} vs {e['opp']} == schedule")
    nxt = [e for e in ev if e["state"] in ("pre", "in")][:3]
    for i, e in enumerate(nxt):
        ok(V.get(f"ravens.next.{i}.et") == et_label(e["date"]), f"Ravens next[{i}] {V.get(f'ravens.next.{i}.et')} == {et_label(e['date'])} ({e['opp']})")
    ok(V.get("ravens.sparkEnd") == f"{'+' if w - l > 0 else ''}{w - l}", f"Ravens sparkline ends at {V.get('ravens.sparkEnd')} (W-L = {w - l})")

    # ---------------- Chelsea
    epl = standings_entries(raw("epl_standings"))
    che = next(e for e in epl if e["team"]["abbreviation"] == "CHE")
    exp = f"{st(che, 'wins')}W {st(che, 'ties')}D {st(che, 'losses')}L"
    ok(V.get("chelsea.record") == exp, f"Chelsea record {V.get('chelsea.record')} == table {exp}")
    ok(V.get("chelsea.table.pts") == st(che, "points"), f"Chelsea table points {V.get('chelsea.table.pts')} == {st(che, 'points')}")
    ok(f"{int(st(che, 'rank'))}" in (V.get("chelsea.standing") or "") and f"{st(che, 'points')} pts" in (V.get("chelsea.standing") or ""),
       f"Chelsea standing '{V.get('chelsea.standing')}' carries rank {st(che, 'rank')} and {st(che, 'points')} pts")
    import re
    hl = len(re.findall(r'data-check-row="chelsea.table"\s*>', dom))
    ok(len(epl) == 20 and hl == 1, f"Premier League table has {len(epl)} clubs, Chelsea highlighted {hl}x")
    cev = events({"events": raw("chelsea_results_all")["events"] + raw("chelsea_fixtures_all")["events"]}, "CHE")
    cdone = [e for e in cev if e["done"] and "Friendly" not in e["league"]]
    for i, e in enumerate(list(reversed(cdone[-5:]))):
        ok(V.get(f"chelsea.last.{i}.result") == result(e) and V.get(f"chelsea.last.{i}.score") == f"{e['me']}–{e['op']}",
           f"Chelsea last[{i}] {V.get(f'chelsea.last.{i}.result')} {V.get(f'chelsea.last.{i}.score')} vs {e['opp']} == ESPN")
    pl = [e for e in cdone if "Premier League" in e["league"]]
    pts = sum({"W": 3, "D": 1}.get(result(e), 0) for e in pl)
    ok(str(pts) == st(che, "points") and V.get("chelsea.sparkEnd") == f"{pts} pts", f"Chelsea points from results {pts} == table {st(che, 'points')} == sparkline end {V.get('chelsea.sparkEnd')}")
    cnext = [e for e in cev if e["state"] in ("pre", "in") and "Friendly" not in e["league"]][:3]
    for i, e in enumerate(cnext):
        ok(V.get(f"chelsea.next.{i}.et") == et_label(e["date"]), f"Chelsea next[{i}] {V.get(f'chelsea.next.{i}.et')} == {et_label(e['date'])} ({e['opp']})")

    # ---------------- Orioles
    ot = raw("orioles_team")["team"]
    orec = next(i["summary"] for i in ot["record"]["items"] if i["type"] == "total")
    ok(V.get("orioles.record") == orec, f"Orioles record {V.get('orioles.record')} == ESPN {orec}")
    oev = [e for e in events(raw("orioles_schedule_regular"), "BAL") if e["done"]]
    ow = sum(result(e) == "W" for e in oev); ol = sum(result(e) == "L" for e in oev)
    ok(f"{ow}-{ol}" == orec == V.get("orioles.summary.wl"), f"Orioles game log {ow}-{ol} == record {orec} == season box {V.get('orioles.summary.wl')}")
    rs = sum(int(e["me"]) for e in oev); ra = sum(int(e["op"]) for e in oev)
    ale = standings_entries(raw("mlb_standings"), "American League East")
    ob = next(e for e in ale if e["team"]["abbreviation"] == "BAL")
    ok(str(rs) == st(ob, "pointsFor") and str(ra) == st(ob, "pointsAgainst"), f"Orioles runs from game log {rs}/{ra} == standings RS/RA {st(ob, 'pointsFor')}/{st(ob, 'pointsAgainst')}")
    ok(V.get("orioles.summary.diff") == f"{rs - ra:+d}".replace("+0", "0"), f"Orioles run diff shown {V.get('orioles.summary.diff')} == {rs - ra:+d}")
    ok(V.get("orioles.table.w") == st(ob, "wins"), f"AL East table BAL wins {V.get('orioles.table.w')} == {st(ob, 'wins')}")
    ok(ot.get("standingSummary", "") in (V.get("orioles.standing") or ""), f"Orioles standing '{V.get('orioles.standing')}' matches ESPN '{ot.get('standingSummary')}'")
    ok(not events(raw("orioles_schedule_current"), "BAL") and "season is over" in dom, "Orioles: no games scheduled in the current feed and the page says the season is over")

    # ---------------- Terps
    tev = events(raw("terps_schedule_2027"), "MD")
    ok(V.get("terps.games") == str(len(tev)), f"Terps 2026-27 games {V.get('terps.games')} == schedule {len(tev)}")
    ok(V.get("terps.next.0.et") == et_label(tev[0]["date"]), f"Terps opener {V.get('terps.next.0.et')} == {et_label(tev[0]['date'])} ({tev[0]['opp']})")
    days = (dt.datetime.fromisoformat(tev[0]["date"].replace("Z", ":00+00:00")).astimezone(ET).date() - dt.datetime.fromisoformat(json.load(open(os.path.join(HERE, "data", "desk.json")))["generatedAt"].replace("Z", "+00:00")).astimezone(ET).date()).days
    ok(V.get("terps.daysToOpener") == str(days), f"Terps countdown {V.get('terps.daysToOpener')} days == {days}")
    lev = [e for e in events(raw("terps_schedule_2026"), "MD") if e["done"]]
    lw = sum(result(e) == "W" for e in lev)
    ok(V.get("terps.lastSeason") == f"{lw}-{len(lev) - lw}", f"Terps 2025-26 record {V.get('terps.lastSeason')} == results {lw}-{len(lev) - lw}")
    ok(V.get("terps.record") == "0-0", "Terps 2026-27 record shows 0-0 (season not started)")


    # ---------------- headlines, sources, offline
    desk = json.load(open(os.path.join(HERE, "data", "desk.json")))

    # ---------------- Sunday Mode
    sm = desk.get("sundayMode") or {}
    ok(sm.get("cards") and sm.get("weekend"), "Sunday Mode payload present with weekend + cards")
    ok(V.get("sunday.weekend") == (sm.get("weekend") or {}).get("label"), f"Sunday Mode weekend label on page: {V.get('sunday.weekend')}")
    by = {c["key"]: c for c in sm.get("cards", [])}
    rav_c, che_c = by.get("ravens"), by.get("chelsea")
    if rav_c and rav_c.get("inWindow") and rav_c.get("event"):
        ok(V.get("sunday.ravens.et") == rav_c["event"]["et"], f"Sunday Mode Ravens kickoff {V.get('sunday.ravens.et')} == {rav_c['event']['et']}")
        ok(V.get("sunday.ravens.record") == rav_c["record"] == V.get("ravens.record"), f"Sunday Mode Ravens record matches desk {V.get('sunday.ravens.record')}")
        ok("Falcons" in (V.get("sunday.ravens.matchup") or "") or "ATL" in (V.get("sunday.ravens.matchup") or ""), f"Sunday Mode Ravens matchup: {V.get('sunday.ravens.matchup')}")
    if che_c and che_c.get("inWindow") and che_c.get("event"):
        ok(V.get("sunday.chelsea.et") == che_c["event"]["et"], f"Sunday Mode Chelsea kickoff {V.get('sunday.chelsea.et')} == {che_c['event']['et']}")
        ok(V.get("sunday.chelsea.record") == che_c["record"] == V.get("chelsea.record"), f"Sunday Mode Chelsea record matches desk {V.get('sunday.chelsea.record')}")
    ok("Watch cards only" in dom or "watch card" in dom.lower(), "Sunday Mode disclaimer / watch-card framing present in DOM")
    ok("not a pick" in dom.lower() or "Desk chrome" in dom, "Sunday Mode lean framed as chrome, not a pick")

    for t in desk["teams"]:
        h = t.get("headline") or {}
        pool = set()
        try:
            pool |= {a["links"]["web"]["href"] for a in raw(f"{t['key']}_news").get("articles", []) if a.get("links", {}).get("web")}
        except Exception:  # noqa: BLE001
            pass
        try:
            pool |= {i["url"] for i in raw(f"{t['key']}_rss")}
        except Exception:  # noqa: BLE001
            pass
        ok(h.get("url") in pool and V.get(f"{t['key']}.headline") == h.get("title"), f"{t['name']} headline links to a fetched source story: {h.get('title')!r}")
        ok(all(s.get("fetchedAt") for s in t["sources"]), f"{t['name']}: all {len(t['sources'])} sources carry a fetched-at time")
    remote = [s for s in g.imgs if s.startswith("http")]
    ok(not remote, f"snapshot has no remote images ({len(g.imgs)} inline)")
    ok("Late Edition · data fetched" in dom, "page shows the fetched-at time in the dateline")

    # ---------------- live server
    try:
        hp = json.load(urllib.request.urlopen("http://127.0.0.1:4244/api/health", timeout=10))
        live = json.load(urllib.request.urlopen("http://127.0.0.1:4244/api/desk", timeout=30))
        ok(hp.get("ok") and [t.get("record") for t in live["teams"]] == [t.get("record") for t in desk["teams"]], "server on :4244 healthy and serving the same records")
    except Exception as e:  # noqa: BLE001
        ok(False, f"server on :4244 reachable ({e})")

    print(f"\n{len(PASSES)} passed, {len(FAILS)} failed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
