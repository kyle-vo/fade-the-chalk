"""Render docs/nba.html from backtest/nba_<date>.json (written by nba.py): moneyline, spread and total for each NBA game, Robinhood's ask vs Pinnacle's
fair price, the crowd's money on each side (Kalshi trade tape), results, and a scorecard.
Rules come from last season (research/nba_hist_2025.json: 1,086 regular-season games at Kalshi's tip-off price):
  spread BET   = the team that won its last game by 20+ (58% covered, +14%; +10% Oct-Jan, +18% Feb-Apr). STRONG when its opponent also won its last game.
  ML LEAN      = the same team on the moneyline (+8%: +12% / +4%). The spread is the better bet.
  total LEAN   = under when the total is below 220 (+18% on 74 games: small).
The NFL crowd-fade rule (less of the spread money) was break-even on NBA spreads (+0.6% on 1,128), so it is tracked on the scorecard only."""
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
    // last season (1,086 games at Kalshi's tip-off price): the team coming off a 20+ point win covered 58% (+14%), both halves of the season.
    // The market expects a letdown that doesn't come. STRONG when its opponent also won its last game (+23%, smaller sample).
    const home = x.team === r.home, last = x.team ? (home ? r.homeLast : r.awayLast) : null, oppLast = x.team ? (home ? r.awayLast : r.homeLast) : null;
    x.last = last; x.blow = last != null && last >= 20;
    x.v = 'PASS';
    if (x.kind === 'spread' && x.blow) x.v = oppLast != null && oppLast > 0 ? 'STRONG BET' : 'BET';
    if (x.kind === 'ml' && x.blow) x.v = 'LEAN';
    // the better team (season point differential 4+ per game above its opponent's, 5+ games each) priced as the UNDERDOG: last season
    // +39% on the moneyline and +22% on the spread, both halves of the season, stronger as the gap grows, but only ~57 games a season
    const myM = home ? r.homeMargin : r.awayMargin, opM = home ? r.awayMargin : r.homeMargin, gpOk = Math.min(r.homeGp || 0, r.awayGp || 0) >= 5;
    x.under = x.team && gpOk && myM != null && opM != null && myM - opM >= 4 && !x.fav && (x.kind === 'ml' || x.kind === 'spread');
    if (x.under && x.v === 'PASS') x.v = 'LEAN';
    if (x.kind === 'total' && x.side.startsWith('Under') && r.total && r.total.line < 220) x.v = 'LEAN';
    x.why = [x.blow ? `${x.team} won its last game by ${last}` + (x.v === 'STRONG BET' ? ', and its opponent won its last too' : '') : '',
             x.under ? `the better team (${myM >= 0 ? '+' : ''}${myM} vs ${opM >= 0 ? '+' : ''}${opM} per game) priced as the underdog` : '',
             x.v === 'LEAN' && x.kind === 'total' ? 'total under 220' : ''].filter(Boolean).join(' · '); }
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
  return { r, xs, picks, tot, awaySh, favP, best: picks.length ? VRANK[picks[0].v] : 0 };
}
let sortKey = 'time', sortDir = 1;
const HEAD = [['time', 'Game'], ['ml', 'Moneyline <span class="tm">Robinhood · Pinnacle fair</span>'], ['spread', 'Spread'], ['total', 'Total'], ['crowd', 'Crowd $ on the moneyline'], ['pick', 'Our pick'], ['res', 'Result']];
const sval = g => ({ time: g.r.time + g.r.away, ml: g.favP, spread: (g.r.spread || {}).line, total: (g.r.total || {}).line, crowd: g.tot || null, pick: g.best, res: g.r.final ? 1 : 0 })[sortKey];
const cmp = (a, b) => { const A = sval(a), B = sval(b); if (A == null && B == null) return 0; if (A == null) return 1; if (B == null) return -1; return (A > B ? 1 : A < B ? -1 : 0) * sortDir; };
document.addEventListener('click', e => { const th = e.target.closest('th[data-k]'); if (!th || !th.closest('#tG')) return;
  const k = th.dataset.k; if (k === sortKey) sortDir = -sortDir; else { sortKey = k; sortDir = k === 'time' ? 1 : -1; } render(); });
function rowHtml(g){ const r = g.r, m = r.ml || {}, s = r.spread || {}, t = r.total || {};
  const mlCell = (m.awayAsk || m.homeAsk) ? `<b>${r.away}</b> ${odds(m.awayAsk)} · <b>${r.home}</b> ${odds(m.homeAsk)}` + (m.pinAway != null ? `<br><span class="tm">fair ${pct(m.pinAway)} / ${pct(m.pinHome)}</span>` : '') : '<span class="tm">—</span>';
  const spCell = s.fav ? `<b>${s.fav} −${s.line}</b> ${cents(s.favAsk)}<br><span class="tm">${s.dog} +${s.line} ${cents(s.dogAsk)}</span>` : '<span class="tm">—</span>';
  const toCell = t.line != null ? `<b>${t.line}</b><br><span class="tm">O ${cents(t.overAsk)} · U ${cents(t.underAsk)}</span>` : '<span class="tm">—</span>';
  const crowd = g.awaySh == null ? '<span class="tm">—</span>' : `<span class="split"><i style="width:${Math.round(g.awaySh * 100)}%"></i></span><br><span class="tm">${r.away} ${Math.round(g.awaySh * 100)}% · ${r.home} ${100 - Math.round(g.awaySh * 100)}% · ${money(g.tot)}</span>`;
  const pick = g.picks.length ? g.picks.map(x => `${chip(x.v)} <b>${pickText(x)}</b> <span class="tm">${cents(x.ask)}</span> ${resMark(x)}<br><span class="why">${x.why}</span>`).join('<br>') : '<span class="tm">no bet</span>';
  const res = r.final ? `<b>${r.finalAway}-${r.finalHome}</b>` : '<span class="tm">—</span>';
  return `<tr class="${g.picks.length ? 'haspick' : ''}"><td><span class="nm">${r.away} @ ${r.home}</span><br><span class="tm">${when(r.time)}</span></td><td>${mlCell}</td><td>${spCell}</td><td>${toCell}</td><td>${crowd}</td><td>${pick}</td><td>${res}</td></tr>`; }
function render(){
  const games = (DAYS[day] || []).map(game);
  const hide = $('#hidepass').checked, list = games.filter(g => !hide || g.picks.length).sort(cmp);
  $('#tG').innerHTML = '<tr>' + HEAD.map(([k, l]) => `<th data-k="${k}" style="cursor:pointer">${l}${k === sortKey ? (sortDir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr>' +
    (list.map(rowHtml).join('') || `<tr><td colspan="7" class="tm" style="text-align:center;padding:14px">${hide ? 'no picks on this day' : 'nothing yet: Robinhood posts NBA lines the day before'}</td></tr>`);
  const picks = games.flatMap(g => g.picks).sort((a, b) => VRANK[b.v] - VRANK[a.v] || (a.r.time < b.r.time ? -1 : 1));
  $('#picks').innerHTML = picks.length ? picks.map(x => `<div class="pk">${chip(x.v)} <b>${pickText(x)}</b> <span class="tm">${cents(x.ask)} ${amer(x.ask)}</span> ${resMark(x)}<div class="tm">${x.r.away} @ ${x.r.home} · ${when(x.r.time)}</div><div class="why">${x.why}</div></div>`).join('')
    : '<div class="tm" style="padding:8px 2px">No picks today. Both rules need each team\'s earlier games this season, so most early-season days are quiet. That is the rules working, not missing.</div>';
  $('#kpi').innerHTML = `<div>games<b>${games.length}</b></div><div>bets<b>${picks.filter(x => x.v.endsWith('BET')).length}</b></div><div>leans<b>${picks.filter(x => x.v === 'LEAN').length}</b></div><div>final<b>${games.filter(g => g.r.final).length}</b></div>`;
}
$('#hidepass').addEventListener('input', render);
// ---- scorecard: every graded side across every day ----
const G = Object.values(DAYS).flat().flatMap(sides).filter(x => x.hit != null && x.ask);
const strat = {
  'Spread BET: team that won its last game by 20+': G.filter(x => x.kind === 'spread' && x.blow),
  '   of which STRONG (opponent also won its last)': G.filter(x => x.kind === 'spread' && x.v === 'STRONG BET'),
  'Moneyline LEAN: same blowout team': G.filter(x => x.kind === 'ml' && x.blow),
  'LEAN: better team (season margin +4/game) priced as underdog, moneyline': G.filter(x => x.kind === 'ml' && x.under),
  'LEAN: same, spread': G.filter(x => x.kind === 'spread' && x.under),
  'Total LEAN: under when the total is below 220': G.filter(x => x.kind === 'total' && x.v === 'LEAN'),
  'Spread: side with LESS of the crowd $ (NFL rule, break-even last season)': G.filter(x => x.kind === 'spread' && x.crowd != null && x.tape >= 25000 && x.crowd < 0.5),
  'Spread: side with MORE of the crowd $': G.filter(x => x.kind === 'spread' && x.crowd != null && x.tape >= 25000 && x.crowd >= 0.5),
  'Spread: every favorite': G.filter(x => x.kind === 'spread' && x.fav), 'Spread: every underdog': G.filter(x => x.kind === 'spread' && !x.fav),
  'Moneyline: Robinhood 3+ pts under Pinnacle (untested)': G.filter(x => x.kind === 'ml' && x.edge != null && x.edge >= 3),
  'Moneyline: team with less of the crowd $': G.filter(x => x.kind === 'ml' && x.crowd != null && x.tape >= 25000 && x.crowd < 0.5),
  'Moneyline: every favorite': G.filter(x => x.kind === 'ml' && x.fav), 'Moneyline: every underdog': G.filter(x => x.kind === 'ml' && !x.fav),
  'Total: the crowd side': G.filter(x => x.kind === 'total' && x.crowd != null && x.tape >= 10000 && x.crowd > 0.5), 'Total: every over': G.filter(x => x.kind === 'total' && x.side.startsWith('Over')),
};
$('#score').innerHTML = '<div class="wrap"><table class="lt"><thead><tr><th>Strategy (1u each at the Robinhood ask)</th><th class="num">Bets</th><th class="num">Record</th><th class="num">Units</th><th class="num">ROI</th></tr></thead><tbody>' +
  Object.entries(strat).map(([n, b]) => { const w = b.filter(x => x.hit).length, u = b.reduce((s, x) => s + (x.hit ? 1 / x.ask - 1 : -1), 0);
    return `<tr><td class="nm">${n}</td><td class="num">${b.length}</td><td class="num">${w}-${b.length - w}</td><td class="num ${u >= 0 ? 'pos' : 'neg'}">${b.length ? (u >= 0 ? '+' : '') + u.toFixed(1) + 'u' : '—'}</td><td class="num">${b.length ? Math.round(u / b.length * 100) + '%' : '—'}</td></tr>`; }).join('') + '</tbody></table></div>';
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
#tG td{{vertical-align:top;line-height:1.45}} #tG tr.haspick td{{background:rgba(46,160,90,.06)}}
.split{{display:inline-block;width:110px;height:7px;border-radius:4px;background:var(--blue);overflow:hidden;vertical-align:middle}}.split i{{display:block;height:100%;background:var(--acc)}}</style><div class="panel top">
<div class="kpi" id="kpi"></div>
<h2 class="mk">Today's picks</h2><div id="picks"></div>
<div class="ctl"><label><input type="checkbox" id="hidepass"> show only games with a pick</label> <span class="tm">click a column to sort</span></div>
<div class="wrap"><table class="lt" id="tG"></table></div>
<div class="legend">One row per game. <b>Moneyline</b> = what a $1 Robinhood contract on each team costs (Robinhood's NBA contracts are Kalshi's), with the American odds, and Pinnacle's de-vigged fair chance under it. <b>Spread</b> = the favorite's line and price, the underdog's under it. <b>Crowd $</b> = how the crowd's taker dollars split on the moneyline (left bar = away team), frozen at tip-off.
<b>Rules, tested on all of last season</b> (1,086 regular-season games, Kalshi's price at tip plus the fee):
<b>BET</b> on a spread = the team that <i>won its last game by 20+</i>. It covered 58% (+14%), and held in both halves of the season (+10% Oct-Jan, +18% Feb-Apr) and across favorites, underdogs, home and road. The market prices in a letdown after a blowout that doesn't come.
<b>STRONG BET</b> = the same, when its opponent also won its last game (+23%, about 125 games).
<b>LEAN</b> on a moneyline = the same team (+8%; the spread pays better). <b>LEAN</b> on a moneyline or spread also = <i>the better team priced as the underdog</i>: its season point differential is 4+ points a game better than its opponent's (5+ games each), yet it's the underdog. Last season: +39% on the moneyline, +22% on the spread, both halves of the season, and stronger as the gap grew, but only about 57 games all season, so it's a LEAN. <b>LEAN</b> on a total = the under when the total is below 220 (+18%, only 74 games).
What did <i>not</i> work last season: fading the crowd's spread money (the NFL rule, +0.6% on 1,128 games), the crowd's moneyline money, back-to-backs, win streaks, home/road. The rule needs each team's previous game, so it starts with each team's second game. Regular season only: in the playoffs it was flat.</div>
<h2 style="margin-top:18px">Scorecard <small>every graded game</small></h2><div id="score"></div>
</div>
<script>const DAYS = {jd(days)}; const CUR = {jd(cur)};{JS}</script>"""

open(os.path.join(SITE, 'nba.html'), 'w', encoding='utf-8', newline='\n').write(page())   # written even before the first game, so the nav link never 404s
print(f"nba.html: {len(order)} days, showing {cur}: {len(days.get(cur, []))} games")
