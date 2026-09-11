"""Build the static site into docs/ (GitHub Pages):
  index.html          today's board (MLB + NFL tabs)
  days/<date>.html    a past MLB slate with results graded in
  nfl/<week>.html     an NFL week with results graded in
  track.html          paper-bet ledger (bets live in your browser) + model strategies scored at fair odds
"""
import json, os, glob, datetime, math
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); SITE = os.path.join(HERE, 'docs')
for d in ('', 'days', 'nfl'): os.makedirs(os.path.join(SITE, d), exist_ok=True)
J = lambda p: json.load(open(p, encoding='utf-8'))
jd = lambda o: json.dumps(o).replace('</', '<' + chr(92) + '/')
jd = lambda o: json.dumps(o).replace('</', '<' + chr(92) + '/')
board = J(os.path.join(HERE, 'output', 'board.json'))
today = board['mlb'][0]['time'][:10] if board['mlb'] else datetime.date.today().isoformat()

# ---------- assemble history ----------
days = {}
for lock in sorted(glob.glob(os.path.join(BT, 'pred_*.json'))):
    date = os.path.basename(lock)[5:15]; rows = J(lock)
    rp = os.path.join(BT, f'res_{date}.json'); res = J(rp) if os.path.exists(rp) else {}
    graded_games = set(res.get('_games', []))
    for r in rows:
        r['date'] = date
        g = res.get(str(r['id']))
        if r.get('gamePk') in graded_games or (g is not None and not r.get('gamePk')):
            if g and g['pa'] > 0: r['hit'] = 1 if g['hr'] > 0 else 0; r['actual'] = g['hr']; r['actualPA'] = g['pa']
            else: r['hit'] = None; r['dnp'] = True
        else: r['hit'] = None
    days[date] = rows
weeks = {}
for lock in sorted(glob.glob(os.path.join(BT, 'nfl_*.json'))):
    wk = os.path.basename(lock)[4:-5]; rows = J(lock)
    rp = os.path.join(BT, f'nflres_{wk}.json'); res = J(rp) if os.path.exists(rp) else {}
    graded_games = set(res.get('_games', []))
    for r in rows:
        r['date'] = wk
        if r['eventId'] in graded_games:
            g = res.get(str(r['id']))
            if g: r['hit'] = 1 if g['td'] > 0 else 0; r['actual'] = g['td']
            else: r['hit'] = 0; r['actual'] = 0; r['dnp'] = True   # on roster, no touches
        else: r['hit'] = None
    weeks[wk] = rows
import unicodedata, re as _re
_norm = lambda x: _re.sub(r'[^a-z ]', '', unicodedata.normalize('NFD', x or '').encode('ascii', 'ignore').decode().lower()).strip()
def _implied(o): return (-o) / (-o + 100) if o < 0 else 100 / (o + 100)
PUBLIC_BOOKS = ('draftkings', 'fanduel', 'betmgm', 'espnbet', 'fanatics', 'williamhill_us', 'betrivers')
SHARP_BOOKS = ('bovada', 'betonlineag', 'pinnacle', 'lowvig', 'betus', 'mybookieag')
def book_skew(books):
    """retail implied % minus offshore implied %: positive = public books are shorter = the crowd is on him."""
    pub = [_implied(o) for b, o in books.items() if b in PUBLIC_BOOKS]; shp = [_implied(o) for b, o in books.items() if b in SHARP_BOOKS]
    if not pub or not shp: return None
    return round(max(-5.0, min(5.0, (sum(pub) / len(pub) - sum(shp) / len(shp)) * 100)), 1)   # capped: a stale book is not the crowd
def attach_odds(rows, date, sport):
    """Book odds from the latest snapshot of that date (closing line), movement vs the first snapshot -> heat bump."""
    sp = os.path.join(BT, f'odds_{date}.json')
    if not os.path.exists(sp): return
    snaps = J(sp); first, last = snaps[0].get(sport, {}), snaps[-1].get(sport, {})
    for r in rows:
        nm = _norm(r['name']); o = last.get(nm)
        if o is None: continue
        r['book'] = o
        bks = snaps[-1].get('books', {}).get(sport, {}).get(nm, {})
        r['onFliff'] = 'fliff' in bks
        r['bookUsed'] = 'fliff' if 'fliff' in bks else 'underdog' if 'underdog' in bks else 'best'
        if bks: r['bestBook'] = max(bks.values()); r['bestAt'] = max(bks, key=bks.get)
        sk = book_skew(snaps[-1].get('books', {}).get(sport, {}).get(nm, {}))
        if sk is not None:
            r['skew'] = sk
            r['heat'] = round(min(100, max(0, r['heat'] + (12 if sk >= 2.5 else 6 if sk >= 1.2 else -6 if sk <= -1.2 else 0))))
            r.setdefault('notes', []).append(f"book skew {sk:+.1f} pts (retail books vs offshore; + = public money on him)")
        if nm in first and len(snaps) > 1:
            mv = (_implied(o) - _implied(first[nm])) * 100   # + = price shortened = money came in
            r['move'] = round(mv, 1)
            r['heat'] = round(min(100, max(0, r['heat'] + (15 if mv >= 3 else 8 if mv >= 1.5 else -8 if mv <= -1.5 else 0))))
            r.setdefault('notes', []).append(f"line moved {first[nm]:+d} -> {o:+d} ({mv:+.1f} pts implied)")
def attach_kalshi(rows, date, sport):
    """Kalshi = the public's own price with money behind it. yes price -> crowd %; volume -> how many are on him."""
    kp = os.path.join(BT, f'kalshi_{sport.lower()}_{date}.json')
    if not os.path.exists(kp): return
    snaps = J(kp); ms = snaps[-1]['markets']; first = snaps[0]['markets']
    vols = sorted(v['vol'] for v in ms.values()); top = vols[int(len(vols) * 0.75)] if vols else 0
    for r in rows:
        k = ms.get(_norm(r['name']))
        if not k: continue
        r['kalshi'] = k['yes']; r['kvol'] = k['vol']; r['koi'] = k['oi']
        gap = (k['yes'] - r['prob']) * 100                      # crowd above the model = they love him more than the numbers do
        bump = (12 if gap >= 6 else 6 if gap >= 3 else -6 if gap <= -3 else 0) + (10 if k['vol'] >= top and k['vol'] > 0 else 0)
        if _norm(r['name']) in first and len(snaps) > 1:
            km = (k['yes'] - first[_norm(r['name'])]['yes']) * 100; r['kmove'] = round(km, 1); bump += 8 if km >= 3 else -5 if km <= -3 else 0
        r['heat'] = round(min(100, max(0, r['heat'] + bump)))
        r.setdefault('notes', []).append(f"Kalshi: crowd says {k['yes'] * 100:.0f}% (model {r['prob'] * 100:.0f}%), ${k['vol']:,} traded" + (f", moved {r['kmove']:+.1f} pts" if 'kmove' in r else ''))
for _d, _rows in days.items(): attach_odds(_rows, _d, 'MLB'); attach_kalshi(_rows, _d, 'MLB')
for _w, _rows in weeks.items(): attach_odds(_rows, today, 'NFL')
attach_odds(board['nfl'], today, 'NFL'); attach_odds(board['mlb'], today, 'MLB'); attach_kalshi(board['mlb'], today, 'MLB')
slim = lambda r: {k: r.get(k) for k in ('sport', 'id', 'name', 'team', 'game', 'time', 'prob', 'fair', 'heat', 'hit', 'actual', 'dnp', 'date', 'pos', 'slot', 'lineupPosted', 'lateLock', 'book', 'move', 'skew', 'onFliff', 'bookUsed', 'bestBook', 'bestAt', 'kalshi', 'kvol', 'kmove')}
HISTORY = [slim(r) for rows in days.values() for r in rows] + [slim(r) for rows in weeks.values() for r in rows]

# ---------- templates ----------
FONTS = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;800&family=IBM+Plex+Sans:wght@400;600;700&family=IBM+Plex+Mono:wght@400;600&display=swap">'
CSS = r"""<style>
:root{--bg:#0b0d10;--panel:#14181e;--line:#232a33;--ink:#e6e9ee;--mute:#8a94a3;--acc:#ffb020;--good:#2fd47a;--bad:#ff4d5e;--warn:#ffb020;--blue:#4aa3ff;--font:"IBM Plex Sans",ui-sans-serif,system-ui,"Segoe UI",sans-serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;--disp:"Barlow Condensed","Arial Narrow",Impact,sans-serif;color-scheme:dark}
*{box-sizing:border-box}body{background:var(--bg);color:var(--ink);font-family:var(--font);margin:0;padding:0 0 60px;font-size:14px}
header{padding:18px 26px 12px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:8px 18px;align-items:baseline}
h1{margin:0;font-family:var(--disp);font-size:34px;font-weight:800;letter-spacing:1.5px;line-height:1}h1 span{color:var(--acc)}h1 a{color:inherit;text-decoration:none}
.sub{color:var(--mute);font-size:13px}
nav{display:flex;flex-wrap:wrap;gap:4px 6px;padding:12px 26px 0;font-size:13px;align-items:center}
nav a{color:var(--mute);text-decoration:none;padding:5px 10px;border:1px solid var(--line);border-radius:6px;background:var(--panel)}nav a:hover{color:var(--ink);border-color:#3a4552}nav a.on{color:var(--ink);border-color:var(--acc)}nav .lbl{color:var(--mute);margin-left:6px;font-size:11px;text-transform:uppercase;letter-spacing:.6px}
.tabs{display:flex;gap:6px;padding:14px 26px 0}
.tab{font-family:var(--disp);font-size:17px;letter-spacing:.6px;text-transform:uppercase;padding:8px 16px;border:1px solid var(--line);border-bottom:none;border-radius:8px 8px 0 0;background:var(--panel);color:var(--mute);cursor:pointer;font-weight:600}
.tab.on{color:var(--ink);background:#1b2129;border-color:#2f3944}
.panel{margin:0 26px;border:1px solid var(--line);background:var(--panel);border-radius:0 10px 10px 10px;padding:14px}
.panel.top{border-radius:10px;margin-top:14px}
.ctl{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px;font-size:13px}
.ctl input[type=text],.ctl input[type=number],.ctl select{background:#0e1115;border:1px solid var(--line);color:var(--ink);padding:6px 8px;border-radius:6px;font:inherit}
.ctl label{color:var(--mute)}
textarea{width:100%;background:#0e1115;color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:8px;font:12px var(--mono);min-height:64px}
details.paste{margin-bottom:12px;font-size:13px;color:var(--mute)}details.paste summary{cursor:pointer;color:var(--ink);font-weight:600}
button{background:#1b2129;border:1px solid #2f3944;color:var(--ink);padding:6px 12px;border-radius:6px;cursor:pointer;font:inherit}button:hover{border-color:var(--acc)}
.wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:1000px}
th{font-size:11px;text-transform:uppercase;letter-spacing:.6px;position:sticky;top:0;background:#1b2129;text-align:left;padding:8px 8px;border-bottom:1px solid var(--line);color:var(--mute);font-weight:600;cursor:pointer;white-space:nowrap}
th.on{color:var(--acc)}
td{padding:7px 8px;border-bottom:1px solid #1a2028;vertical-align:middle;white-space:nowrap}
tr.row:hover td{background:#181e26}
td.num{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right}
.nm{font-weight:700}.tm{color:var(--mute);font-size:12px}
input.odds,input.pub,input.stk{width:60px;background:#0e1115;border:1px solid var(--line);color:var(--ink);padding:4px 6px;border-radius:5px;font:12px var(--mono);text-align:right}input.stk{width:44px}
input.bet{accent-color:var(--acc);width:16px;height:16px;vertical-align:middle}
.bar{display:inline-block;height:8px;border-radius:4px;background:#2b3440;width:60px;vertical-align:middle;position:relative;overflow:hidden}.bar i{position:absolute;left:0;top:0;bottom:0;background:linear-gradient(90deg,#4aa3ff,#ff4d5e)}
.v{display:inline-block;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:800;letter-spacing:.4px}
.v.SLEEPER{background:#123d26;color:var(--good)}.v.VALUE{background:#12304a;color:var(--blue)}.v.TRAP,.v.FADE{background:#4a1218;color:var(--bad)}.v.CHALK{background:#463610;color:var(--warn)}.v.PASS,.v.DONE{background:#20262e;color:var(--mute)}
.res{font-family:var(--mono);font-weight:600}.res.y{color:var(--good)}.res.n{color:var(--mute)}.res.d{color:#5b6472}
.pos{color:var(--good)}.neg{color:var(--bad)}
tr.det td{background:#0e1115;color:var(--mute);white-space:normal;font-size:12px;padding:8px 14px 10px}
tr.det .f{display:inline-block;margin:2px 10px 2px 0;font-family:var(--mono)}
.legend{font-size:12px;color:var(--mute);margin:10px 0 0;line-height:1.7;max-width:110ch}.legend b{color:var(--ink)}
.kpi{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}.kpi div{background:#0e1115;border:1px solid var(--line);border-radius:8px;padding:8px 12px;font-size:12px;color:var(--mute);min-width:96px}.kpi b{display:block;font-size:22px;color:var(--ink);font-family:var(--disp);font-weight:800;letter-spacing:.5px}.kpi b.pos{color:var(--good)}.kpi b.neg{color:var(--bad)}
h2{font-family:var(--disp);font-size:22px;letter-spacing:.8px;text-transform:uppercase;margin:22px 0 10px;color:var(--ink)}h2 small{font-family:var(--font);font-size:12px;color:var(--mute);text-transform:none;letter-spacing:0;margin-left:10px;font-weight:400}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px}
.mini table{min-width:0}
svg.chart{width:100%;height:220px;display:block;background:#0e1115;border:1px solid var(--line);border-radius:8px}
.note{font-size:12px;color:var(--mute);line-height:1.6;max-width:90ch}
.empty{padding:22px;color:var(--mute);text-align:center;border:1px dashed var(--line);border-radius:8px}
@media(max-width:700px){header,nav,.tabs,.panel{padding-left:10px;padding-right:10px}.panel{margin-left:6px;margin-right:6px}}
</style>"""

def nav(active, root):
    items = [('index.html', 'Today'), ('track.html', 'Track')]
    html = ''.join(f'<a href="{root}{h}" class="{"on" if active == h else ""}">{t}</a>' for h, t in items)
    html += '<span class="lbl">MLB days</span>' + ''.join(f'<a href="{root}days/{d}.html" class="{"on" if active == "days/" + d else ""}">{d[5:]}</a>' for d in sorted(days, reverse=True)[:14])
    if weeks: html += '<span class="lbl">NFL</span>' + ''.join(f'<a href="{root}nfl/{w}.html" class="{"on" if active == "nfl/" + w else ""}">wk {w.split("wk")[1]}</a>' for w in sorted(weeks, reverse=True)[:6])
    return f'<nav>{html}</nav>'

def head(title, sub, active, root):
    return f'<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>{FONTS}{CSS}<header><h1><a href="{root}index.html">FADE THE <span>CHALK</span></a></h1><div class="sub">{sub}</div></header>{nav(active, root)}'

BOARD_JS = r"""
const $ = s => document.querySelector(s);
let tab = PAGE.tab, sortKey = PAGE.graded ? 'prob' : 'nasty', sortDir = -1;
let store = {};
try { store = JSON.parse(localStorage.getItem('ftc_bets') || '{}'); } catch (e) { store = {}; }
function save(){ try { localStorage.setItem('ftc_bets', JSON.stringify(store)); } catch (e) {} }
const norm = s => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z ]/g, '').replace(/\s+/g, ' ').trim();
const implied = o => { o = +o; if (!o || isNaN(o)) return null; return o < 0 ? (-o) / (-o + 100) : 100 / (o + 100); };
const fmtOdds = o => o > 0 ? '+' + o : '' + o;
const key = r => r.date + '|' + r.sport + ':' + r.id;
function verdict(r){
  const e = store[key(r)] || {}; const oddsIn = e.odds || r.book; const imp = implied(oddsIn); const edge = imp == null ? null : r.prob - imp;
  const heat = e.pub != null && e.pub !== '' ? +e.pub : r.heat;
  const live = r.hit != null || r.dnp || !/Scheduled|Pre-Game|Warmup|STATUS_SCHEDULED/i.test(r.state || 'Scheduled');
  let v = 'PASS';
  if (edge != null) {
    if (edge >= .04 && heat < 45) v = 'SLEEPER'; else if (edge >= .03) v = 'VALUE';
    else if (e.pub !== undefined && e.pub !== '' && +e.pub >= 60 && edge < 0) v = 'FADE';
    else if (heat >= 60 && edge <= 0.01) v = 'TRAP';
  } else if (heat >= 65) v = 'CHALK'; else if (r.prob >= .3 && heat < 40) v = 'SLEEPER';
  const nasty = r.prob * 100 + (edge == null ? 0 : edge * 150) - heat * 0.2;
  return { edge, heat, v, nasty, imp, live };
}
const COLS = {
  mlb: [['Player','name'],['Slot','slot'],['Game','game'],['vs SP','pitcher'],['Season','hr'],['L15','l15hr'],['Model %','prob'],['Fair','fair'],['Book','odds'],['Edge','edge'],['Heat','heat'],['Public %','pub'],['Verdict','v'],['Nasty','nasty'],['Bet','bet'],['Result','hit']],
  nfl: [['Player','name'],['Pos','pos'],['Game','game'],['Line','spread'],['Team imp.','implied'],['2025 TD','prevTD'],['Share','share'],['Model %','prob'],['Fair','fair'],['Book','odds'],['Edge','edge'],['Heat','heat'],['Public %','pub'],['Verdict','v'],['Nasty','nasty'],['Bet','bet'],['Result','hit']]
};
function resultCell(r){
  if (r.dnp) return '<span class="res d">DNP</span>';
  if (r.hit == null) return '<span class="res n">—</span>';
  return r.hit ? `<span class="res y">✓ ${r.sport === 'MLB' ? 'HR' : 'TD'}${r.actual > 1 ? ' x' + r.actual : ''}</span>` : '<span class="res n">✗</span>';
}
function render(){
  const rows = (PAGE.rows[tab] || []).map(r => ({ r, ...verdict(r) }));
  const q = norm($('#q').value), minp = +$('#minp').value / 100, maxh = +$('#maxh').value, hide = $('#hidedone').checked, only = $('#onlyplays').checked, onlybets = $('#onlybets').checked;
  let list = rows.filter(x => (!hide || !x.live || PAGE.graded) && x.r.prob >= minp && x.heat <= maxh && (!only || ['SLEEPER','VALUE','TRAP','FADE'].includes(x.v)) && (!onlybets || (store[key(x.r)] || {}).on) &&
      (!q || norm(x.r.name).includes(q) || norm(x.r.team).includes(q) || norm(x.r.game).includes(q) || norm(x.r.teamName || '').includes(q)));
  const get = x => ({ nasty: x.nasty, prob: x.r.prob, edge: x.edge == null ? -9 : x.edge, heat: x.heat, time: x.r.time, name: x.r.name, slot: x.r.slot, hr: x.r.hr, l15hr: x.r.l15hr, fair: x.r.fair, prevTD: x.r.prevTD, share: x.r.share, implied: x.r.implied, v: x.v, game: x.r.game, pitcher: x.r.pitcher, pos: x.r.pos, spread: x.r.spread, odds: +(store[key(x.r)]||{}).odds || 0, pub: +(store[key(x.r)]||{}).pub || 0, bet: (store[key(x.r)]||{}).on ? 1 : 0, hit: x.r.hit == null ? -1 : x.r.hit })[sortKey];
  list.sort((a, b) => { const A = get(a), B = get(b); return (A > B ? 1 : A < B ? -1 : 0) * sortDir; });
  $('#tbl thead').innerHTML = '<tr>' + COLS[tab].map(([l, k]) => `<th data-k="${k}" class="${k === sortKey ? 'on' : ''}">${l}${k === sortKey ? (sortDir < 0 ? ' ▼' : ' ▲') : ''}</th>`).join('') + '</tr>';
  const tb = $('#tbl tbody'); tb.innerHTML = '';
  const n = { s: 0, v: 0, t: 0, bets: 0, hits: 0, graded: 0, exp: 0, act: 0 };
  for (const x of list) {
    const r = x.r, e = store[key(r)] || {}; if (x.v === 'SLEEPER') n.s++; if (x.v === 'VALUE') n.v++; if (x.v === 'TRAP' || x.v === 'FADE') n.t++;
    if (e.on) n.bets++; if (r.hit != null) { n.graded++; n.exp += r.prob; n.act += r.hit; }
    const when = new Date(r.time).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
    const tr = document.createElement('tr'); tr.className = 'row';
    const common = `<td><span class="nm">${r.name}</span> <span class="tm">${r.team}${r.inj ? ' · ' + r.inj : ''}${r.lateLock ? ' · late lock' : ''}</span></td>`;
    const tail = `<td class="num">${(r.prob * 100).toFixed(1)}%</td><td class="num">${fmtOdds(r.fair)}</td>
      <td><input class="odds" data-k="${key(r)}" data-f="odds" value="${e.odds || ''}" placeholder="${r.book ? fmtOdds(r.book) : '+000'}" title="${r.book ? (r.bookUsed === 'fliff' ? 'Fliff price' : r.bookUsed === 'underdog' ? 'Underdog price (not on Fliff)' : 'not on Fliff or Underdog - best price elsewhere') + (r.bestBook && r.bestBook > r.book ? ', best ' + fmtOdds(r.bestBook) + ' at ' + r.bestAt : '') + (r.move ? ', moved ' + (r.move > 0 ? '+' : '') + r.move + ' pts' : '') : 'type the book odds'}">${r.book && r.bookUsed === 'underdog' ? '<span class="tm">UD</span>' : r.book && r.bookUsed === 'best' ? '<span class="tm">*</span>' : ''}${r.move ? `<span class="tm ${r.move > 0 ? 'neg' : 'pos'}">${r.move > 0 ? '▲' : '▼'}</span>` : ''}</td>
      <td class="num ${x.edge == null ? '' : x.edge >= 0 ? 'pos' : 'neg'}">${x.edge == null ? '—' : (x.edge >= 0 ? '+' : '') + (x.edge * 100).toFixed(1)}</td>
      <td><span class="bar"><i style="width:${x.heat}%"></i></span> <span class="tm">${Math.round(x.heat)}</span></td>
      <td><input class="pub" data-k="${key(r)}" data-f="pub" value="${e.pub || ''}" placeholder="${r.kalshi != null ? Math.round(r.kalshi * 100) + '% $' + (r.kvol >= 1000 ? Math.round(r.kvol / 1000) + 'k' : r.kvol) : r.skew != null ? 'skew ' + (r.skew > 0 ? '+' : '') + r.skew : '%'}" title="${r.kalshi != null ? 'Kalshi: the crowd prices him at ' + Math.round(r.kalshi * 100) + '% with $' + r.kvol.toLocaleString() + ' traded' + (r.kmove ? ', moved ' + (r.kmove > 0 ? '+' : '') + r.kmove + ' pts' : '') + '. Type a real public % to override.' : r.skew != null ? 'retail books minus offshore, in implied %: positive = crowd on him. Type a real public % to override.' : 'type a public bet % if you have one'}">${r.kmove ? `<span class="tm ${r.kmove > 0 ? 'neg' : 'pos'}">${r.kmove > 0 ? '▲' : '▼'}</span>` : ''}</td>
      <td><span class="v ${x.v}">${x.v}</span></td><td class="num">${x.nasty.toFixed(1)}</td>
      <td><input type="checkbox" class="bet" data-k="${key(r)}" data-f="on" ${e.on ? 'checked' : ''} title="paper bet"> <input class="stk" data-k="${key(r)}" data-f="stake" value="${e.stake || ''}" placeholder="1u"></td>
      <td>${resultCell(r)}</td>`;
    if (tab === 'mlb') tr.innerHTML = common + `<td class="num">${r.slot}${r.lineupPosted ? '' : '*'}</td><td class="tm">${r.game.replace(/ at /, ' @ ')}<br>${when}</td><td class="tm">${r.pitcher} (${r.pHand})</td><td class="num">${r.hr} HR / ${r.pa} PA</td><td class="num">${r.l15hr}</td>` + tail;
    else tr.innerHTML = common + `<td>${r.pos}</td><td class="tm">${r.game}<br>${when}</td><td class="tm">${r.spread || '—'} / ${r.total || '—'}</td><td class="num">${r.implied}</td><td class="num">${r.prevTD} in ${r.prevGP}g${r.prevTeam && r.prevTeam !== r.team ? ' (' + r.prevTeam + ')' : ''}</td><td class="num">${(r.share * 100).toFixed(0)}%</td>` + tail;
    const det = document.createElement('tr'); det.className = 'det'; det.hidden = true;
    const facts = r.factors ? Object.entries(r.factors).map(([k, v]) => `<span class="f">${k} ${v}</span>`).join('') : '';
    det.innerHTML = `<td colspan="${COLS[tab].length}">${(r.notes || []).filter(Boolean).join(' &nbsp;|&nbsp; ')}<br>${facts}</td>`;
    tr.addEventListener('click', ev => { if (ev.target.tagName !== 'INPUT') det.hidden = !det.hidden; });
    tb.appendChild(tr); tb.appendChild(det);
  }
  let k = `<div>rows<b>${list.length}</b></div><div>sleepers<b>${n.s}</b></div><div>value<b>${n.v}</b></div><div>traps / fades<b>${n.t}</b></div><div>with a price<b>${list.filter(x => x.edge != null).length}</b></div><div>paper bets<b>${n.bets}</b></div>`;
  if (n.graded) k += `<div>graded<b>${n.graded}</b></div><div>model said<b>${n.exp.toFixed(1)}</b></div><div>actually hit<b>${n.act}</b></div>`;
  $('#kpi').innerHTML = k;
  tb.querySelectorAll('input').forEach(i => i.addEventListener('change', () => { const k = i.dataset.k; store[k] = store[k] || {}; store[k][i.dataset.f] = i.type === 'checkbox' ? i.checked : i.value.trim(); if (i.type === 'checkbox' && i.checked) { store[k].sport = tab; } save(); render(); }));
  $('#tbl thead').querySelectorAll('th').forEach(th => th.addEventListener('click', () => { const k = th.dataset.k; if (sortKey === k) sortDir = -sortDir; else { sortKey = k; sortDir = -1; } render(); }));
}
function applyPaste(){
  const all = [...(PAGE.rows.mlb || []), ...(PAGE.rows.nfl || [])];
  for (const line of $('#paste').value.split('\n')) {
    const m = line.match(/^(.+?)\s+([-+]\d{3,4})(?:\s+(\d{1,3})%?)?\s*$/); if (!m) continue;
    const nm = norm(m[1]); let best = null, bs = 0;
    for (const r of all) { const rn = norm(r.name); let s = 0; if (rn === nm) s = 3; else if (rn.includes(nm) || nm.includes(rn)) s = 2; else if (rn.split(' ').pop() === nm.split(' ').pop()) s = 1; if (s > bs) { bs = s; best = r; } }
    if (best) { const k = key(best); store[k] = store[k] || {}; store[k].odds = m[2]; if (m[3]) store[k].pub = m[3]; }
  }
  save(); render();
}
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => { document.querySelectorAll('.tab').forEach(x => x.classList.remove('on')); t.classList.add('on'); tab = t.dataset.t; render(); }));
['#q', '#minp', '#maxh', '#hidedone', '#onlyplays', '#onlybets'].forEach(s => $(s).addEventListener('input', render));
$('#sort').addEventListener('change', () => { sortKey = $('#sort').value; sortDir = sortKey === 'time' ? 1 : -1; render(); });
$('#apply').addEventListener('click', applyPaste);
$('#clear').addEventListener('click', () => { for (const k of Object.keys(store)) if (k.startsWith(PAGE.datePrefix)) delete store[k]; save(); render(); });
render();
"""

def board_page(title, sub, active, root, rows_mlb, rows_nfl, graded, tabs=True):
    tab = 'mlb' if rows_mlb else 'nfl'
    tabhtml = ''
    if tabs and rows_mlb and rows_nfl: tabhtml = '<div class="tabs"><div class="tab on" data-t="mlb">MLB Home Runs</div><div class="tab" data-t="nfl">NFL Anytime TD</div></div>'
    date_prefix = (rows_mlb or rows_nfl)[0]['date'] if (rows_mlb or rows_nfl) else ''
    page = {'tab': tab, 'graded': graded, 'rows': {'mlb': rows_mlb, 'nfl': rows_nfl}, 'datePrefix': date_prefix}
    return f"""{head(title, sub, active, root)}{tabhtml}
<div class="panel {'' if tabhtml else 'top'}">
<div class="kpi" id="kpi"></div>
<details class="paste"><summary>Paste the book's odds / public bet % (optional)</summary>
<p>One player per line: <code>Kyle Schwarber +165</code> or <code>Schwarber +165 62%</code> (third token = public bet %). Names are fuzzy-matched. Saved in this browser only.</p>
<textarea id="paste" placeholder="Aaron Judge +210 58%&#10;Jahmyr Gibbs -115 71%"></textarea>
<div style="margin-top:6px;display:flex;gap:8px"><button id="apply">Apply</button><button id="clear">Clear this page's entries</button></div>
</details>
<div class="ctl">
<label>search <input type="text" id="q" placeholder="player / team / game"></label>
<label>min model % <input type="number" id="minp" value="0" min="0" max="100" style="width:56px"></label>
<label>max heat <input type="number" id="maxh" value="100" min="0" max="100" style="width:56px"></label>
<label><input type="checkbox" id="hidedone" {'' if graded else 'checked'}> hide started games</label>
<label><input type="checkbox" id="onlyplays"> only SLEEPER / VALUE / TRAP</label>
<label><input type="checkbox" id="onlybets"> only my paper bets</label>
<label>sort <select id="sort"><option value="nasty" {'' if graded else 'selected'}>nasty score</option><option value="prob" {'selected' if graded else ''}>model %</option><option value="edge">edge</option><option value="heat">public heat</option><option value="hit">result</option><option value="time">game time</option></select></label>
</div>
<div class="wrap"><table id="tbl"><thead></thead><tbody></tbody></table></div>
<div class="legend">
<b>Model %</b> = what the numbers say. <b>Fair</b> = the odds that % deserves. <b>Book</b> = the Fliff price, auto-filled (UD = Underdog's price because Fliff doesn't list him; * = neither lists him, best price elsewhere shown; hover for the best price and any line move; ▲ = shortened since the morning pull). Type over it if Fliff shows you something different. <b>Edge</b> = model % minus the book's implied %.
<b>Heat</b> = how crowded the bet is: name recognition + hot streak + narrative, then adjusted by two live signals once odds are flowing: <b>line movement</b> (price shortened since the morning pull = money came in) and <b>book skew</b> (DraftKings / FanDuel / MGM pricing him shorter than Bovada / BetOnline = retail crowd is on him). For MLB the Public column shows <b>Kalshi</b>: the prediction-market crowd's own price for him and how many dollars they've put on it; crowd above the model, heavy volume, or a rising price all raise Heat. Typing a real public-bet % overrides all of it.<br>
<b>SLEEPER</b> = edge with low heat. <b>VALUE</b> = edge, some heat. <b>TRAP</b> = crowd on him, no edge. <b>FADE</b> = public 60%+ and negative edge. <b>CHALK</b> = hot name, no price entered.
<b>Bet</b> = tick to paper-bet him (stake in units, blank = 1u). It's scored on the Track page once the game is final, at the Book odds you typed, or at Fair if you typed none.
</div>
</div>
<script>const PAGE = {jd(page)};{BOARD_JS}</script>"""

TRACK_JS = r"""
const H = HISTORY; let store = {};
try { store = JSON.parse(localStorage.getItem('ftc_bets') || '{}'); } catch (e) {}
const byKey = {}; for (const r of H) byKey[r.date + '|' + r.sport + ':' + r.id] = r;
const pay = (odds, stake, hit) => hit ? stake * (odds > 0 ? odds / 100 : 100 / -odds) : -stake;
const fmt = o => o > 0 ? '+' + o : '' + o;
// ---- your paper bets ----
const bets = [];
for (const [k, e] of Object.entries(store)) { if (!e.on) continue; const r = byKey[k]; if (!r) continue;
  const odds = +e.odds || r.book || r.fair, stake = +e.stake || 1; const settled = r.hit != null && !r.dnp;
  bets.push({ r, odds, stake, atFair: !e.odds && !r.book, settled, pnl: settled ? pay(odds, stake, r.hit) : 0, void: !!r.dnp }); }
bets.sort((a, b) => a.r.date < b.r.date ? -1 : a.r.date > b.r.date ? 1 : 0);
const settled = bets.filter(b => b.settled); const units = settled.reduce((s, b) => s + b.pnl, 0); const staked = settled.reduce((s, b) => s + b.stake, 0);
document.querySelector('#mykpi').innerHTML = `<div>paper bets<b>${bets.length}</b></div><div>settled<b>${settled.length}</b></div><div>record<b>${settled.filter(b => b.r.hit).length}-${settled.filter(b => !b.r.hit).length}</b></div><div>units<b class="${units >= 0 ? 'pos' : 'neg'}">${units >= 0 ? '+' : ''}${units.toFixed(2)}</b></div><div>ROI<b class="${units >= 0 ? 'pos' : 'neg'}">${staked ? (units / staked * 100).toFixed(1) : '0.0'}%</b></div><div>pending<b>${bets.filter(b => !b.settled && !b.void).length}</b></div>`;
const led = document.querySelector('#ledger');
if (!bets.length) led.innerHTML = '<div class="empty">No paper bets yet. Open any day page, tick the Bet box next to a player, type the book odds if you have them, and it shows up here.</div>';
else { let run = 0; led.innerHTML = '<div class="wrap"><table><thead><tr><th>Date</th><th>Player</th><th>Game</th><th>Model %</th><th>Heat</th><th>Odds</th><th>Stake</th><th>Result</th><th>P/L</th><th>Running</th></tr></thead><tbody>' +
  bets.map(b => { if (b.settled) run += b.pnl; return `<tr><td class="tm">${b.r.date}</td><td><span class="nm">${b.r.name}</span> <span class="tm">${b.r.team}</span></td><td class="tm">${b.r.game}</td><td class="num">${(b.r.prob * 100).toFixed(1)}%</td><td class="num">${Math.round(b.r.heat)}</td><td class="num">${fmt(b.odds)}${b.atFair ? ' <span class="tm">fair</span>' : ''}</td><td class="num">${b.stake}u</td><td>${b.void ? '<span class="res d">void</span>' : !b.settled ? '<span class="res n">pending</span>' : b.r.hit ? '<span class="res y">✓ hit</span>' : '<span class="res n">✗ miss</span>'}</td><td class="num ${b.pnl >= 0 ? 'pos' : 'neg'}">${b.settled ? (b.pnl >= 0 ? '+' : '') + b.pnl.toFixed(2) : '—'}</td><td class="num ${run >= 0 ? 'pos' : 'neg'}">${b.settled ? (run >= 0 ? '+' : '') + run.toFixed(2) : ''}</td></tr>`; }).join('') + '</tbody></table></div>'; }
// ---- model strategies at fair odds ----
const G = H.filter(r => r.hit != null && !r.dnp && r.sport === 'MLB');
const dates = [...new Set(G.map(r => r.date))].sort();
const strat = {
  'Top 5 by model %': d => G.filter(r => r.date === d).sort((a, b) => b.prob - a.prob).slice(0, 5),
  'Top 10 by model %': d => G.filter(r => r.date === d).sort((a, b) => b.prob - a.prob).slice(0, 10),
  'Sleepers (20%+, heat < 35)': d => G.filter(r => r.date === d && r.prob >= .2 && r.heat < 35),
  'Chalk (20%+, heat 60+)': d => G.filter(r => r.date === d && r.prob >= .2 && r.heat >= 60),
  'Everyone 20%+': d => G.filter(r => r.date === d && r.prob >= .2),
};
const curves = {}; let rowsHtml = '';
for (const [name, fn] of Object.entries(strat)) { let bets = 0, hits = 0, pnl = 0, exp = 0; const curve = [0];
  for (const d of dates) { for (const r of fn(d)) { bets++; hits += r.hit; exp += r.prob; pnl += pay(r.fair, 1, r.hit); } curve.push(pnl); }
  curves[name] = curve;
  rowsHtml += `<tr><td class="nm">${name}</td><td class="num">${bets}</td><td class="num">${hits}-${bets - hits}</td><td class="num">${bets ? (hits / bets * 100).toFixed(1) : 0}%</td><td class="num">${bets ? (exp / bets * 100).toFixed(1) : 0}%</td><td class="num ${pnl >= 0 ? 'pos' : 'neg'}">${pnl >= 0 ? '+' : ''}${pnl.toFixed(1)}u</td><td class="num ${pnl >= 0 ? 'pos' : 'neg'}">${bets ? (pnl / bets * 100).toFixed(1) : 0}%</td></tr>`; }
document.querySelector('#strat tbody').innerHTML = rowsHtml;
// ---- calibration + heat ----
const bk = [[0, .08], [.08, .12], [.12, .16], [.16, .20], [.20, .25], [.25, 1]];
document.querySelector('#calib tbody').innerHTML = bk.map(([lo, hi]) => { const b = G.filter(r => r.prob >= lo && r.prob < hi); if (!b.length) return ''; const p = b.reduce((s, r) => s + r.prob, 0) / b.length, a = b.reduce((s, r) => s + r.hit, 0) / b.length; return `<tr><td>${(lo * 100).toFixed(0)}–${hi === 1 ? '100' : (hi * 100).toFixed(0)}%</td><td class="num">${b.length}</td><td class="num">${(p * 100).toFixed(1)}%</td><td class="num">${(a * 100).toFixed(1)}%</td><td class="num ${a >= p ? 'pos' : 'neg'}">${((a - p) * 100 >= 0 ? '+' : '')}${((a - p) * 100).toFixed(1)}</td></tr>`; }).join('');
const hb = [[0, 35, 'Cold (< 35)'], [35, 60, 'Warm (35–60)'], [60, 101, 'Hot (60+)']];
document.querySelector('#heat tbody').innerHTML = hb.map(([lo, hi, lab]) => { const b = G.filter(r => r.heat >= lo && r.heat < hi); if (!b.length) return ''; const p = b.reduce((s, r) => s + r.prob, 0), a = b.reduce((s, r) => s + r.hit, 0); return `<tr><td>${lab}</td><td class="num">${b.length}</td><td class="num">${(p / b.length * 100).toFixed(1)}%</td><td class="num">${(a / b.length * 100).toFixed(1)}%</td><td class="num ${a / p >= 1 ? 'pos' : 'neg'}">${(a / p).toFixed(2)}</td></tr>`; }).join('');
// ---- kalshi volume terciles ----
const K = G.filter(r => r.kalshi != null && r.kvol != null);
if (K.length) { const vs = K.map(r => r.kvol).sort((a, b) => a - b); const t1 = vs[Math.floor(vs.length / 3)], t2 = vs[Math.floor(vs.length * 2 / 3)];
  const kb = [[0, t1, 'Light money'], [t1, t2, 'Medium'], [t2, 1e12, 'Heavy money']];
  document.querySelector('#kvol tbody').innerHTML = kb.map(([lo, hi, lab]) => { const b = K.filter(r => r.kvol >= lo && r.kvol < hi); if (!b.length) return ''; const p = b.reduce((s, r) => s + r.prob, 0), c = b.reduce((s, r) => s + r.kalshi, 0), a = b.reduce((s, r) => s + r.hit, 0); return `<tr><td>${lab}</td><td class="num">${b.length}</td><td class="num">${(p / b.length * 100).toFixed(1)}%</td><td class="num">${(c / b.length * 100).toFixed(1)}%</td><td class="num">${(a / b.length * 100).toFixed(1)}%</td><td class="num ${a / c >= 1 ? 'pos' : 'neg'}">${(a / c).toFixed(2)}</td></tr>`; }).join(''); }
else document.querySelector('#kvol tbody').innerHTML = '<tr><td colspan="6" class="tm">No graded days with Kalshi data yet. Fills in from tomorrow.</td></tr>';
// ---- chart ----
const svg = document.querySelector('#chart'); const W = 800, Hh = 220, pad = 34;
const series = [['Top 5 by model %', '#ffb020'], ['Sleepers (20%+, heat < 35)', '#2fd47a'], ['Chalk (20%+, heat 60+)', '#ff4d5e']];
let myCurve = [0]; { let run = 0; for (const d of dates) { for (const b of settled) if (b.r.date === d) run += b.pnl; myCurve.push(run); } }
const all = [...series.map(s => curves[s[0]]), myCurve].flat(); const mn = Math.min(0, ...all), mx = Math.max(1, ...all);
const X = i => pad + i * (W - pad * 2) / Math.max(1, dates.length), Y = v => Hh - pad + (v - mn) * -(Hh - pad * 2) / (mx - mn || 1);
let g = `<line x1="${pad}" x2="${W - pad}" y1="${Y(0)}" y2="${Y(0)}" stroke="#2b3440"/>`;
for (const [name, col] of series) g += `<polyline fill="none" stroke="${col}" stroke-width="2" points="${curves[name].map((v, i) => X(i) + ',' + Y(v)).join(' ')}"/>`;
if (settled.length) g += `<polyline fill="none" stroke="#e6e9ee" stroke-width="2.5" stroke-dasharray="5 4" points="${myCurve.map((v, i) => X(i) + ',' + Y(v)).join(' ')}"/>`;
dates.forEach((d, i) => { if (i % Math.ceil(dates.length / 8) === 0) g += `<text x="${X(i + 1)}" y="${Hh - 10}" fill="#8a94a3" font-size="10" text-anchor="middle">${d.slice(5)}</text>`; });
g += `<text x="${pad}" y="${Y(mx) + 4}" fill="#8a94a3" font-size="10">${mx >= 0 ? '+' : ''}${mx.toFixed(0)}u</text><text x="${pad}" y="${Y(mn) - 2}" fill="#8a94a3" font-size="10">${mn.toFixed(0)}u</text>`;
svg.innerHTML = g;
document.querySelector('#chartlegend').innerHTML = series.map(([n, c]) => `<span style="color:${c}">■</span> ${n}`).join(' &nbsp; ') + (settled.length ? ' &nbsp; <span style="color:#e6e9ee">┅</span> your paper bets' : '');
"""

def track_page():
    n_days = len([d for d, rows in days.items() if any(r['hit'] is not None for r in rows)])
    return f"""{head('Fade The Chalk', 'paper-bet ledger + how the model is doing at fair odds', 'track.html', '')}
<div class="panel top">
<h2>Your paper bets <small>ticked on the day pages, kept in this browser, scored when games go final</small></h2>
<div class="kpi" id="mykpi"></div>
<div id="ledger"></div>
<h2>Model strategies at fair odds <small>{n_days} graded MLB days · flat 1u · fair = the odds the model's own % implies, so a real book pays less than this</small></h2>
<svg class="chart" id="chart" viewBox="0 0 800 220" preserveAspectRatio="none"></svg>
<div class="note" id="chartlegend" style="margin:6px 0 12px"></div>
<div class="wrap"><table id="strat"><thead><tr><th>Strategy</th><th>Bets</th><th>Record</th><th>Hit %</th><th>Model said</th><th>Units</th><th>ROI</th></tr></thead><tbody></tbody></table></div>
<div class="grid2" style="margin-top:18px">
<div class="mini"><h2>Calibration <small>does 25% mean 25%?</small></h2><div class="wrap"><table id="calib"><thead><tr><th>Model %</th><th>n</th><th>Predicted</th><th>Actual</th><th>Diff</th></tr></thead><tbody></tbody></table></div></div>
<div class="mini"><h2>The rigged test, Kalshi money <small>hitters with the most public dollars on them: do they underperform?</small></h2><div class="wrap"><table id="kvol"><thead><tr><th>Kalshi volume</th><th>n</th><th>Model said</th><th>Crowd said</th><th>Actual</th><th>Actual ÷ crowd</th></tr></thead><tbody></tbody></table></div></div>
<div class="mini"><h2>The rigged test, heat <small>do the crowd's names underperform their own numbers?</small></h2><div class="wrap"><table id="heat"><thead><tr><th>Heat</th><th>n</th><th>Predicted</th><th>Actual</th><th>Actual ÷ predicted</th></tr></thead><tbody></tbody></table></div></div>
</div>
<p class="note" style="margin-top:14px">Picks are locked before first pitch and graded from box scores afterward; results never change a lock. Days before {min(days) if days else ''} were reconstructed from posted lineups with season stats as of the build, which leaks a little. Model v2 (from 2026-09-12): base rate regressed less toward league, weak hitters dampened, level scaled 0.92 - fitted on those same days, so judge it on days after that.</p>
</div>
<script>const HISTORY = {jd(HISTORY)};{TRACK_JS}</script>"""

W = lambda path, html: open(os.path.join(SITE, path), 'w', encoding='utf-8', newline='\n').write(html)
gen = board['generated']
for r in board['mlb']: r.setdefault('date', today)
for r in board['nfl']: r.setdefault('date', 'now')
# today's page: use the locked rows for today if present (so results show once graded), else the live board
today_rows = days.get(today, board['mlb'])
W('index.html', board_page('Fade The Chalk', f'MLB HR + NFL anytime TD · model prob vs. the price vs. the crowd · built {gen}', 'index.html', '', today_rows, board['nfl'], False))
for d, rows in days.items():
    graded = any(r['hit'] is not None for r in rows)
    W(f'days/{d}.html', board_page('Fade The Chalk', f'MLB home runs · {d} · {"results graded" if graded else "waiting on results"} · picks locked pre-game', 'days/' + d, '../', rows, [], graded, tabs=False))
for w, rows in weeks.items():
    graded = any(r['hit'] is not None for r in rows)
    W(f'nfl/{w}.html', board_page('Fade The Chalk', f'NFL anytime TD · {w.replace("_", " ")} · {"results graded" if graded else "waiting on results"}', 'nfl/' + w, '../', [], rows, graded, tabs=False))
W('track.html', track_page())
open(os.path.join(SITE, '.nojekyll'), 'w').close()
print(f"site: index + {len(days)} day pages + {len(weeks)} nfl pages + track -> {SITE}")
