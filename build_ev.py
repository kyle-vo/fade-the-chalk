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
const $ = s => document.querySelector(s);
const LS = (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } };
const SV = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
const NAMES = { Kalshi: 'Kalshi / Robinhood', draftkings: 'DraftKings', fanduel: 'FanDuel', betmgm: 'BetMGM', betrivers: 'BetRivers', bovada: 'Bovada', betonlineag: 'BetOnline', fliff: 'Fliff', williamhill_us: 'Caesars', espnbet: 'ESPN Bet', hardrockbet: 'Hard Rock', ballybet: 'Bally', betus: 'BetUS', lowvig: 'LowVig', mybookieag: 'MyBookie' };
const nm = v => NAMES[v] || v;
let on = LS('ftc_ev_venues', null) || VENUES.filter(v => ['Kalshi', 'bovada', 'betonlineag'].includes(v));
let sport = LS('ftc_ev_sport', 'ALL'), minEv = LS('ftc_ev_min', 2), bank = LS('ftc_ev_bank', 1000);
const when = t => new Date(t).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
const pricef = x => x.venue === 'Kalshi' ? Math.round(x.price * 100) + '¢' : (x.price > 0 ? '+' : '') + x.price;
const evf = v => v == null ? '—' : `<span class="${v >= 0 ? 'pos' : 'neg'}">${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%</span>`;
const costOf = x => x.venue === 'Kalshi' ? x.price + 0.07 * x.price * (1 - x.price) : null;
// quarter Kelly: f = (p*b - (1-p)) / b with b = profit per $1
function kelly(x){ const b = x.venue === 'Kalshi' ? (1 - costOf(x)) / costOf(x) : (x.price > 0 ? x.price / 100 : 100 / -x.price); const f = (x.fair * b - (1 - x.fair)) / b; return Math.max(0, f / 4); }
const bet = x => `${x.market === 'ML' ? x.side + ' ML' : x.side}${x.pinLine != null ? ` <span class="tm" title="Kalshi's line differs from Pinnacle's; fair adjusted about 2.5 points per half point">alt line · Pinnacle ${x.pinLine}</span>` : ''}`;
let sk = 'ev', sd = -1;
const cols = [['sport', 'Sport'], ['time', 'Game'], ['bet', 'Bet'], ['venue', 'Where'], ['price', 'Price'], ['fair', 'Pinnacle fair'], ['ev', 'EV'], ['stake', 'Stake (¼ Kelly)']];
function filt(xs){ return xs.filter(x => (sport === 'ALL' || x.sport === sport) && on.includes(x.venue)); }
function render(){
  const val = x => ({ sport: x.sport, time: x.time, bet: x.side, venue: x.venue, price: x.venue === 'Kalshi' ? x.price : 1 / dec(x.price), fair: x.fair, ev: x.ev, stake: kelly(x) })[sk];
  const xs = filt(NOW.sides).filter(x => x.ev * 100 >= minEv).sort((a, b) => { const A = val(a), B = val(b); return (A > B ? 1 : A < B ? -1 : 0) * sd; });
  $('#now').innerHTML = '<tr>' + cols.map(([k, l]) => `<th data-k="${k}" class="${['price', 'fair', 'ev', 'stake'].includes(k) ? 'num' : ''}" style="cursor:pointer">${l}${k === sk ? (sd > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr>' +
    (xs.map(x => `<tr><td>${x.sport}</td><td><span class="nm">${x.game}</span><br><span class="tm">${when(x.time)}</span></td><td class="nm">${bet(x)}</td><td>${nm(x.venue)}</td>
      <td class="num"><b>${pricef(x)}</b></td><td class="num">${Math.round(x.fair * 1000) / 10}%</td><td class="num"><b>${evf(x.ev)}</b></td><td class="num">$${Math.round(kelly(x) * bank)}</td></tr>`).join('') ||
     `<tr><td colspan="8" class="tm" style="text-align:center;padding:16px">Nothing at +${minEv}% or better right now on the books you picked. Most of the time the prices agree with Pinnacle: +EV shows up in short windows (news, line moves, new markets), so check back near game time.</td></tr>`);
  // near misses: the best few under the bar, so an empty board still shows how close things are
  const near = filt(NOW.sides).filter(x => x.ev * 100 < minEv).sort((a, b) => b.ev - a.ev).slice(0, 6);
  $('#near').innerHTML = near.length ? 'Closest below the bar: ' + near.map(x => `${x.side}${x.market === 'ML' ? ' ML' : ''} @ ${nm(x.venue)} ${pricef(x)} (${evf(x.ev)})`).join(' · ') : '';
  // tracked plays
  const P = filt(PLAYS), done = P.filter(x => x.res != null), wcl = P.filter(x => x.clv != null && new Date(x.time) < new Date());
  const units = done.reduce((s, x) => s + x.pl, 0), beat = wcl.filter(x => x.clv > 0).length;
  $('#kpi').innerHTML = `<div>+EV now<b>${xs.length}</b></div><div>tracked<b>${P.length}</b></div><div>avg EV when flagged<b>${P.length ? (P.reduce((s, x) => s + x.ev, 0) / P.length * 100).toFixed(1) + '%' : '—'}</b></div>` +
    `<div>avg CLV<b>${wcl.length ? (wcl.reduce((s, x) => s + x.clv, 0) / wcl.length * 100).toFixed(1) + '%' : '—'}</b></div><div>beat the close<b>${wcl.length ? Math.round(beat / wcl.length * 100) + '%' : '—'}</b></div>` +
    `<div>record<b>${done.filter(x => x.res).length}-${done.filter(x => !x.res).length}</b></div><div>units (1u flat)<b class="${units >= 0 ? 'pos' : 'neg'}">${done.length ? (units >= 0 ? '+' : '') + units.toFixed(1) : '—'}</b></div>`;
  $('#log').innerHTML = '<tr><th>Sport</th><th>Game</th><th>Bet</th><th>Where</th><th>Flagged</th><th class="num">Price</th><th class="num">Fair then</th><th class="num">EV then</th><th class="num">Fair at close</th><th class="num">CLV</th><th>Result</th></tr>' +
    (P.slice(0, 300).map(x => `<tr><td>${x.sport}</td><td><span class="nm">${x.game}</span><br><span class="tm">${when(x.time)}</span></td><td class="nm">${bet(x)}</td><td>${nm(x.venue)}</td><td class="tm">${when(x.at)}</td>
      <td class="num">${pricef(x)}</td><td class="num">${Math.round(x.fair * 1000) / 10}%</td><td class="num">${evf(x.ev)}</td><td class="num">${x.closeFair == null ? '—' : Math.round(x.closeFair * 1000) / 10 + '%'}</td><td class="num">${evf(x.clv)}</td>
      <td>${x.res == null ? (new Date(x.time) < new Date() ? '<span class="tm">pending</span>' : '<span class="tm">upcoming</span>') : x.res ? `<span class="res y">✓</span> <span class="tm">+${x.pl.toFixed(2)}u</span>` : '<span class="res n">✗</span> <span class="tm">−1u</span>'}</td></tr>`).join('') ||
     '<tr><td colspan="11" class="tm" style="text-align:center;padding:14px">nothing flagged yet: every side that reaches +2% gets logged here with the closing line and the result</td></tr>');
}
const dec = a => 1 + (a > 0 ? a / 100 : 100 / -a);
$('#venues').innerHTML = VENUES.map(v => `<label class="ck"><input type="checkbox" value="${v}" ${on.includes(v) ? 'checked' : ''}> ${nm(v)}</label>`).join('');
$('#venues').addEventListener('change', () => { on = [...document.querySelectorAll('#venues input:checked')].map(i => i.value); SV('ftc_ev_venues', on); render(); });
$('#sport').value = sport; $('#sport').addEventListener('change', e => { sport = e.target.value; SV('ftc_ev_sport', sport); render(); });
$('#minev').value = minEv; $('#minev').addEventListener('input', e => { minEv = +e.target.value || 0; SV('ftc_ev_min', minEv); render(); });
$('#bank').value = bank; $('#bank').addEventListener('input', e => { bank = +e.target.value || 0; SV('ftc_ev_bank', bank); render(); });
document.addEventListener('click', e => { const th = e.target.closest('#now th[data-k]'); if (!th) return; const k = th.dataset.k; if (k === sk) sd = -sd; else { sk = k; sd = (k === 'sport' || k === 'time' || k === 'bet' || k === 'venue') ? 1 : -1; } render(); });
render();
"""

def page():
    from navbar import navbar
    nav = navbar('ev', '', {}, {})
    upd = now.get('at') or ''
    return f"""<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fade The Chalk</title>{FONTS}{CSS}<header><h1><a href="index.html">FADE THE <span>CHALK</span></a></h1><div class="sub">+EV · every price you can bet vs Pinnacle's fair line · MLB, NFL, NBA · prices from {upd.replace('T', ' ')} UTC</div></header>{nav}
<style>.ck{{display:inline-flex;align-items:center;gap:4px;margin:2px 12px 2px 0;font-size:13px;white-space:nowrap}}#venues{{margin:6px 0 4px}}#near{{font-size:12px;color:var(--mute);margin:6px 2px 0}}
.ctl input[type=number]{{width:70px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:5px;padding:3px 6px}}</style>
<div class="panel top">
<div class="kpi" id="kpi"></div>
<div class="ctl"><label>sport <select id="sport"><option value="ALL">All</option><option>NFL</option><option>NBA</option><option>MLB</option></select></label>
<label>min EV % <input type="number" id="minev" step="0.5" min="0"></label><label>bankroll $ <input type="number" id="bank" step="50" min="0"></label></div>
<div id="venues"></div>
<h2 style="margin:12px 0 6px">Bet now</h2>
<div class="wrap"><table class="lt" id="now"></table></div><div id="near"></div>
<div class="legend"><b>How it works.</b> Pinnacle is the sharpest book, so its price with the vig removed is the best estimate of each side's real chance (<b>Pinnacle fair</b>). <b>EV</b> = that chance times what you'd be paid, minus your stake: +3% means you expect to make 3¢ per $1 over the long run. For <b>Kalshi / Robinhood</b>, the price is the ask plus Kalshi's taker fee (about 1.75¢ at 50¢). Robinhood charges a flat 2¢ per contract instead, so knock about a point off there. Sportsbook prices are their posted moneylines. <b>Stake</b> = a quarter of the Kelly bet for your bankroll, the standard way to size +EV without big swings. Pick the books you actually use; the choice is saved on this device.
<b>Read it with care.</b> Prices refresh with each run (hourly, or press ↻ Rerun), Pinnacle at most every 50 minutes, so a big edge can be a stale line that's already moved. Check the live price before you bet. "Alt line" = Kalshi's strike differs from Pinnacle's, so the fair is adjusted and less exact. Kalshi asks are only good for the size posted at that price.</div>
<h2 style="margin:18px 0 6px">Tracked plays <small>every side that hit +2%, with the closing line</small></h2>
<div class="wrap"><table class="lt" id="log"></table></div>
<div class="legend"><b>CLV</b> (closing-line value) = what the bet was worth at Pinnacle's last price before the game. Beating the close over and over is the proof an edge is real: it shows up after a couple hundred bets, long before wins and losses settle it. <b>Units</b> = 1u flat on every flagged side at the price it was flagged.</div>
</div>
<script>const NOW = {jd(now)}; const PLAYS = {jd(plays)}; const VENUES = {jd(venues)};{JS}</script>"""

open(os.path.join(SITE, 'ev.html'), 'w', encoding='utf-8', newline='\n').write(page())
print(f"ev.html: {len(now['sides'])} prices now, {sum(1 for x in now['sides'] if x['ev'] >= 0.02)} at +2%+, {len(plays)} tracked ({sum(1 for p in plays if p['res'] is not None)} graded)")
