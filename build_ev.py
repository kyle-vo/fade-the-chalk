"""Render docs/ev.html from backtest/ev_now.json (every price we can bet right now vs Pinnacle's fair) and backtest/ev_log.json (every side
flagged at +2% EV, with the closing fair and the result). Written by ev.py; this only grades and draws."""
import json, os, re, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); SITE = os.path.join(HERE, 'docs')
J = lambda p: json.load(open(p, encoding='utf-8'))
jd = lambda o: json.dumps(o, separators=(',', ':')).replace('</', '<' + chr(92) + '/')
src = open(os.path.join(HERE, 'build_site.py'), encoding='utf-8').read()
CSS = re.search(r'CSS = r"""(.*?)"""', src, re.S).group(1); FONTS = re.search(r"FONTS = '(.*?)'", src).group(1)
from ev import kfee, dec

now = J(os.path.join(BT, 'ev_now.json')) if os.path.exists(os.path.join(BT, 'ev_now.json')) else {'at': None, 'sides': []}
log = J(os.path.join(BT, 'ev_log.json')) if os.path.exists(os.path.join(BT, 'ev_log.json')) else {}

_cache = {}
def load(name):
    if name not in _cache:
        p = os.path.join(BT, name + '.json'); _cache[name] = J(p) if os.path.exists(p) else None
    return _cache[name]

def result(e):
    """1 won, 0 lost, None not graded / push"""
    if e['market'] == 'Prop':                                                  # NBA player props: graded from ESPN box scores (nbaprops.box_scores)
        box = load('nbabox_' + e['src'][-10:]) or {}
        v = (box.get(e.get('player')) or {}).get(e.get('stat'))
        return None if v is None or v == e.get('line') else int((v > e['line']) == bool(e.get('over')))
    if e['src'].startswith('ml_'):
        g = (load('mlres_' + e['src'][3:]) or {}).get(e['id'])
        return None if not g or g.get('homeWin') is None else int(g['homeWin'] == (1 if e.get('home') else 0))
    rows = load(e['src']) or []
    r = next((x for x in rows if str(x.get('gamePk') or x.get('eventId')) == e['id']), None)
    if not r: return None
    if e['market'] == 'ML':
        return None if r.get('homeWin') is None else int(r['homeWin'] == (1 if e.get('home') else 0))
    if e['market'] == 'Spread':
        c = (r.get('spread') or {}).get('favCovered')
        return None if c is None else int(c == (1 if e.get('fav') else 0))
    o = (r.get('total') or {}).get('over')
    return None if o is None else int(o == (1 if e['side'].startswith('Over') else 0))

def cost_and_payout(venue, price):
    """$ staked per contract (Kalshi incl. fee) and the profit per $1 staked if it wins"""
    if venue == 'Kalshi': c = price + kfee(price); return c, (1 - c) / c
    return 1.0, dec(price) - 1

plays = []
for k, e in log.items():
    c, win = cost_and_payout(e['venue'], e['price'])
    cf = e.get('closeFair'); clv = None if cf is None else (cf / c - 1 if e['venue'] == 'Kalshi' else cf * dec(e['price']) - 1)
    res = result(e) if datetime.datetime.fromisoformat(e['time'].replace('Z', '+00:00')) < datetime.datetime.now(datetime.timezone.utc) else None
    plays.append(dict(e, clv=None if clv is None else round(clv, 4), res=res, pl=None if res is None else round(win if res else -1, 4)))
plays.sort(key=lambda x: x['time'], reverse=True)
venues = sorted({x['venue'] for x in now['sides']} | {x['venue'] for x in plays}, key=lambda v: (v != 'Kalshi', v))

JS = r"""
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const LS = (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } };
const SV = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
const NAMES = { Kalshi: 'Kalshi', draftkings: 'DraftKings', fanduel: 'FanDuel', betmgm: 'BetMGM', betrivers: 'BetRivers', bovada: 'Bovada', betonlineag: 'BetOnline', fliff: 'Fliff', novig: 'Novig', prophetx: 'ProphetX', polymarket: 'Polymarket', polymarket_us: 'Polymarket US', williamhill_us: 'Caesars', espnbet: 'ESPN Bet', hardrockbet: 'Hard Rock', ballybet: 'Bally', betus: 'BetUS', lowvig: 'LowVig', mybookieag: 'MyBookie' };
const nm = v => NAMES[v] || v;
// ---- filter state (saved on this device)
const F = Object.assign({ books: VENUES.filter(v => ['Kalshi', 'novig', 'prophetx', 'bovada', 'betonlineag'].includes(v)), sports: ['NFL', 'NBA', 'MLB'], mkts: ['ML', 'Spread', 'Total', 'pts', 'reb', 'ast', '3PM'],
  minEv: 2, oddsMin: -400, oddsMax: 600, within: 'all', pinOnly: false, q: '', hideStarted: true, view: 'best', bank: 1000 }, LS('ftc_ev_f', {}));
const save = () => SV('ftc_ev_f', F);
// ---- prices: everything in American odds; Kalshi is the ask plus its taker fee
const dec = a => 1 + (a > 0 ? a / 100 : 100 / -a);
const kcost = p => p + 0.07 * p * (1 - p);
const decOf = x => x.venue === 'Kalshi' ? 1 / kcost(x.price) : dec(x.price);
const amer = d => d >= 2 ? '+' + Math.round((d - 1) * 100) : '−' + Math.round(100 / (d - 1));
const priceHtml = x => x.venue === 'Kalshi' ? `<b>${Math.round(x.price * 100)}¢</b> <span class="tm">${amer(decOf(x))}</span>` : `<b>${x.price > 0 ? '+' : '−'}${Math.abs(x.price)}</b>`;
const fairAmer = p => p > 0 && p < 1 ? amer(1 / p) : '—';
const evf = v => v == null ? '—' : `<span class="${v >= 0 ? 'pos' : 'neg'}">${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%</span>`;
const kelly = x => { const b = decOf(x) - 1, f = (x.fair * b - (1 - x.fair)) / b; return Math.max(0, f / 4); };
const mktOf = x => x.market === 'Prop' ? ((x.side.match(/ (pts|reb|ast|3PM)$/) || [])[1] || 'pts') : x.market;
const when = t => new Date(t).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
const until = t => { const m = Math.round((new Date(t) - Date.now()) / 60000); return m <= 0 ? 'started' : m < 60 ? m + 'm' : m < 1440 ? Math.floor(m / 60) + 'h ' + (m % 60) + 'm' : Math.floor(m / 1440) + 'd'; };
const betTxt = x => x.market === 'ML' ? x.side + ' ML' : x.side;
const note = x => [x.market === 'Prop' ? (x.fairSrc === 'pinnacle' ? 'vs Pinnacle' : 'vs sharp-book average') : '', x.pinLine != null ? 'alt line · Pinnacle ' + x.pinLine : ''].filter(Boolean).join(' · ');
const WITHIN = { '1h': 1, '3h': 3, '12h': 12, '24h': 24, all: 1e9 };
function pass(x, evBar){
  const d = decOf(x), am = d >= 2 ? (d - 1) * 100 : -100 / (d - 1), hrs = (new Date(x.time) - Date.now()) / 3600e3, q = F.q.trim().toLowerCase();
  return F.sports.includes(x.sport) && F.mkts.includes(mktOf(x)) && F.books.includes(x.venue) && (!evBar || x.ev * 100 >= F.minEv) && am >= F.oddsMin && am <= F.oddsMax &&
    hrs <= WITHIN[F.within] && (!F.hideStarted || hrs > 0) && (!F.pinOnly || x.market !== 'Prop' || x.fairSrc === 'pinnacle') && (!q || (x.game + ' ' + x.side).toLowerCase().includes(q));
}
// ---- Bet now
let sk = 'ev', sd = -1;
const COLS = [['ev', 'EV', 'num'], ['bet', 'Bet', ''], ['time', 'Starts', ''], ['venue', 'Best book', ''], ['price', 'Price', 'num'], ['fair', 'Fair', 'num'], ['others', 'Other books', ''], ['stake', 'Stake ¼K', 'num']];
function render(){
  const all = NOW.sides.filter(x => pass(x, false));
  let rows;
  if (F.view === 'best') {                                     // one row per bet: the best price on your books, the rest beside it
    const g = {}; for (const x of all) { const k = x.sport + '|' + x.id + '|' + x.market + '|' + x.side; (g[k] = g[k] || []).push(x); }
    rows = Object.values(g).map(xs => { xs.sort((a, b) => b.ev - a.ev); return Object.assign({}, xs[0], { others: xs.slice(1) }); }).filter(x => x.ev * 100 >= F.minEv);
  } else rows = all.filter(x => x.ev * 100 >= F.minEv).map(x => Object.assign({}, x, { others: [] }));
  const val = x => ({ ev: x.ev, bet: x.side, time: x.time, venue: x.venue, price: decOf(x), fair: x.fair, others: x.others.length, stake: kelly(x) })[sk];
  rows.sort((a, b) => { const A = val(a), B = val(b); return (A > B ? 1 : A < B ? -1 : 0) * sd; });
  $('#now').innerHTML = '<tr>' + COLS.map(([k, l, c]) => `<th data-k="${k}" class="${c}" style="cursor:pointer">${l}${k === sk ? (sd > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr>' +
    (rows.slice(0, 400).map(x => `<tr><td class="num"><b class="evb">${evf(x.ev)}</b></td>
      <td><span class="sp ${x.sport}">${x.sport}</span> <span class="nm">${betTxt(x)}</span><br><span class="tm">${x.game}${note(x) ? ' · ' + note(x) : ''}</span></td>
      <td><span class="nm">${until(x.time)}</span><br><span class="tm">${when(x.time)}</span></td><td><span class="bk">${nm(x.venue)}</span></td>
      <td class="num">${priceHtml(x)}</td><td class="num">${fairAmer(x.fair)}<br><span class="tm">${(x.fair * 100).toFixed(1)}%</span></td>
      <td class="tm">${x.others.slice(0, 5).map(o => `${nm(o.venue)} ${o.venue === 'Kalshi' ? Math.round(o.price * 100) + '¢' : (o.price > 0 ? '+' : '') + o.price} <span class="${o.ev >= 0 ? 'pos' : 'neg'}">(${(o.ev * 100).toFixed(1)}%)</span>`).join('<br>') || '—'}</td>
      <td class="num">$${Math.round(kelly(x) * F.bank)}</td></tr>`).join('') ||
     `<tr><td colspan="8" class="tm" style="text-align:center;padding:18px">Nothing at +${F.minEv}% or better with these filters. Most of the time the prices agree with Pinnacle: +EV shows up in short windows (news, line moves, new markets). Try a lower min EV, more books, or check back near game time.</td></tr>`);
  $('#count').textContent = `${rows.length} bet${rows.length === 1 ? '' : 's'} · ${all.length} prices match the filters · prices from ${NOW.at ? when(NOW.at) : '—'}`;
  // tracked plays: same filters (EV bar off), newest first
  const P = PLAYS.filter(x => F.sports.includes(x.sport) && F.mkts.includes(mktOf(x)) && F.books.includes(x.venue) && (!F.q.trim() || (x.game + ' ' + x.side).toLowerCase().includes(F.q.trim().toLowerCase())));
  const done = P.filter(x => x.res != null), wcl = P.filter(x => x.clv != null && new Date(x.time) < new Date()), units = done.reduce((s, x) => s + x.pl, 0), beat = wcl.filter(x => x.clv > 0).length;
  $('#kpi').innerHTML = `<div>+EV now<b>${rows.length}</b></div><div>tracked<b>${P.length}</b></div><div>avg EV flagged<b>${P.length ? (P.reduce((s, x) => s + x.ev, 0) / P.length * 100).toFixed(1) + '%' : '—'}</b></div>` +
    `<div>avg CLV<b>${wcl.length ? (wcl.reduce((s, x) => s + x.clv, 0) / wcl.length * 100).toFixed(1) + '%' : '—'}</b></div><div>beat the close<b>${wcl.length ? Math.round(beat / wcl.length * 100) + '%' : '—'}</b></div>` +
    `<div>record<b>${done.filter(x => x.res).length}-${done.filter(x => !x.res).length}</b></div><div>units<b class="${units >= 0 ? 'pos' : 'neg'}">${done.length ? (units >= 0 ? '+' : '') + units.toFixed(1) : '—'}</b></div>`;
  $('#log').innerHTML = '<tr><th>Bet</th><th>Book</th><th>Flagged</th><th class="num">Price</th><th class="num">EV then</th><th class="num">Fair at close</th><th class="num">CLV</th><th>Result</th></tr>' +
    (P.slice(0, 300).map(x => `<tr><td><span class="sp ${x.sport}">${x.sport}</span> <span class="nm">${betTxt(x)}</span><br><span class="tm">${x.game} · ${when(x.time)}</span></td><td>${nm(x.venue)}</td><td class="tm">${when(x.at)}</td>
      <td class="num">${priceHtml(x)}</td><td class="num">${evf(x.ev)}</td><td class="num">${x.closeFair == null ? '—' : (x.closeFair * 100).toFixed(1) + '%'}</td><td class="num">${evf(x.clv)}</td>
      <td>${x.res == null ? (new Date(x.time) < new Date() ? '<span class="tm">pending</span>' : '<span class="tm">upcoming</span>') : x.res ? `<span class="res y">✓</span> <span class="tm">+${x.pl.toFixed(2)}u</span>` : '<span class="res n">✗</span> <span class="tm">−1u</span>'}</td></tr>`).join('') ||
     '<tr><td colspan="8" class="tm" style="text-align:center;padding:14px">nothing flagged yet for these filters</td></tr>');
}
// ---- filter bar wiring: chips toggle values in F[key]; an empty chip set shows nothing, 'All' / 'None' buttons per group
function chips(id, key, opts, label){
  $(id).innerHTML = `<span class="fl">${label}</span>` + opts.map(([v, l]) => `<button class="chip${F[key].includes(v) ? ' on' : ''}" data-v="${v}">${l}</button>`).join('') +
    `<button class="mini" data-all="1">all</button><button class="mini" data-none="1">none</button>`;
  $(id).onclick = e => { const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.all) F[key] = opts.map(o => o[0]); else if (b.dataset.none) F[key] = []; else { const v = b.dataset.v; F[key] = F[key].includes(v) ? F[key].filter(x => x !== v) : F[key].concat(v); }
    save(); chips(id, key, opts, label); render(); };
}
chips('#fSport', 'sports', [['NFL', 'NFL'], ['NBA', 'NBA'], ['MLB', 'MLB']], 'Sport');
chips('#fMkt', 'mkts', [['ML', 'Moneyline'], ['Spread', 'Spread'], ['Total', 'Total'], ['pts', 'Points'], ['reb', 'Rebounds'], ['ast', 'Assists'], ['3PM', 'Threes']], 'Market');
chips('#fBook', 'books', VENUES.map(v => [v, nm(v)]), 'Books');
const bind = (id, key, num, ev = 'input') => { const el = $(id); if (el.type === 'checkbox') el.checked = F[key]; else el.value = F[key];
  el.addEventListener(ev, () => { F[key] = el.type === 'checkbox' ? el.checked : num ? (+el.value || 0) : el.value; save(); render(); }); };
bind('#minev', 'minEv', true); bind('#oddsMin', 'oddsMin', true); bind('#oddsMax', 'oddsMax', true); bind('#bank', 'bank', true); bind('#q', 'q', false);
bind('#within', 'within', false, 'change'); bind('#view', 'view', false, 'change'); bind('#pinOnly', 'pinOnly', false, 'change'); bind('#hideStarted', 'hideStarted', false, 'change');
document.addEventListener('click', e => { const th = e.target.closest('#now th[data-k]'); if (!th) return; const k = th.dataset.k; if (k === sk) sd = -sd; else { sk = k; sd = (k === 'bet' || k === 'time' || k === 'venue') ? 1 : -1; } render(); });
render(); setInterval(render, 60000);   // keep the countdowns fresh
"""

def page():
    from navbar import navbar
    nav = navbar('ev', '', {}, {})
    upd = now.get('at') or ''
    return f"""<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fade The Chalk</title>{FONTS}{CSS}<header><h1><a href="index.html">FADE THE <span>CHALK</span></a></h1><div class="sub">+EV · every price you can bet vs Pinnacle's fair line · MLB, NFL, NBA · prices from {upd.replace('T', ' ')} UTC</div></header>{nav}
<style>.fb{{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:6px 0}}.fl{{font-size:11px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:var(--mute);min-width:62px}}
.chip{{background:var(--panel);color:var(--mute);border:1px solid var(--line);border-radius:999px;padding:5px 12px;font:600 12px var(--font);cursor:pointer}}.chip.on{{color:var(--ink);border-color:var(--acc);background:#1d2a20}}
.mini{{background:none;border:none;color:var(--mute);font:600 11px var(--font);cursor:pointer;text-decoration:underline;padding:2px 4px}}
.fr{{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;margin:8px 0;font-size:13px}}.fr label{{display:inline-flex;align-items:center;gap:6px;color:var(--mute)}}
.fr input[type=number],.fr input[type=search],.fr select{{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:5px 8px;font:13px var(--font)}}.fr input[type=number]{{width:78px}}.fr input[type=search]{{width:190px}}
.evb{{font-size:15px}}.bk{{display:inline-block;border:1px solid var(--line);border-radius:5px;padding:2px 7px;font-weight:700;font-size:12px}}
.sp{{display:inline-block;font-size:10px;font-weight:800;letter-spacing:.5px;border-radius:4px;padding:1px 5px}}.sp.NFL{{background:#153325;color:#86e8ad}}.sp.NBA{{background:#3a2410;color:#ffb36b}}.sp.MLB{{background:#18293d;color:#8cc2ff}}
#count{{font-size:12px;color:var(--mute);margin:4px 2px}}#now td,#log td{{vertical-align:top}}
@media(max-width:700px){{.fl{{min-width:auto;width:100%}}}}</style>
<div class="panel top">
<div class="kpi" id="kpi"></div>
<div class="fb" id="fSport"></div><div class="fb" id="fMkt"></div><div class="fb" id="fBook"></div>
<div class="fr"><label>min EV % <input type="number" id="minev" step="0.5" min="0"></label>
<label>odds from <input type="number" id="oddsMin" step="25"> to <input type="number" id="oddsMax" step="25"></label>
<label>starts within <select id="within"><option value="1h">1 hour</option><option value="3h">3 hours</option><option value="12h">12 hours</option><option value="24h">24 hours</option><option value="all">any time</option></select></label>
<label>view <select id="view"><option value="best">best price per bet</option><option value="all">every book</option></select></label>
<label><input type="checkbox" id="pinOnly"> props vs Pinnacle only</label><label><input type="checkbox" id="hideStarted"> hide started</label>
<label>search <input type="search" id="q" placeholder="team or player"></label><label>bankroll $ <input type="number" id="bank" step="50" min="0"></label></div>
<h2 style="margin:12px 0 4px">Bet now</h2>
<div id="count"></div><div class="wrap"><table class="lt" id="now"></table></div>
<div class="legend"><b>How it works.</b> Pinnacle is the sharpest book, so its price with the vig removed is the best estimate of each side's real chance (<b>Pinnacle fair</b>). <b>EV</b> = that chance times what you'd be paid, minus your stake: +3% means you expect to make 3¢ per $1 over the long run. For <b>Kalshi / Robinhood</b>, the price is the ask plus Kalshi's taker fee (about 1.75¢ at 50¢). Robinhood charges a flat 2¢ per contract instead, so knock about a point off there. Sportsbook prices are their posted moneylines. <b>NBA player props</b> (points, rebounds, assists, threes) come from Novig, ProphetX, Polymarket and the sportsbooks, compared at the exact same line against Pinnacle's no-vig price (power method), or, when Pinnacle doesn't list the player, the average of BetOnline / FanDuel / DraftKings (less reliable: shown under the bet). They're pulled once a game, about 2 to 3 hours before tip. Exchange fees other than Kalshi's are not included. <b>Stake</b> = a quarter of the Kelly bet for your bankroll, the standard way to size +EV without big swings. <b>Best price per bet</b> groups the same bet across your books and shows the best one, with the others beside it; <b>every book</b> lists each price. Odds range is in American odds (−400 to +600 by default). Every filter is saved on this device.
<b>Read it with care.</b> Prices refresh with each run (hourly, or press ↻ Rerun), Pinnacle at most every 50 minutes, so a big edge can be a stale line that's already moved. Check the live price before you bet. "Alt line" = Kalshi's strike differs from Pinnacle's, so the fair is adjusted and less exact. Kalshi asks are only good for the size posted at that price.</div>
<h2 style="margin:18px 0 6px">Tracked plays <small>every side that hit +2%, with the closing line</small></h2>
<div class="wrap"><table class="lt" id="log"></table></div>
<div class="legend"><b>CLV</b> (closing-line value) = what the bet was worth at Pinnacle's last price before the game. Beating the close over and over is the proof an edge is real: it shows up after a couple hundred bets, long before wins and losses settle it. <b>Units</b> = 1u flat on every flagged side at the price it was flagged.</div>
</div>
<script>const NOW = {jd(now)}; const PLAYS = {jd(plays)}; const VENUES = {jd(venues)};{JS}</script>"""

open(os.path.join(SITE, 'ev.html'), 'w', encoding='utf-8', newline='\n').write(page())
print(f"ev.html: {len(now['sides'])} prices now, {sum(1 for x in now['sides'] if x['ev'] >= 0.02)} at +2%+, {len(plays)} tracked ({sum(1 for p in plays if p['res'] is not None)} graded)")
