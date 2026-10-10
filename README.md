# The Sports Desk

A newspaper-style sports front for Boyd's teams (Ravens, Chelsea, Orioles, Terps men's basketball),
with ESPN-style data viz and a **Sunday Mode** weekend watch-card panel. Remastered by TokenMax
on Oct 10, 2026 (Saturday daily-usage-check).

**Live:** http://127.0.0.1:4244 (box only) · **Offline:** `dist/sports-desk-snapshot.html` (one file, opens anywhere) · **Best shot:** `screenshots/00-best-home.png`

## What's on the page
- **Masthead + ticker:** the next game for each team, in ET with TV.
- **Sunday Mode:** Bill Simmons–style watch cards for this weekend's Ravens (and Chelsea when in-window). Cards show only opponent, kickoff ET, TV, and records from the fetched payloads. Any “lean” is labeled as playful UI chrome — **not a pick**, and never invents lines or injuries.
- **One section per team:** record and standing, a lead story linked to its source, three more links,
  the last 5 results, the next 3 fixtures (ET + TV where the source lists it), a season sparkline and a fact strip.
  - Ravens: current season record and AFC North position. When teams are level on record, the tie is called out using ESPN's own tiebreak order.
  - Chelsea: Premier League record, position and points. The last 5 and next 3 cover all competitions, friendlies excluded. The sparkline is cumulative league points.
  - Orioles: the final 2026 record. The sparkline shows games over .500 across decided games, with the peak and low marked.
  - Terps: 2026-27 tip-off watch. The section shows the opener and the next 3 games, plus the last 5 of 2025-26 and that season's sparkline.
- **Agate section:**
  - the full Premier League table, with ESPN's zone notes
  - AFC North standings
  - an *Orioles: Season Over* box: run differential, streaks, one-run record, record vs the AL East, month-by-month bars, and final AL East standings
  - *Terps Tip-Off Watch*: countdown, the full schedule grid, and the TV mix
  - a combined watch guide
- **Colophon:** every source URL, with its fetched-at time (ET) and status (live / stale / unavailable).

## Data sources (all free, no keys)
| What | Source |
|---|---|
| Schedules, results, records, TV | ESPN public site API, e.g. `site.api.espn.com/apis/site/v2/sports/football/nfl/teams/bal/schedule` |
| Standings and tables | `site.api.espn.com/apis/v2/sports/{sport}/{league}/standings` |
| Headlines | ESPN team news feeds, plus the official RSS feeds from umterps.com (Terps) and MLB.com (Orioles) |

The approach is copied from `../boyd-wall/collect.py`: per-source disk cache, TTLs, and fallback to the last good copy when a fetch fails. Boyd Wall's cache is used only as a **read-only** seed for identical URLs; nothing in `../boyd-wall` is written.

**No invented data.** Every number is copied from a payload or computed from one by simple arithmetic (games over .500, monthly splits, schedule counts, run totals). If a value is missing, the page shows a gap ("—", "TV n/a", "not found in source").

## Files
```
collect.py          fetch + cache + build data/desk.json (stdlib only), including sundayMode
server.py           serves web/, /api/desk, /api/health, /img/*; refreshes every 15 min
web/                index.html, style.css, app.js, fonts/ (Unifraktur, Playfair, Oswald, Libre Franklin)
export_snapshot.py  bundles everything (fonts, images, data) into dist/sports-desk-snapshot.html
render.sh           screenshots (1440x900, full page, phone) + dist/sports-desk.pdf
tests/smoke_test.py cross-checks displayed numbers against raw cached payloads + Sunday Mode
run.sh              start | restart | stop | build
config.json         teams, endpoints, TTLs, port 4244
```

## Run
```bash
./run.sh            # start on :4244 (nohup, idempotent)
./run.sh build      # collect → snapshot → screenshots + PDF → smoke test
python3 collect.py --force   # ignore TTLs and refetch everything
```


---
## Repo notes
- **Built:** Oct 10, 2026, by TokenMax (Boyd's Grok Bot) on the Grok Bot box.
- **Run:** `./run.sh` (then open the localhost URL it prints).
- Imported from `/workspace/tokenmax/sports-desk` on Oct 23, 2026. node_modules, virtualenvs, logs and files over 20 MB were left out.
