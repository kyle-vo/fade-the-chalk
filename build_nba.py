"""Render docs/nba.html from backtest/nba_<date>.json (written by nba.py): moneyline, spread and total for each NBA game, Robinhood's ask vs Pinnacle's
fair price, the crowd's money on each side (Kalshi trade tape), results, and a scorecard.
Rules, re-tested 2026-10-30 on last season (1,306 games) and checked on this season's first 71.
Last season's spread/total strikes in research/nba_hist_2025.json were picked by trading volume, which includes in-game trading, so they lean
toward the final score: their cover rates are biased. Spreads are now tested against the line implied by Kalshi's closing moneyline
(margin ~ Normal(13.5 * z(p)), within 0.5 pts of Pinnacle's line), at a 51c ask plus fee.
  spread BET   = won its last game by 18+ AND (its opponent also won its last OR it is the underdog): 62% (+18%), 61% / 63% by half; 2026 8-2.
                 STRONG when both. If both teams qualify, only the underdog (16-9; the favorite 9-16). Coming off a blowout, favored, against a team that lost its last: 48%, no edge -> PASS.
  ML LEAN      = the same team on the moneyline (+15%).
  LEAN         = the better team (season margin 4+/game better, 5+ games each) as the moneyline underdog: +33% on 47 games, both halves.
  LEAN         = the underdog getting 10-12.5 points: 57% both halves (+8%).
  total LEAN   = under below 220: NOT validated (last season's totals data is the biased kind); kept small until this season says otherwise.
Dropped: fading a 4c spread line move. Measured on the moneyline price (unbiased), fading a 3c+ move in the last 6h covered 43% (-19%);
following it 57%, best when the move is toward an underdog that stays the underdog (60%). Tracked on the scorecard, not a pick yet.
Still nothing: crowd money of any kind (ML or spread, big or small, early or late), back-to-backs, rest, streaks, home/road."""
import json, os, re, glob, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); SITE = os.path.join(HERE, 'docs')
J = lambda p: json.load(open(p, encoding='utf-8'))
jd = lambda o: json.dumps(o, separators=(',', ':')).replace('</', '<' + chr(92) + '/')
src = open(os.path.join(HERE, 'build_site.py'), encoding='utf-8').read()
CSS = re.search(r'CSS = r"""(.*?)"""', src, re.S).group(1); FONTS = re.search(r"FONTS = '(.*?)'", src).group(1)

days = {os.path.basename(p)[4:-5]: J(p) for p in sorted(glob.glob(os.path.join(BT, 'nba_20*.json')))}   # dated files only (not nba_pinnacle_cache.json)
days = {d: rows for d, rows in days.items() if rows}
order = sorted(days, reverse=True)
# each team's previous final (margin, from our own graded days): the blowout rule needs it at board time
_log = {}
for d in sorted(days):
    for r in days[d]:
        if r.get('final'):
            for t, m in ((r['home'], r['finalHome'] - r['finalAway']), (r['away'], r['finalAway'] - r['finalHome'])): _log.setdefault(t, []).append((r['time'], m))
for d in days:
    for r in days[d]:
        for side in ('home', 'away'):
            prev = [m for t, m in _log.get(r[side], []) if t < r['time']]
            r[side + 'Last'] = prev[-1] if prev else None
            r[side + 'Margin'] = round(sum(prev) / len(prev), 1) if prev else None; r[side + 'Gp'] = len(prev)   # season point differential per game so far
_pt = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=-7)).date().isoformat()
cur = _pt if _pt in days else (min([d for d in order if d >= _pt], default=None) or (order[0] if order else None))

JS = r"""
const $ = s => document.querySelector(s); let day = CUR;
window.onNavSlate = (sp, v) => { day = v; render(); };
const cents = p => p == null ? '—' : Math.round(p * 100) + '¢';
const amer = p => { if (!p || p <= 0 || p >= 1) return ''; return p >= .5 ? '−' + Math.round(100 * p / (1 - p)) : '+' + Math.round(100 * (1 - p) / p); };
const pct = p => p == null ? '—' : Math.round(p * 100) + '%';
const money = v => v == null ? '—' : '$' + (v >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : v >= 1000 ? Math.round(v / 1000) + 'k' : Math.round(v));
const when = t => new Date(t).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
// one row per market side. crowd = share of the taker $ on this side; edge = Pinnacle fair minus Robinhood ask, in points
function sides(r){
  const out = [], m = r.ml, s = r.spread, t = r.total;
  if (m && (m.homeAsk || m.pinHome != null)) { const tot = (m['tapeHome$'] || 0) + (m['tapeAway$'] || 0);
    for (const [k, team, ask, fair, own] of [['home', r.home, m.homeAsk, m.pinHome, m['tapeHome$']], ['away', r.away, m.awayAsk, m.pinAway, m['tapeAway$']]])
      out.push({ r, kind: 'ml', team, side: team + ' ML', ask, fair, own: own || 0, tape: tot, crowd: tot ? (own || 0) / tot : null, hit: r.final ? ((r.homeWin === 1) === (k === 'home') ? 1 : 0) : null, fav: fair != null ? fair >= .5 : (ask || 0) >= .5 }); }
  if (s && s.fav) { const tot = (s['tapeFav$'] || 0) + (s['tapeDog$'] || 0);
    out.push({ r, kind: 'spread', team: s.fav, side: s.fav + ' −' + s.line, ask: s.favAsk, fair: s.pinFavFair, own: s['tapeFav$'] || 0, tape: tot, crowd: tot ? (s['tapeFav$'] || 0) / tot : null, hit: s.favCovered ?? null, fav: true });
    out.push({ r, kind: 'spread', team: s.dog, side: s.dog + ' +' + s.line, ask: s.dogAsk, fair: s.pinDogFair, own: s['tapeDog$'] || 0, tape: tot, crowd: tot ? (s['tapeDog$'] || 0) / tot : null, hit: s.favCovered == null ? null : 1 - s.favCovered, fav: false }); }
  if (t && t.line != null) { const tot = (t['tapeOver$'] || 0) + (t['tapeUnder$'] || 0);
    out.push({ r, kind: 'total', side: 'Over ' + t.line, ask: t.overAsk, fair: t.pinOverFair, own: t['tapeOver$'] || 0, tape: tot, crowd: tot ? (t['tapeOver$'] || 0) / tot : null, hit: t.over ?? null });
    out.push({ r, kind: 'total', side: 'Under ' + t.line, ask: t.underAsk, fair: t.pinUnderFair, own: t['tapeUnder$'] || 0, tape: tot, crowd: tot ? (t['tapeUnder$'] || 0) / tot : null, hit: t.over == null ? null : 1 - t.over }); }
  for (const x of out) { x.edge = (x.ask != null && x.fair != null) ? (x.fair - x.ask) * 100 : null;
    // coming off an 18+ point win: covers 62% when its opponent also won its last game or it is the underdog (both: STRONG);
    // favored against a team that lost its last, it's a coin flip (48%), so that case is a PASS (see the docstring for the numbers)
    const home = x.team === r.home, last = x.team ? (home ? r.homeLast : r.awayLast) : null, oppLast = x.team ? (home ? r.awayLast : r.homeLast) : null;
    x.last = last; const big = last != null && last >= 18, oppWon = oppLast != null && oppLast > 0;
    x.blowFav = big && !oppWon && x.fav; x.blow = big && (oppWon || !x.fav);
    // both teams qualify (each won its last by 18+): only the underdog's side counts (last season 16-9 for the underdog, 9-16 for the favorite)
    const oppBlow = oppLast != null && oppLast >= 18 && ((last != null && last > 0) || x.fav);
    if (x.blow && oppBlow && x.fav) { x.blow = false; x.bothFav = true; }
    x.v = 'PASS';
    if (x.kind === 'spread' && x.blow) x.v = oppWon && !x.fav ? 'STRONG BET' : 'BET';
    if (x.kind === 'ml' && x.blow) x.v = 'LEAN';
    // the better team (season point differential 4+ per game above its opponent's, 5+ games each) priced as the UNDERDOG:
    // +33% on the moneyline (47 games, both halves), only +5% on the spread, so the LEAN is the moneyline
    const myM = home ? r.homeMargin : r.awayMargin, opM = home ? r.awayMargin : r.homeMargin, gpOk = Math.min(r.homeGp || 0, r.awayGp || 0) >= 5;
    x.under = x.team && gpOk && myM != null && opM != null && myM - opM >= 4 && !x.fav && (x.kind === 'ml' || x.kind === 'spread');
    if (x.under && x.kind === 'ml' && x.v === 'PASS') x.v = 'LEAN';
    x.bigDog = x.kind === 'spread' && !x.fav && s && s.line >= 10 && s.line < 13;   // 10-12.5 point underdogs covered 57%
    if (x.bigDog && x.v === 'PASS') x.v = 'LEAN';
    if (x.kind === 'total' && x.side.startsWith('Under') && r.total && r.total.line < 220) x.v = 'LEAN';
    // line move: the favorite's price at this line now (frozen at tip) vs the first price seen 6h+ before tip. Not a pick any more (fading it
    // was measured on the biased strikes); x.toDog = a 2c+ move toward this underdog, the follow-the-move idea, tracked on the scorecard
    if (x.kind === 'spread') { const sp = r.spread || {}, op = (r.spreadOpen || {})[sp.ticker];
      if (op && sp.favAsk && sp.dogAsk && (new Date(r.time) - new Date(op[1])) >= 6 * 3600e3) {
        const mid = (sp.favAsk + 1 - sp.dogAsk) / 2, mv = mid - op[0]; x.move = mv;
        if (!x.fav && mv <= -0.02) x.toDog = true; } }
    x.why = [x.blow ? `${x.team} won its last game by ${last}` + (oppWon ? ', and its opponent won its last too' : '') + (!x.fav ? ', and it is the underdog' : '') : '',
             x.blowFav && x.v === 'PASS' && x.kind === 'spread' ? `${x.team} won its last by ${last} but is favored against a team that lost: no edge` : '',
             x.bothFav && x.kind === 'spread' ? `${x.team} won its last by ${last}, but so did its opponent: the underdog side is the play` : '',
             x.bigDog ? `${s.line}-point underdog (10-12.5 covered 57%)` : '',
             x.under ? `the better team (${myM >= 0 ? '+' : ''}${myM} vs ${opM >= 0 ? '+' : ''}${opM} per game) priced as the underdog` : '',
             x.v === 'LEAN' && x.kind === 'total' ? 'total under 220' : '',
             x.toDog ? `the line moved ${Math.round(Math.abs(x.move) * 100)}¢ toward ${x.team} (tracked, not a pick)` : ''].filter(Boolean).join(' · '); }
  return out;
}
// ---- board: one row per game. Every market on one line; our pick (if any) in its own column ----
const VRANK = { 'STRONG BET': 4, 'BET': 3, 'LEAN': 2, 'PASS': 0 };
const chip = v => `<span class="v ${v.replace(' ', '')}">${v}</span>`;
const odds = p => p == null ? '—' : `${cents(p)} <span class="tm">${amer(p)}</span>`;
const pickText = x => x.kind === 'ml' ? x.team + ' ML' : x.side;
const resMark = x => x.hit == null ? (x.r.final ? '<span class="res d">push</span>' : '') : x.hit ? '<span class="res y">✓</span>' : '<span class="res n">✗</span>';
function game(r){
  const xs = sides(r), m = r.ml || {}, s = r.spread || {}, t = r.total || {};
  const picks = xs.filter(x => x.v !== 'PASS').sort((a, b) => VRANK[b.v] - VRANK[a.v]);
  const tot = (m['tapeHome$'] || 0) + (m['tapeAway$'] || 0), awaySh = tot ? (m['tapeAway$'] || 0) / tot : null;
  const favP = Math.max(m.homeAsk || 0, m.awayAsk || 0) || null;
  // what the book kept and paid out: once final, the crowd's money on the losing side vs the winning side (trade tape, frozen at tip)
  let took = null, paid = null;
  // winners are paid their PROFIT, not their stake: stake x (1 - price) / price at the winning side's price ($102k on a 61¢ / -156 favorite wins ~$65k)
  const prof = (stake, p) => p && p > 0 && p < 1 ? stake * (1 - p) / p : stake;
  let mlWinStake = null, spWinStake = null;
  if (r.final && tot && r.homeWin != null) { const hw = r.homeWin === 1; took = (hw ? m['tapeAway$'] : m['tapeHome$']) || 0; mlWinStake = (hw ? m['tapeHome$'] : m['tapeAway$']) || 0; paid = prof(mlWinStake, hw ? m.homeAsk : m.awayAsk); }
  const st = (s['tapeFav$'] || 0) + (s['tapeDog$'] || 0); let spTook = null, spPaid = null;
  if (s.favCovered != null && st) { spTook = (s.favCovered ? s['tapeDog$'] : s['tapeFav$']) || 0; spWinStake = (s.favCovered ? s['tapeFav$'] : s['tapeDog$']) || 0; spPaid = prof(spWinStake, s.favCovered ? s.favAsk : s.dogAsk); }
  const favSh = st ? (s['tapeFav$'] || 0) / st : null;
  return { r, xs, picks, tot, awaySh, favP, took, paid, spTook, spPaid, mlWinStake, spWinStake, st, favSh, best: picks.length ? VRANK[picks[0].v] : 0 };
}
let sortKey = 'time', sortDir = 1;
const HEAD = [['time', 'Game'], ['ml', 'Moneyline <span class="tm">Robinhood · Pinnacle fair</span>'], ['spread', 'Spread'], ['total', 'Total'], ['spcrowd', 'Crowd $ on the spread'], ['crowd', 'Crowd $ on the moneyline'], ['book', 'Book took / paid'], ['pick', 'Our pick'], ['res', 'Result']];
const sval = g => ({ time: g.r.time + g.r.away, ml: g.favP, spread: (g.r.spread || {}).line, total: (g.r.total || {}).line, crowd: g.tot || null, spcrowd: g.st || null, book: g.took == null ? null : g.took - g.paid, pick: g.best, res: g.r.final ? 1 : 0 })[sortKey];
const cmp = (a, b) => { const A = sval(a), B = sval(b); if (A == null && B == null) return 0; if (A == null) return 1; if (B == null) return -1; return (A > B ? 1 : A < B ? -1 : 0) * sortDir; };
document.addEventListener('click', e => { const th = e.target.closest('th[data-k]'); if (!th || !th.closest('#tG')) return;
  const k = th.dataset.k; if (k === sortKey) sortDir = -sortDir; else { sortKey = k; sortDir = k === 'time' ? 1 : -1; } render(); });
function rowHtml(g){ const r = g.r, m = r.ml || {}, s = r.spread || {}, t = r.total || {};
  const mlCell = (m.awayAsk || m.homeAsk) ? `<b>${r.away}</b> ${odds(m.awayAsk)} · <b>${r.home}</b> ${odds(m.homeAsk)}` + (m.pinAway != null ? `<br><span class="tm">fair ${pct(m.pinAway)} / ${pct(m.pinHome)}</span>` : '') : '<span class="tm">—</span>';
  const spCell = s.fav ? `<b>${s.fav} −${s.line}</b> ${cents(s.favAsk)}<br><span class="tm">${s.dog} +${s.line} ${cents(s.dogAsk)}</span>` : '<span class="tm">—</span>';
  const toCell = t.line != null ? `<b>${t.line}</b><br><span class="tm">O ${cents(t.overAsk)} · U ${cents(t.underAsk)}</span>` : '<span class="tm">—</span>';
  const crowd = g.awaySh == null ? '<span class="tm">—</span>' : `<span class="split"><i style="width:${Math.round(g.awaySh * 100)}%"></i></span><br><b>${r.away}</b> ${Math.round(g.awaySh * 100)}% <span class="tm">${money(m['tapeAway$'] || 0)}</span> · <b>${r.home}</b> ${100 - Math.round(g.awaySh * 100)}% <span class="tm">${money(m['tapeHome$'] || 0)}</span><br><span class="tm">total ${money(g.tot)}</span>`;
  // spread crowd: share and $ on each side, oriented like the moneyline bar (left = away, right = home)
  // so a team keeps the same color in both columns; heavy side (65%+) flagged
  const fs = g.favSh, heavy = fs == null || g.st < 25000 ? null : fs >= .65 ? s.fav : fs <= .35 ? s.dog : null;
  const awayFav = s.fav === r.away, aSh = fs == null ? null : (awayFav ? fs : 1 - fs);
  const aSide = awayFav ? `${s.fav} −${s.line}` : `${s.dog} +${s.line}`, hSide = awayFav ? `${s.dog} +${s.line}` : `${s.fav} −${s.line}`;
  const aUsd = (awayFav ? s['tapeFav$'] : s['tapeDog$']) || 0, hUsd = (awayFav ? s['tapeDog$'] : s['tapeFav$']) || 0;
  const spCrowd = fs == null ? '<span class="tm">—</span>' : `<span class="split"><i style="width:${Math.round(aSh * 100)}%"></i></span><br><b>${aSide}</b> ${Math.round(aSh * 100)}% <span class="tm">${money(aUsd)}</span> · <b>${hSide}</b> ${100 - Math.round(aSh * 100)}% <span class="tm">${money(hUsd)}</span><br><span class="tm">total ${money(g.st)}${g.st < 25000 ? ' · thin, not readable yet' : ''}</span>${heavy ? ` <span class="hv">crowd heavy on ${heavy}</span>` : ''}`;
  const pick = g.picks.length ? g.picks.map(x => `${chip(x.v)} <b>${pickText(x)}</b> <span class="tm">${cents(x.ask)}</span> ${resMark(x)}<br><span class="why">${x.why}</span>`).join('<br>') : '<span class="tm">no bet</span>';
  const res = r.final ? `<b>${r.finalAway}-${r.finalHome}</b>` : '<span class="tm">—</span>';
  const book = g.took == null && g.spTook == null ? `<span class="tm">${r.final ? '—' : 'after the game'}</span>` :
    (g.took != null ? `<span class="tm">ML</span> <span class="pos" title="crowd money on the losing team">took ${money(g.took)}</span> · <span class="neg" title="the winners staked ${money(g.mlWinStake)} and were paid this profit at their price">paid ${money(g.paid)}</span> = <b class="${g.took - g.paid >= 0 ? 'pos' : 'neg'}">${g.took - g.paid >= 0 ? '+' : '−'}${money(Math.abs(g.took - g.paid))}</b>` : '') +
    (g.spTook != null ? `<br><span class="tm">spread</span> <span class="pos">took ${money(g.spTook)}</span> · <span class="neg" title="the winners staked ${money(g.spWinStake)}">paid ${money(g.spPaid)}</span> = <b class="${g.spTook - g.spPaid >= 0 ? 'pos' : 'neg'}">${g.spTook - g.spPaid >= 0 ? '+' : '−'}${money(Math.abs(g.spTook - g.spPaid))}</b>` : '');
  return `<tr class="${g.picks.length ? 'haspick' : ''}"><td><span class="nm">${r.away} @ ${r.home}</span><br><span class="tm">${when(r.time)}</span></td><td>${mlCell}</td><td>${spCell}</td><td>${toCell}</td><td>${spCrowd}</td><td>${crowd}</td><td>${book}</td><td>${pick}</td><td>${res}</td></tr>`; }
function render(){
  const games = (DAYS[day] || []).map(game);
  const hide = $('#hidepass').checked, list = games.filter(g => !hide || g.picks.length).sort(cmp);
  $('#tG').innerHTML = '<tr>' + HEAD.map(([k, l]) => `<th data-k="${k}" style="cursor:pointer">${l}${k === sortKey ? (sortDir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr>' +
    (list.map(rowHtml).join('') || `<tr><td colspan="9" class="tm" style="text-align:center;padding:14px">${hide ? 'no picks on this day' : 'nothing yet: Robinhood posts NBA lines the day before'}</td></tr>`);
  const picks = games.flatMap(g => g.picks).sort((a, b) => VRANK[b.v] - VRANK[a.v] || (a.r.time < b.r.time ? -1 : 1));
  $('#picks').innerHTML = picks.length ? picks.map(x => `<div class="pk">${chip(x.v)} <b>${pickText(x)}</b> <span class="tm">${cents(x.ask)} ${amer(x.ask)}</span> ${resMark(x)}<div class="tm">${x.r.away} @ ${x.r.home} · ${when(x.r.time)}</div><div class="why">${x.why}</div></div>`).join('')
    : '<div class="tm" style="padding:8px 2px">No picks today. Both rules need each team\'s earlier games this season, so most early-season days are quiet. That is the rules working, not missing.</div>';
  renderSpreads();
  const tk = games.reduce((a, g) => a + (g.took || 0) + (g.spTook || 0), 0), pd = games.reduce((a, g) => a + (g.paid || 0) + (g.spPaid || 0), 0), anyF = games.some(g => g.took != null || g.spTook != null);
  $('#kpi').innerHTML = `<div>games<b>${games.length}</b></div><div>bets<b>${picks.filter(x => x.v.endsWith('BET')).length}</b></div><div>leans<b>${picks.filter(x => x.v === 'LEAN').length}</b></div><div>final<b>${games.filter(g => g.r.final).length}</b></div>` +
    (anyF ? `<div title="crowd money on losing sides (moneyline + spread) on finished games">book took<b class="pos">${money(tk)}</b></div><div title="profit paid to the winning sides at their prices">book paid<b class="neg">${money(pd)}</b></div><div title="took minus paid">book net<b class="${tk - pd >= 0 ? 'pos' : 'neg'}">${tk - pd >= 0 ? '+' : '−'}${money(Math.abs(tk - pd))}</b></div>` : '');
}
// ---- Spreads tab: both sides of every spread, with the crowd's money on each ----
let spKey = 'game', spDir = 1;
const SPHEAD = [['game', 'Game', ''], ['side', 'Side', ''], ['ask', 'Robinhood ask', 'num'], ['fair', 'Pinnacle fair', 'num'], ['edge', 'Edge', 'num'], ['crowd', 'Crowd share', 'num'], ['own', '$ on side', 'num'], ['tape', 'Total $', 'num'], ['book', 'Book', 'num'], ['v', 'Verdict', ''], ['hit', 'Result', '']];
const spVal = x => ({ game: x.r.time + x.r.away + (x.fav ? 0 : 1), side: x.side, ask: x.ask, fair: x.fair, edge: x.edge, crowd: x.crowd, own: x.tape ? x.own : null, tape: x.tape || null, book: x.hit == null || !x.tape ? null : (x.hit ? -x.own : x.own), v: VRANK[x.v] ?? 0, hit: x.hit })[spKey];
const spCmp = (a, b) => { const A = spVal(a), B = spVal(b); if (A == null && B == null) return 0; if (A == null) return 1; if (B == null) return -1; return (A > B ? 1 : A < B ? -1 : 0) * spDir; };
document.addEventListener('click', e => { const th = e.target.closest('th[data-s]'); if (!th) return;
  const k = th.dataset.s; if (k === spKey) spDir = -spDir; else { spKey = k; spDir = (k === 'game' || k === 'side') ? 1 : -1; } renderSpreads(); });
function renderSpreads(){
  const hide = $('#hidepass').checked;
  const xs = (DAYS[day] || []).flatMap(sides).filter(x => x.kind === 'spread' && (!hide || x.v !== 'PASS')).sort(spCmp);
  $('#tSp').innerHTML = '<tr>' + SPHEAD.map(([k, l, c]) => `<th class="${c}" data-s="${k}" style="cursor:pointer">${l}${k === spKey ? (spDir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr>' +
    (xs.map(x => { const r = x.r, res = x.hit == null ? (r.final ? '<span class="res d">push</span>' : '<span class="tm">—</span>') : x.v === 'PASS' ? `<span class="res d">${x.hit ? 'covered' : 'missed'} (no bet)</span>` : x.hit ? '<span class="res y">✓</span>' : '<span class="res n">✗</span>';
      return `<tr class="${x.v !== 'PASS' ? 'haspick' : ''}${x.fav ? ' fv' : ''}"><td><span class="nm">${r.away} @ ${r.home}</span><br><span class="tm">${when(r.time)}${r.final ? ' · ' + r.finalAway + '-' + r.finalHome : ''}</span></td><td class="nm">${x.side}</td>
      <td class="num">${odds(x.ask)}</td><td class="num">${pct(x.fair)}</td><td class="num ${x.edge == null ? '' : x.edge >= 2 ? 'pos' : x.edge <= -2 ? 'neg' : ''}">${x.edge == null ? '—' : (x.edge >= 0 ? '+' : '') + x.edge.toFixed(1)}</td>
      <td class="num"><span class="bar"><i style="width:${x.crowd == null ? 0 : x.crowd * 100}%"></i></span> ${pct(x.crowd)}</td><td class="num">${x.tape ? money(x.own) : '—'}</td><td class="num">${money(x.tape)}</td>
      <td class="num">${x.hit == null || !x.tape ? '<span class="tm">—</span>' : x.hit ? `<span class="neg" title="the crowd staked ${money(x.own)} on this side and was paid its profit at ${cents(x.ask)}">paid ${money(x.ask ? x.own * (1 - x.ask) / x.ask : x.own)}</span>` : `<span class="pos" title="the book kept the crowd's money on this side">took ${money(x.own)}</span>`}</td>
      <td>${chip(x.v)}${x.why ? '<br><span class="why">' + x.why + '</span>' : ''}</td><td>${res}</td></tr>`; }).join('') ||
     '<tr><td colspan="11" class="tm" style="text-align:center;padding:14px">no spreads yet: Robinhood posts NBA lines the day before</td></tr>');
}
// tabs live in the nav bar (Games / Spreads / Scorecard); the hash keeps the tab on reload
let tab = ['board', 'spread', 'score'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'board';
function showTab(t){ tab = t; document.querySelectorAll('nav.nb .pg a[data-nt]').forEach(a => a.classList.toggle('on', a.dataset.nt === t));
  $('#vBoard').style.display = t === 'board' ? '' : 'none'; $('#vSpread').style.display = t === 'spread' ? '' : 'none'; $('#vScore').style.display = t === 'score' ? '' : 'none';
  $('#dayview').style.display = t === 'score' ? 'none' : ''; }
document.querySelectorAll('nav.nb .pg a[data-nt]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); history.replaceState(null, '', '#' + a.dataset.nt); showTab(a.dataset.nt); }));
showTab(tab);
$('#hidepass').addEventListener('input', render);
// ---- scorecard: every graded side across every day ----
const G = Object.values(DAYS).flat().flatMap(sides).filter(x => x.hit != null && x.ask);
const strat = {
  'Spread BET: won last by 18+, and opponent won its last or it is the underdog': G.filter(x => x.kind === 'spread' && x.blow),
  '   of which STRONG (both)': G.filter(x => x.kind === 'spread' && x.v === 'STRONG BET'),
  'PASS now: won last by 18+, favored, opponent lost its last (old BET)': G.filter(x => x.kind === 'spread' && x.blowFav),
  'Moneyline LEAN: same blowout team': G.filter(x => x.kind === 'ml' && x.blow),
  'LEAN: better team (season margin +4/game) priced as underdog, moneyline': G.filter(x => x.kind === 'ml' && x.under),
  '   same, spread (not a pick)': G.filter(x => x.kind === 'spread' && x.under),
  'LEAN: underdog getting 10-12.5 points': G.filter(x => x.kind === 'spread' && x.bigDog),
  'Tracked: follow a 2¢+ line move toward the underdog': G.filter(x => x.kind === 'spread' && x.toDog),
  'Total LEAN: under when the total is below 220': G.filter(x => x.kind === 'total' && x.v === 'LEAN'),
  'Spread: side with LESS of the crowd $ (NFL rule, break-even last season)': G.filter(x => x.kind === 'spread' && x.crowd != null && x.tape >= 25000 && x.crowd < 0.5),
  'Spread: side with MORE of the crowd $': G.filter(x => x.kind === 'spread' && x.crowd != null && x.tape >= 25000 && x.crowd >= 0.5),
  'Spread: every favorite': G.filter(x => x.kind === 'spread' && x.fav), 'Spread: every underdog': G.filter(x => x.kind === 'spread' && !x.fav),
  'Moneyline: Robinhood 3+ pts under Pinnacle (untested)': G.filter(x => x.kind === 'ml' && x.edge != null && x.edge >= 3),
  'Moneyline: team with less of the crowd $': G.filter(x => x.kind === 'ml' && x.crowd != null && x.tape >= 25000 && x.crowd < 0.5),
  'Moneyline: every favorite': G.filter(x => x.kind === 'ml' && x.fav), 'Moneyline: every underdog': G.filter(x => x.kind === 'ml' && !x.fav),
  'Total: the crowd side': G.filter(x => x.kind === 'total' && x.crowd != null && x.tape >= 10000 && x.crowd > 0.5), 'Total: every over': G.filter(x => x.kind === 'total' && x.side.startsWith('Over')),
};
const SC = Object.entries(strat).map(([n, b], i) => { const w = b.filter(x => x.hit).length, u = b.reduce((s, x) => s + (x.hit ? 1 / x.ask - 1 : -1), 0);
  return { i, n, bets: b.length, w, l: b.length - w, units: b.length ? u : null, roi: b.length ? u / b.length : null, win: b.length ? w / b.length : null }; });
let scKey = 'i', scDir = 1;
const SCHEAD = [['n', 'Strategy (1u each at the Robinhood ask)', ''], ['bets', 'Bets', 'num'], ['win', 'Record', 'num'], ['units', 'Units', 'num'], ['roi', 'ROI', 'num']];
function renderScore(){
  const rows = SC.slice().sort((a, b) => { const A = a[scKey], B = b[scKey]; if (A == null && B == null) return a.i - b.i; if (A == null) return 1; if (B == null) return -1; return (A > B ? 1 : A < B ? -1 : 0) * scDir || a.i - b.i; });
  $('#score').innerHTML = '<div class="wrap"><table class="lt" id="tSc"><thead><tr>' + SCHEAD.map(([k, l, c]) => `<th class="${c}" data-c="${k}" style="cursor:pointer">${l}${k === scKey ? (scDir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr></thead><tbody>' +
    rows.map(x => `<tr><td class="nm">${x.n}</td><td class="num">${x.bets}</td><td class="num">${x.w}-${x.l}</td><td class="num ${x.units == null ? '' : x.units >= 0 ? 'pos' : 'neg'}">${x.units == null ? '—' : (x.units >= 0 ? '+' : '') + x.units.toFixed(1) + 'u'}</td><td class="num">${x.roi == null ? '—' : Math.round(x.roi * 100) + '%'}</td></tr>`).join('') + '</tbody></table></div>';
}
document.addEventListener('click', e => { const th = e.target.closest('#tSc th[data-c]'); if (!th) return; const k = th.dataset.c;
  if (k === scKey) scDir = -scDir; else { scKey = k; scDir = k === 'n' ? 1 : -1; } renderScore(); });
renderScore();
render();
"""

def page():
    from navbar import navbar, day_label
    nav = navbar('nba', '', {'mlb': [], 'nfl': [], 'nba': [(d, day_label(d), '') for d in order]}, {'nba': cur}, fixed='nba')
    return f"""<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fade The Chalk</title>{FONTS}{CSS}<header><h1><a href="index.html">FADE THE <span>CHALK</span></a></h1><div class="sub">NBA · moneyline, spread, total · Robinhood vs Pinnacle · crowd money by side · built {datetime.datetime.now().isoformat(timespec="minutes")}</div></header>{nav}
<style>h2.mk{{margin:16px 0 8px}}
#picks{{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:8px;margin:6px 0 14px}}
.pk{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:9px 11px;line-height:1.5}}
.why{{font-size:12px;color:var(--mute)}}
#tG td{{vertical-align:top;line-height:1.45}} #tG tr.haspick td,#tSp tr.haspick td{{background:rgba(46,160,90,.06)}}
#tSp tr.fv td{{border-top:2px solid var(--line)}}
.pt{{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 8px}}.pt button{{background:var(--panel);color:var(--mute);border:1px solid var(--line);border-radius:999px;padding:6px 16px;font:700 13px var(--font);cursor:pointer}}.pt button.on{{color:var(--ink);border-color:var(--acc)}}
.hv{{display:inline-block;font-size:11px;font-weight:700;color:var(--warn);border:1px solid var(--warn);border-radius:4px;padding:0 5px;margin-top:2px}}
.split{{display:inline-block;width:110px;height:7px;border-radius:4px;background:var(--blue);overflow:hidden;vertical-align:middle}}.split i{{display:block;height:100%;background:var(--acc)}}</style><div class="panel top">
<div id="dayview"><div class="kpi" id="kpi"></div>
<h2 class="mk">Today's picks</h2><div id="picks"></div>
<div class="ctl"><label><input type="checkbox" id="hidepass"> show only picks</label> <span class="tm">click a column to sort, again to flip</span></div></div>
<div id="vBoard"><div class="wrap"><table class="lt" id="tG"></table></div>
<div class="legend">One row per game. <b>Moneyline</b> = what a $1 Robinhood contract on each team costs (Robinhood's NBA contracts are Kalshi's), with the American odds, and Pinnacle's de-vigged fair chance under it. <b>Spread</b> = the favorite's line and price, the underdog's under it. <b>Crowd $ on the spread</b> = how the crowd's taker dollars split between the favorite and the underdog at Kalshi's main line (left bar = away team, same as the moneyline bar, so each team keeps its color), with the dollars on each; "crowd heavy" marks 65%+ on one side once $25k+ is in. <b>Crowd $ on the moneyline</b> = the same for who wins (left bar = away team). Both frozen at tip-off. Each pre-game trade is credited to the side the bettor actually backed. <b>Book took / paid</b> = once the game is final: <i>took</i> = the crowd's money on the losing side (all of it is lost); <i>paid</i> = the profit the winning side was paid at its price (the dollars on the winner x (1 - price) / price, so $102k on a 61¢ / −156 favorite is paid about $65k, not $102k); then the book's net. Robinhood/Kalshi is an exchange, so the 'book' is really the other side of each trade; the math is the same.</div>
</div>
<div id="vSpread" style="display:none"><div class="wrap"><table class="lt" id="tSp"></table></div>
<div class="legend">Both sides of every spread. <b>Robinhood ask</b> = what a $1 contract on that side costs. <b>Pinnacle fair</b> = the sharpest book's de-vigged chance at the same line; <b>Edge</b> = fair minus ask, in points. <b>Crowd share</b> / <b>$ on side</b> = how much of the crowd's taker money (each pre-game trade credited to the side the bettor backed) is on that side, frozen at tip-off. Crowd money alone was break-even on NBA spreads last season, so it's information, not a pick.</div></div>
<div id="vScore" style="display:none"><h2 style="margin:4px 0 8px">Scorecard <small>every graded NBA game · click a column to sort</small></h2><div id="score"></div>
<div class="legend"><b>Rules, re-tested Oct 30</b> on all of last season (1,306 games) and checked against this season. Last season's spreads are graded against the line implied by Kalshi's closing moneyline (it matches Pinnacle's line within half a point), at a 51¢ ask plus the fee. An older test used spread lines picked partly by in-game trading, which flattered several rules; those numbers are replaced below.<br>
<b>BET</b> on a spread = the team that <i>won its last game by 18+</i>, when its opponent also won its last game <i>or</i> it is the underdog: covered 62% (+18%), 61% and 63% in the two halves of the season, 8-2 so far this season. The market prices in a letdown after a blowout that doesn't come.
<b>STRONG BET</b> = both (opponent won its last <i>and</i> it is the underdog). If <i>both</i> teams qualify, only the underdog is the bet (16-9 vs 9-16 for the favorite). <b>No longer a bet:</b> the blowout team favored against an opponent that lost its last game (48% last season, 0-4 this season).
<b>LEAN</b> on a moneyline = the same blowout team (+15%). <b>LEAN</b> on a moneyline = <i>the better team priced as the underdog</i>: its season point differential is 4+ points a game better than its opponent's (5+ games each): +33% on 47 games, both halves (only +5% on the spread, so it's the moneyline). <b>LEAN</b> on a spread = <i>the underdog getting 10-12.5 points</i>: 57% both halves (+8%); smaller and bigger underdogs didn't cover. <b>LEAN</b> on a total = the under below 220: not confirmed (last season's totals data isn't reliable), so keep it small.
<b>Dropped:</b> fading a line move. On clean prices, fading a 3¢+ move in the last 6 hours covered only 43%; following the move did better (57%), best when it moves toward an underdog that stays the underdog. That one is tracked on the scorecard, not a pick yet.
What did <i>not</i> work: the crowd's money of any kind (moneyline or spread, big or small bets, early or late), back-to-backs and rest, win or losing streaks, home/road. The rule needs each team's previous game, so it starts with each team's second game. Regular season only: in the playoffs it was flat.</div>
</div>
</div>
<script>const DAYS = {jd(days)}; const CUR = {jd(cur)};{JS}</script>"""

open(os.path.join(SITE, 'nba.html'), 'w', encoding='utf-8', newline='\n').write(page())   # written even before the first game, so the nav link never 404s
print(f"nba.html: {len(order)} days, showing {cur}: {len(days.get(cur, []))} games")
