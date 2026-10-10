/* Sports Desk renderer. Data comes from /api/desk (live server) or window.DESK (offline snapshot).
   Everything shown is read from that payload; missing values render as an explicit gap. */
(function () {
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const gap = (txt) => `<span class="gap">${esc(txt || "not found in source")}</span>`;
  const val = (v, key) => (v == null || v === "" ? gap("—") : `<span data-check="${key}">${esc(v)}</span>`);
  const img = (src, alt, cls) => (src ? `<img src="${esc(src)}" alt="${esc(alt || "")}" ${cls ? `class="${cls}"` : ""} loading="eager">` : "");
  const fmtEt = (iso) => {
    if (!iso) return null;
    const d = new Date(iso);
    return d.toLocaleString("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) + " ET";
  };

  function sparkSvg(sp, c1, c2, opts = {}) {
    const pts = (sp && sp.points) || [];
    if (!pts.length) return `<div class="gap">No completed games in the source yet.</div>`;
    const W = 620, H = opts.h || 96, padL = 26, padR = 64, padT = 12, padB = 16;
    const vals = pts.map((p) => p.v);
    let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
    if (hi - lo < 4) { hi += 2; lo -= sp.kind === "points" ? 0 : 2; }
    const x = (i) => padL + (pts.length === 1 ? (W - padL - padR) / 2 : (i * (W - padL - padR)) / (pts.length - 1));
    const y = (v) => padT + ((hi - v) * (H - padT - padB)) / (hi - lo || 1);
    const line = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
    const y0 = y(0);
    let g = "";
    g += `<defs><clipPath id="up-${opts.id}"><rect x="0" y="0" width="${W}" height="${y0}"/></clipPath><clipPath id="dn-${opts.id}"><rect x="0" y="${y0}" width="${W}" height="${H}"/></clipPath></defs>`;
    const area = `${line}L${x(pts.length - 1).toFixed(1)},${y0}L${x(0).toFixed(1)},${y0}Z`;
    if (sp.kind === "over500") {
      g += `<path d="${area}" fill="${c1}" opacity=".22" clip-path="url(#up-${opts.id})"/>`;
      g += `<path d="${area}" fill="#7a7062" opacity=".22" clip-path="url(#dn-${opts.id})"/>`;
      g += `<line x1="${padL}" x2="${W - padR}" y1="${y0}" y2="${y0}" stroke="#16130f" stroke-width="1" stroke-dasharray="2 3"/>`;
      g += `<text x="${padL - 4}" y="${y0 + 3}" font-size="9.5" text-anchor="end" font-family="Oswald" fill="#6d6457">.500</text>`;
    } else {
      g += `<path d="${area}" fill="${c1}" opacity=".16"/>`;
      g += `<line x1="${padL}" x2="${W - padR}" y1="${y0}" y2="${y0}" stroke="#16130f" stroke-width="1"/>`;
    }
    g += `<path d="${line}" fill="none" stroke="${c1}" stroke-width="${pts.length > 60 ? 1.6 : 2.4}" stroke-linejoin="round"/>`;
    if (pts.length <= 40) {
      pts.forEach((p, i) => {
        const col = p.r === "W" ? "#1f7a3f" : p.r === "L" ? "#b3261e" : "#8a7d63";
        g += `<circle cx="${x(i).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="${pts.length > 20 ? 2.6 : 4.2}" fill="${col}" stroke="#f6f1e6" stroke-width="1.2"><title>${esc(p.d)} ${p.r} vs ${esc(p.opp)} ${esc(p.s)}</title></circle>`;
        if (pts.length <= 8) g += `<text x="${x(i).toFixed(1)}" y="${H - 2}" font-size="9.5" text-anchor="middle" font-family="Oswald" fill="#6d6457">${esc(p.opp)}</text>`;
      });
    }
    if (opts.marks) {
      opts.marks.forEach((m) => {
        const i = pts.findIndex((p) => p.d === m.d && p.v === m.v);
        if (i < 0) return;
        const yy = y(m.v);
        g += `<circle cx="${x(i)}" cy="${yy}" r="3.4" fill="#16130f"/><text x="${x(i) + 5}" y="${yy + (m.v >= 0 ? -5 : 12)}" font-size="10" font-family="Oswald" fill="#16130f">${esc(m.label)}</text>`;
      });
    }
    const last = pts[pts.length - 1];
    const endTxt = sp.kind === "points" ? `${last.v} pts` : `${last.v > 0 ? "+" : ""}${last.v}`;
    g += `<text x="${x(pts.length - 1) + 8}" y="${y(last.v) + 5}" font-size="17" font-weight="700" font-family="Oswald" fill="${c1}" data-check="${opts.id}.sparkEnd">${esc(endTxt)}</text>`;
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sp.label)}">${g}</svg>`;
  }

  function oppCell(e) {
    const where = e.neutral ? "vs" : e.home ? "vs" : "at";
    return `<td class="o">${img(e.oppLogoLocal || e.oppLogo, e.oppAbbr)}<span class="comp">${where}</span> ${esc(e.oppShort || e.opp)}${e.competition && e.sport === "soccer" ? "" : ""}</td>`;
  }

  function lastTable(t) {
    const L = t.last || [];
    if (!L.length) return gap("No completed games found.");
    return `<table class="games">${L.map((e, i) => `<tr data-row="${t.key}.last.${i}">
      <td><span class="res ${e.result}" data-check="${t.key}.last.${i}.result">${esc(e.result || "?")}</span></td>
      ${oppCell(e)}
      <td class="sc" data-check="${t.key}.last.${i}.score">${esc(e.score)}–${esc(e.oppScore)}</td>
      <td class="comp">${esc(new Date(e.date).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" }))}${t.sport === "soccer" ? "<br>" + esc((e.competition || "").replace("English ", "").replace(" 2026-27", "")) : ""}</td></tr>`).join("")}</table>`;
  }

  function nextTable(t) {
    const N = t.next || [];
    if (!N.length) return gap(t.key === "orioles" ? "No games scheduled — the 2026 season is over for Baltimore." : "No upcoming fixtures in the source.");
    return `<table class="games">${N.map((e, i) => `<tr>
      ${oppCell(e)}
      <td class="when" data-check="${t.key}.next.${i}.et">${esc(e.et)}</td>
      <td>${e.tv && e.tv.length ? e.tv.map((n) => `<span class="tv">${esc(n)}</span>`).join("") : `<span class="comp">TV n/a</span>`}</td></tr>`).join("")}</table>`;
  }

  function teamCard(t) {
    const [c1, c2] = t.colors || ["#333", "#999"];
    const h = t.headline;
    const story = h
      ? `<div class="story ${h.imageLocal ? "" : "noimg"}"><div>
          <h2><a href="${esc(h.url)}" target="_blank" rel="noopener" data-check="${t.key}.headline">${esc(h.title)}</a></h2>
          ${h.desc ? `<p class="dek">${esc(h.desc.length > 210 ? h.desc.slice(0, 207) + "…" : h.desc)}</p>` : ""}
          <div class="by">${esc(h.source)}${h.publishedEt ? " · " + esc(h.publishedEt) : ""}</div></div>
          ${h.imageLocal ? img(h.imageLocal, h.title) : ""}</div>`
      : gap("No headline found in the news feeds.");
    const more = (t.more || []).slice(0, 3).map((m) => `<li><a href="${esc(m.url)}" target="_blank" rel="noopener">${esc(m.title)}</a> <span class="src">${esc(m.source)}${m.publishedEt ? " · " + esc(m.publishedEt.split(" · ")[0]) : ""}</span></li>`).join("");
    const marks = t.key === "orioles" && t.seasonSummary ? [{ d: t.seasonSummary.peak.d, v: t.seasonSummary.peak.v, label: `peak +${t.seasonSummary.peak.v}` }, { d: t.seasonSummary.low.d, v: t.seasonSummary.low.v, label: `low ${t.seasonSummary.low.v}` }] : null;
    const facts = (t.facts || []).map(([k, v], i) => `<div class="fact"><b>${v == null ? "—" : `<span data-check="${t.key}.fact.${i}">${esc(v)}</span>`}</b><span>${esc(k)}</span></div>`).join("");
    return `<section class="team" id="${t.key}" style="--c1:${c1};--c2:${c2}">
      <div class="flag">${img(t.logoLocal || t.logo, t.name)}<div><div class="nm">${esc(t.name)}</div><div class="lg">${esc(t.leagueLabel)}</div></div>
        <div class="rec"><b>${val(t.record, t.key + ".record")}</b><span>${esc(t.recordLabel || "")}</span></div></div>
      <div class="standline"><span>${val(t.standing, t.key + ".standing")}</span>${t.espnStanding && t.espnStanding !== t.standing && t.key !== "terps" ? `<span class="muted">ESPN: ${esc(t.espnStanding)}</span>` : ""}</div>
      ${story}
      ${more ? `<ul class="more">${more}</ul>` : ""}
      <div class="cols">
        <div><div class="lbl"><span>${esc(t.lastLabel || "Last 5")}</span><em>${t.sport === "soccer" ? "all comps" : ""}</em></div>${lastTable(t)}</div>
        <div><div class="lbl"><span>Next 3</span><em>times ET</em></div>${nextTable(t)}</div>
      </div>
      <div class="spark"><div class="lbl"><span>${esc((t.spark && t.spark.label) || "Season")}</span><em>${t.spark && t.spark.kind === "over500" ? "W +1 · L −1" : "W 3 · D 1 · L 0"}</em></div>${sparkSvg(t.spark, c1, c2, { id: t.key, marks, h: t.key === "orioles" ? 110 : 92 })}</div>
      <div class="facts">${facts}</div>
    </section>`;
  }

  function stdTable(cols, rows, render, cls) {
    return `<table class="std"><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => render(r)).join("")}</tbody></table>`;
  }

  function agate(D) {
    const T = Object.fromEntries(D.teams.map((t) => [t.key, t]));
    const che = T.chelsea, rav = T.ravens, ori = T.orioles, md = T.terps;
    let out = `<div class="section-head">Standings · Agate · Season Desk</div><div class="agate">`;
    // Premier League table
    const zones = {};
    out += `<div><h3>Premier League <small>table · ESPN</small></h3>`;
    if (che && che.table && che.table.rows.length) {
      out += stdTable(["#", "Club", "P", "W", "D", "L", "GF", "GA", "GD", "Pts"], che.table.rows, (r) => {
        if (r.note) zones[r.note] = r.noteColor;
        return `<tr class="${r.me ? "me" : ""} ${r.note ? "zone" : ""}" style="${r.noteColor ? `--z:${esc(r.noteColor)}` : ""}" ${r.me ? 'data-check-row="chelsea.table"' : ""}>
          <td class="rk">${esc(r.rank)}</td><td class="tm">${img(r.logoLocal || r.logo, r.abbr)}${esc(r.team)}</td>
          <td>${esc(r.p)}</td><td>${esc(r.w)}</td><td>${esc(r.d)}</td><td>${esc(r.l)}</td><td>${esc(r.gf)}</td><td>${esc(r.ga)}</td><td>${esc(r.gd)}</td><td class="pts" ${r.me ? 'data-check="chelsea.table.pts"' : ""}>${esc(r.pts)}</td></tr>`;
      });
      out += `<div class="legend">${Object.entries(zones).map(([n, c]) => `<span><i style="background:${esc(c)}"></i>${esc(n)}</span>`).join("")}</div>`;
      out += `<div class="note">${esc(che.table.note)}</div>`;
    } else out += gap("Premier League table unavailable.");
    out += `</div>`;
    // Ravens + Orioles
    out += `<div>`;
    out += `<div class="box"><h3>AFC North <small>2026 · ESPN</small></h3>`;
    if (rav && rav.table && rav.table.rows.length) {
      out += stdTable(["", "Team", "W-L", "PCT", "DIV", "PF", "PA", "DIFF", "STRK"], rav.table.rows, (r) => `<tr class="${r.me ? "me bal" : ""}">
        <td class="rk">${esc(r.seed ? "#" + r.seed : "")}</td><td class="tm">${img(r.logoLocal || r.logo, r.abbr)}${esc(r.team)}</td><td ${r.me ? 'data-check="ravens.table.rec"' : ""}>${esc(r.rec)}</td><td>${esc(r.pct)}</td><td>${esc(r.div)}</td><td>${esc(r.pf)}</td><td>${esc(r.pa)}</td><td>${esc(r.diff)}</td><td>${esc(r.strk)}</td></tr>`);
      out += `<div class="note">Seed = AFC playoff seed in ESPN's standings feed; teams level on record are listed in ESPN's tiebreak order.</div>`;
    } else out += gap("AFC North standings unavailable.");
    out += `</div>`;
    out += `<div class="box"><h3>Orioles: Season Over <small>2026 final</small></h3>`;
    const s = ori && ori.seasonSummary;
    if (s) {
      out += `<div class="bigstat"><div><b data-check="orioles.summary.wl">${s.w}-${s.l}</b><span>final record</span></div><div><b data-check="orioles.summary.diff">${s.diff > 0 ? "+" : ""}${s.diff}</b><span>run diff (${s.rs} RS / ${s.ra} RA)</span></div><div><b>${s.longestWin}</b><span>longest win streak</span></div><div><b>${esc(s.oneRun)}</b><span>one-run games</span></div><div><b>${esc(s.vsDiv)}</b><span>vs AL East</span></div></div>`;
      out += `<div class="pullquote">${esc(ori.standing || "")}. Peaked at +${s.peak.v} on ${esc(s.peak.d)}, bottomed out at ${s.low.v} on ${esc(s.low.d)}; best month ${(() => { const b = s.months.slice().sort((a, c) => (c.w - c.l) - (a.w - a.l))[0]; return b ? esc(b.m) + " (" + b.w + "-" + b.l + ")" : "n/a"; })()}.</div>`;
      const mx = Math.max(...s.months.map((m) => m.w + m.l));
      out += `<div class="months">${s.months.map((m) => `<div class="month"><div class="bar"><div class="w" style="height:${(m.w / mx) * 70}px" title="${m.w} W"></div><div class="l" style="height:${(m.l / mx) * 70}px" title="${m.l} L"></div></div><b>${m.w}-${m.l}</b><span>${esc(m.m)}</span></div>`).join("")}</div>`;
      out += `<div class="legend"><span><i style="background:#df4601"></i>wins</span><span><i style="background:#2b2b2b"></i>losses</span><span>· ${s.games} decided games, ${esc(s.first)} → ${esc(s.lastGame)} (ESPN: finale vs NYY rained out)</span></div>`;
      if (ori.table && ori.table.rows.length) {
        out += `<div style="margin-top:8px"></div>` + stdTable(["", "AL East", "W", "L", "PCT", "GB", "DIFF", "L10"], ori.table.rows, (r) => `<tr class="${r.me ? "me ori" : ""}"><td class="rk">${esc(r.clinch && r.clinch !== "" ? r.clinch : "")}</td><td class="tm">${img(r.logoLocal || r.logo, r.abbr)}${esc(r.team)}</td><td ${r.me ? 'data-check="orioles.table.w"' : ""}>${esc(r.w)}</td><td>${esc(r.l)}</td><td>${esc(r.pct)}</td><td>${esc(r.gb)}</td><td>${esc(r.diff)}</td><td>${esc(r.l10)}</td></tr>`);
        out += `<div class="note">Clinch codes as ESPN reports them (e.g. z = division, y = playoff berth / bye, x = clinched spot).</div>`;
      }
    } else out += gap("Orioles season data unavailable.");
    out += `</div></div>`;
    // Terps preseason
    out += `<div><div class="box"><h3>Terps Tip-Off Watch <small>2026-27 preseason</small></h3>`;
    const p = md && md.preseason;
    if (p && p.opener) {
      out += `<div class="countdown"><div class="n" data-check="terps.daysToOpener">${p.daysToOpener}</div><div class="t">days to the opener<br><span style="font-weight:400;font-style:italic">${esc(p.opener.oppShort)}${p.opener.venue ? " at " + esc(p.opener.venue) : ""} · ${esc(p.opener.et)}${p.opener.tv.length ? " · " + esc(p.opener.tv.join(", ")) : ""}</span></div></div>`;
      out += `<div class="bigstat"><div><b data-check="terps.games">${p.games}</b><span>games listed</span></div><div><b>${p.home}</b><span>home</span></div><div><b>${p.away}</b><span>away</span></div><div><b>${p.neutral}</b><span>neutral</span></div><div><b>${p.bigTen}</b><span>Big Ten</span></div></div>`;
      out += `<div class="lbl"><span>2026-27 schedule</span><em>red = home · gold = neutral · bold = Big Ten</em></div><div class="sched">${p.fullSchedule.map((g) => {
        const d = new Date(g.date).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "numeric", day: "numeric" });
        const b10 = ["ILL", "IND", "IU", "IOWA", "MSU", "MICH", "MINN", "NEB", "NU", "OSU", "PSU", "PUR", "RUTG", "UCLA", "USC", "WASH", "WIS", "ORE"].includes(g.abbr);
        return `<div class="${g.neutral ? "n" : g.home ? "h" : ""} ${b10 ? "b10" : ""}" title="${esc(g.et)} ${esc(g.opp)} ${esc(g.tv.join(", "))}">${esc(g.abbr)}<small>${esc(d)}</small></div>`;
      }).join("")}</div>`;
      const tot = p.tv.reduce((a, [, n]) => a + n, 0) || 1;
      const pal = ["#16130f", "#e21833", "#ffd200", "#6d6457", "#034694", "#1f7a3f"];
      out += `<div class="lbl"><span>TV mix (listed broadcasts)</span></div><div class="tvmix">${p.tv.map(([n, c], i) => `<span style="width:${(c / tot) * 100}%;background:${pal[i % pal.length]}" title="${esc(n)} ${c}"></span>`).join("")}</div>`;
      out += `<div class="legend">${p.tv.map(([n, c], i) => `<span><i style="background:${pal[i % pal.length]}"></i>${esc(n)} ${c}</span>`).join("")}</div>`;
      out += `<div class="note" style="margin-top:8px">Last season: <b data-check="terps.lastSeason">${esc(p.lastSeasonRecord)}</b> across ${p.lastSeasonGames} games in ESPN's 2025-26 results${p.lastSeasonFinal ? `, the last a ${esc(p.lastSeasonFinal.score)}–${esc(p.lastSeasonFinal.oppScore)} ${p.lastSeasonFinal.result === "W" ? "win over" : "loss to"} ${esc(p.lastSeasonFinal.oppShort)} on ${esc(new Date(p.lastSeasonFinal.date).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", year: "numeric" }))}` : ""}.</div>`;
    } else out += gap("Terps 2026-27 schedule unavailable.");
    out += `</div>`;
    // Ravens upcoming tough stretch: next 3 already shown; add game-day planner of all next games
    if (rav && rav.next && rav.next.length) {
      out += `<div class="box"><h3>Watch Guide <small>next 7 days+ · ET</small></h3><table class="games">`;
      const all = [];
      D.teams.forEach((t) => (t.next || []).forEach((e) => all.push({ t, e })));
      all.sort((a, b) => (a.e.date < b.e.date ? -1 : 1));
      out += all.slice(0, 8).map(({ t, e }) => `<tr><td><span class="res" style="background:${t.colors[0]};width:auto;padding:0 5px">${esc(t.abbr)}</span></td><td class="o">${e.home ? "vs" : "at"} ${esc(e.oppShort)}</td><td class="when">${esc(e.et)}</td><td>${e.tv.map((n) => `<span class="tv">${esc(n)}</span>`).join("") || '<span class="comp">TV n/a</span>'}</td></tr>`).join("");
      out += `</table></div>`;
    }
    out += `</div></div>`;
    return out;
  }


  function sundayMode(D) {
    const sm = D.sundayMode;
    const el = $("#sundayMode");
    if (!sm || !sm.cards || !sm.cards.length) { el.hidden = true; el.innerHTML = ""; return; }
    el.hidden = false;
    const cards = sm.cards.map((c) => {
      const e = c.event;
      const logos = e
        ? `<div class="logos">${img(c.logoLocal, c.team)}<div class="vs">${esc((e.where || "").toUpperCase())}</div>${img(e.oppLogoLocal, e.oppAbbr || e.opp)}</div>`
        : `<div class="logos">${img(c.logoLocal, c.team)}</div>`;
      const matchup = e
        ? `<div class="matchup" data-check="sunday.${c.key}.matchup">${esc(c.team)} ${esc(e.where || "")} ${esc(e.opp)}</div>
           <div class="meta"><span data-check="sunday.${c.key}.et">${esc(e.et || "time TBD")}</span>${(e.tv || []).map((n) => `<span class="tv">${esc(n)}</span>`).join("") || '<span class="comp"> TV n/a</span>'}${e.venue ? ` · ${esc(e.venue)}` : ""}${e.week ? ` · ${esc(e.week)}` : ""}</div>`
        : `<div class="matchup">${esc(c.standing || "No weekend fixture")}</div>`;
      const facts = (c.facts || []).slice(0, 4).map((f) => `<span><b>${esc(f.value)}</b> ${esc(f.label)}</span>`).join("");
      const lean = c.lean
        ? `<div class="lean"><div class="lbl">${esc(c.lean.label)}</div><div class="txt">${esc(c.lean.text)}</div><div class="dis">${esc(c.lean.disclaimer)}</div></div>`
        : "";
      const note = c.note ? `<div class="note">${esc(c.note)}</div>` : "";
      return `<article class="watch ${c.inWindow ? "in" : ""}" data-check-row="sunday.${c.key}">
        <div class="badge"><span>${esc(c.tagline)}</span>${c.inWindow ? '<span class="live">This weekend</span>' : "<span>Desk</span>"}</div>
        ${logos}
        <div class="body">
          <div class="nm">${esc(c.full)}</div>
          ${matchup}
          <div class="recrow"><span data-check="sunday.${c.key}.record">${esc(c.record || "—")}</span>${c.standing ? `<span data-check="sunday.${c.key}.standing">${esc(c.standing)}</span>` : ""}${facts}</div>
          ${lean}${note}
        </div>
      </article>`;
    }).join("");
    el.innerHTML = `<div class="sm-head">
        <div><div class="sm-kicker">TokenMax · Boyd Edition</div>
          <div class="sm-title">${esc(sm.title)}</div>
          <div class="sm-sub">${esc(sm.subtitle)}</div></div>
        <div class="sm-weekend">This weekend<b data-check="sunday.weekend">${esc(sm.weekend.label)}</b></div>
      </div>
      <div class="sm-grid">${cards}</div>
      <div class="sm-disclaimer">${esc(sm.disclaimer)}</div>`;
  }

  function render(D) {
    const T = D.teams;
    sundayMode(D);
    $("#dateline").innerHTML = `<span>Millersville, Md.</span><span>${esc(new Date(D.generatedAt).toLocaleDateString("en-US", { timeZone: "America/New_York", weekday: "long", year: "numeric", month: "long", day: "numeric" }))}</span><span>Late Edition · data fetched ${esc(D.generatedAtEt || fmtEt(D.generatedAt))}</span>`;
    const allNext = [];
    T.forEach((t) => (t.next || []).forEach((e) => allNext.push({ t, e })));
    allNext.sort((a, b) => (a.e.date < b.e.date ? -1 : 1));
    const n0 = allNext[0];
    $("#earLeft").innerHTML = n0 ? `Next on the dial<b>${esc(n0.t.name)} ${n0.e.home ? "vs" : "at"} ${esc(n0.e.oppShort)}</b>${esc(n0.e.et)}${n0.e.tv.length ? " · " + esc(n0.e.tv.join(", ")) : ""}` : "";
    const rav = T.find((t) => t.key === "ravens");
    $("#earRight").innerHTML = rav && rav.next && rav.next[0] ? `Ravens · ${esc(rav.record || "")}<b>${rav.next[0].home ? "vs" : "at"} ${esc(rav.next[0].oppShort)}</b>${esc(rav.next[0].et)}${rav.next[0].tv.length ? " · " + esc(rav.next[0].tv.join(", ")) : ""}` : "";
    $("#ticker").innerHTML = T.map((t) => {
      const e = (t.next || [])[0];
      const v = e ? `${e.home ? "vs" : "at"} ${esc(e.oppAbbr)} · ${esc(e.et)}` : t.key === "orioles" ? "Season over · " + esc(t.record || "") : "—";
      return `<a class="tick" href="#${t.key}">${img(t.logoLocal || t.logo, t.name)}<div><div class="k">${esc(t.name)} · ${esc(t.record || "")}</div><div class="v">${v}</div></div></a>`;
    }).join("");
    $("#desk").innerHTML = `<div class="front">${T.map(teamCard).join("")}</div>${agate(D)}`;
    const srcs = T.map((t) => `<div class="s"><h4>${esc(t.full)}</h4>${(t.sources || []).map((s) => `<div><span class="st ${esc(s.state)}">${esc(s.state)}</span> ${esc(s.name)} · fetched ${esc(s.fetchedAt ? fmtEt(s.fetchedAt) : "never")}${s.from ? ` (${esc(s.from)})` : ""}${s.error ? ` · <i>${esc(s.error)}</i>` : ""}<br><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.url)}</a></div>`).join("")}</div>`).join("");
    $("#colophon").innerHTML = `<div class="s"><h4>About this page</h4>Built by TokenMax for Christopher Boyd. Sunday Mode watch cards use only opponent, kickoff (ET), TV, and records from the same feeds — no invented lines or injury claims. Records, standings, scores, fixtures and TV come from ESPN's public JSON endpoints; Terps and Orioles lead stories come from the teams' official RSS feeds (umterps.com, MLB.com). Derived numbers (games over .500, Orioles monthly splits, Terps schedule counts) are arithmetic on those payloads. Anything a source didn't return is left blank. Page built ${esc(D.generatedAtEt || "")}.</div>${srcs}`;
    document.body.dataset.ready = "1";
  }

  if (window.DESK) render(window.DESK);
  else fetch("/api/desk").then((r) => r.json()).then(render).catch((e) => { $("#desk").innerHTML = `<p class="loading">Couldn't load the desk: ${esc(e)}</p>`; });
})();
