"""Render docs/book.html: for every NFL game, what the book makes in each of the three results (favorite covers / favorite wins but doesn't cover /
underdog wins outright), from all of the crowd's taker $ on Robinhood's spread and moneyline (backtest/lines_<week>.json + ml_<week>.json).
The book keeps every losing stake and pays every winner's profit (stake x (1-p)/p at the ask). One card per game, easiest-to-read first."""
import json, os, re, glob, datetime
from zoneinfo import ZoneInfo
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); SITE = os.path.join(HERE, 'docs')
J = lambda p: json.load(open(p, encoding='utf-8'))
src = open(os.path.join(HERE, 'build_site.py'), encoding='utf-8').read()
CSS = re.search(r'CSS = r"""(.*?)"""', src, re.S).group(1); FONTS = re.search(r"FONTS = '(.*?)'", src).group(1)
PT = ZoneInfo('America/Los_Angeles')

def prime(t):
    d = datetime.datetime.fromisoformat(t.replace('Z', '+00:00')).astimezone(PT)
    return d.strftime('%a') in ('Thu', 'Mon', 'Fri', 'Sat') or (d.strftime('%a') == 'Sun' and d.hour >= 17)

def board_verdict(s, fav_side, t):
    """the spread verdict build_lines.py shows (keep in sync): the side with less of the spread $; PASS under $100k (wait), STRONG BET in primetime, BET at $300k+"""
    sf, sd = s.get('tapeFav$', 0), s.get('tapeDog$', 0); tot = sf + sd
    if not tot: return None, None
    side = fav_side if sf < sd else 'dog'
    v = 'PASS (wait)' if tot < 100000 else 'STRONG BET' if prime(t) else 'BET' if tot >= 300000 else 'PASS'
    return side, v

def game(r, m):
    s = r.get('spread') or {}
    if not s.get('ticker') or not m or m.get('takerHome$') is None or not m.get('kalshiAsk') or not m.get('kalshiAwayAsk') or not s.get('favAsk') or not s.get('dogAsk'): return None
    fh = s['fav'] == r['home']; fav, dog, line = s['fav'], s['dog'], s['line']
    W = lambda S, p: S * (1 - p) / p
    bets = [  # (label, team, $, price)
        (f'{fav} −{line}', fav, s.get('tapeFav$', 0), s['favAsk']), (f'{dog} +{line}', dog, s.get('tapeDog$', 0), s['dogAsk']),
        (f'{fav} ML', fav, m['takerHome$'] if fh else m['takerAway$'], m['kalshiAsk'] if fh else m['kalshiAwayAsk']),
        (f'{dog} ML', dog, m['takerAway$'] if fh else m['takerHome$'], m['kalshiAwayAsk'] if fh else m['kalshiAsk'])]
    sf, sd, mf, md = (b[2] or 0 for b in bets); pays = [W(b[2] or 0, b[3]) for b in bets]
    outs = [  # (result, winners, keep, pay)
        (f'{fav} wins by {int(line + .5)}+ (covers)', (0, 2)), (f'{fav} wins by 1–{int(line - .5)} ({dog} covers)' if line > 1 else None, (1, 2)), (f'{dog} wins outright', (1, 3))]
    res = []
    for lab, win in outs:
        if lab is None: continue
        keep = sum((bets[i][2] or 0) for i in range(4) if i not in win); pay = sum(pays[i] for i in win)
        res.append({'lab': lab, 'keep': keep, 'pay': pay, 'net': keep - pay, 'k': len(res) if lab else None, 'favCovers': win == (0, 2)})
    nets = [x['net'] for x in res]; best = nets.index(max(nets)); worst = nets.index(min(nets))
    act = None
    if r.get('finalHome') is not None:
        mar = (r['finalHome'] - r['finalAway']) * (1 if fh else -1)
        act = 0 if mar > line else (len(res) - 1 if mar < 0 else (1 if len(res) == 3 and mar > 0 else None))
    winners = [x for x in res if x['net'] > 0]
    if len(winners) == 1: head, shape = f"Book wins only if {winners[0]['lab'].split(' (')[0]}", 'one'
    elif len(winners) == len(res): head, shape = 'Book wins whatever happens', 'all'
    elif not winners: head, shape = 'Book loses whatever happens', 'none'
    else: head, shape = f"Book wins unless {res[worst]['lab'].split(' (')[0]}", 'two'
    book_side = f'{fav} −{line}' if res[best]['favCovers'] else f'{dog} +{line}'
    bs, bv = board_verdict(s, 'fav', r['time']); board = None if bs is None else (f'{fav} −{line}' if bs == 'fav' else f'{dog} +{line}')
    cover = s.get('favCovered'); hit = lambda side: None if cover is None else int((side.startswith(fav + ' ')) == bool(cover))
    team_all = {fav: sf + mf, dog: sd + md}
    return {'g': f"{r['away']} @ {r['home']}", 'time': r['time'], 'prime': prime(r['time']), 'at': r.get('at') or m.get('takerAt'), 'fav': fav, 'dog': dog, 'line': line,
            'bets': [(b[0], b[2] or 0, b[3], p) for b, p in zip(bets, pays)], 'res': res, 'best': best, 'worst': worst, 'act': act, 'head': head, 'shape': shape,
            'bookSide': book_side, 'bookHit': hit(book_side), 'board': board, 'boardV': bv, 'boardHit': hit(board) if board else None, 'all': team_all,
            'final': None if r.get('finalHome') is None else f"{r['away']} {r['finalAway']} – {r['home']} {r['finalHome']}"}

weeks = {}
for lf in sorted(glob.glob(os.path.join(BT, 'lines_20*_wk*.json'))):
    tag = os.path.basename(lf)[6:-5]; mp = os.path.join(BT, f'ml_{tag}.json')
    if not os.path.exists(mp): continue
    ml = {x.get('eventId'): x for x in J(mp) if x.get('sport') == 'NFL'}
    gs = [g for g in (game(r, ml.get(r.get('eventId'))) for r in J(lf) if r.get('sport') == 'NFL') if g]
    if gs: weeks[tag] = sorted(gs, key=lambda g: g['time'])
order = sorted(weeks, key=lambda w: int(w.split('wk')[1]), reverse=True)

money = lambda v: ('−' if v < 0 else '') + '$' + (f'{abs(v) / 1e6:.2f}M' if abs(v) >= 1e6 else f'{abs(v) / 1e3:.0f}k' if abs(v) >= 1000 else f'{abs(v):.0f}')
signed = lambda v: ('+' if v >= 0 else '') + money(v)
cents = lambda p: f'{round(p * 100)}¢'
res_tag = lambda h: '' if h is None else ('<span class="res y">✓</span>' if h else '<span class="res n">✗</span>')

def rec(gs, key):
    hs = [g[key] for g in gs if g[key] is not None]; return f"{sum(hs)}-{len(hs) - sum(hs)}" if hs else '—'

def card(g):
    rows = ''.join(f'<tr><td>{lab}</td><td class="num">{money(st)}</td><td class="num">{cents(p)}</td><td class="num">{money(w)}</td></tr>' for lab, st, p, w in g['bets'])
    outs = ''.join(f'<tr class="{"best" if i == g["best"] else ""}{" act" if i == g["act"] else ""}"><td>{x["lab"]}{" <b class=tagb>book’s best</b>" if i == g["best"] else ""}{" <b class=taga>✔ happened</b>" if i == g["act"] else ""}</td>'
                   f'<td class="num">{money(x["keep"])}</td><td class="num">{money(x["pay"])}</td><td class="num"><b class="{"pos" if x["net"] >= 0 else "neg"}">{signed(x["net"])}</b></td></tr>' for i, x in enumerate(g['res']))
    tot = sum(g['all'].values()) or 1
    allm = ' · '.join(f'{t} {money(v)} ({v / tot:.0%})' for t, v in sorted(g['all'].items(), key=lambda kv: -kv[1]))
    agree = g['board'] and g['board'] == g['bookSide']
    return f'''<div class="card {'done' if g['final'] else ''}" data-done="{1 if g['final'] else 0}">
<div class="ch"><div><span class="gm">{g['g']}</span> <span class="tm" data-t="{g['time']}"></span>{' 🌙' if g['prime'] else ''}<br><span class="tm">spread {g['fav']} −{g['line']} · money as of <span data-t="{g['at']}"></span></span></div>
<div class="fin">{g['final'] or ''}</div></div>
<div class="head {g['shape']}">{g['head']}</div>
<div class="two"><div><h4>The money</h4><table class="bt"><thead><tr><th>Bet</th><th class="num">$ on it</th><th class="num">Price</th><th class="num">Profit if it wins</th></tr></thead><tbody>{rows}</tbody></table></div>
<div><h4>What the book makes</h4><table class="bt"><thead><tr><th>Result</th><th class="num">Keeps</th><th class="num">Pays</th><th class="num">Book net</th></tr></thead><tbody>{outs}</tbody></table></div></div>
<div class="foot"><span>Book’s side: <b>{g['bookSide']}</b> {res_tag(g['bookHit'])}</span><span>Board: <b>{(g['boardV'] + ' ' + g['board']) if g['board'] else '—'}</b> {res_tag(g['boardHit']) if g['boardV'] and not g['boardV'].startswith('PASS') else ''}{' <span class="agree">same side</span>' if agree else ' <span class="split">different sides</span>' if g['board'] else ''}</span><span class="tm">all $ (spread + ML): {allm}</span></div></div>'''

def week_html(w):
    gs = weeks[w]; done = [g for g in gs if g['act'] is not None]
    nb = sum(g['act'] == g['best'] for g in done); net = sum(g['res'][g['act']]['net'] for g in done)
    k = f'<div class="kpi"><div>games<b>{len(gs)}</b></div>' + (f'<div>book’s best happened<b>{nb} of {len(done)}</b></div><div>book net<b class="{"pos" if net >= 0 else "neg"}">{signed(net)}</b></div><div>book’s side covered<b>{rec(gs, "bookHit")}</b></div>' if done else '') + '</div>'
    return f'<div class="wk" data-w="{w}" hidden>{k}' + ''.join(card(g) for g in gs) + '</div>'

allg = [g for w in weeks for g in weeks[w]]
def season_row(name, gs):
    done = [g for g in gs if g['bookHit'] is not None]; w = sum(g['bookHit'] for g in done)
    units = sum((1 / g['bets'][0 if g['bookSide'].startswith(g['fav'] + ' ') else 1][2] - 1) if g['bookHit'] else -1 for g in done)
    return f'<tr><td>{name}</td><td class="num">{w}-{len(done) - w}</td><td class="num {"pos" if units >= 0 else "neg"}">{units:+.1f}u</td></tr>' if done else ''
season = ''.join([season_row('Every game: bet the book’s side', allg), season_row('Book wins only one way', [g for g in allg if g['shape'] == 'one']),
                  season_row('Book wins unless one result', [g for g in allg if g['shape'] == 'two']), season_row('Primetime 🌙', [g for g in allg if g['prime']]),
                  season_row('Book’s side = the board’s pick', [g for g in allg if g['board'] == g['bookSide']]), season_row('Book’s side ≠ the board’s pick', [g for g in allg if g['board'] and g['board'] != g['bookSide']])])
done_all = [g for g in allg if g['act'] is not None]
best_all = sum(g['act'] == g['best'] for g in done_all); net_all = sum(g['res'][g['act']]['net'] for g in done_all)

STYLE = """<style>
.card{background:var(--panel,#151a21);border:1px solid rgba(128,128,128,.25);border-radius:12px;padding:14px 16px;margin:12px 0}
.card.done{opacity:.85}.ch{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.gm{font-weight:700;font-size:1.1em}.fin{font-weight:700;white-space:nowrap}
.head{margin:10px 0;padding:8px 12px;border-radius:8px;font-weight:700;font-size:1.05em;background:rgba(224,160,48,.15)}
.head.one{background:rgba(76,175,80,.16)}.head.none,.head.all{background:rgba(128,128,128,.15)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}.two>div{min-width:0;overflow-x:auto}@media(max-width:820px){.two{grid-template-columns:1fr}}
@media(max-width:520px){.card{padding:12px}table.bt{font-size:.82em}table.bt th,table.bt td{padding:4px 3px}.ch{flex-direction:column;gap:4px}}
h4{margin:4px 0 6px;font-size:.85em;text-transform:uppercase;letter-spacing:.04em;opacity:.7}
table.bt{width:100%;min-width:0;border-collapse:collapse;font-size:.92em}table.bt th,table.bt td{padding:5px 6px;border-bottom:1px solid rgba(128,128,128,.18);text-align:left}table.bt .num{text-align:right}
tr.best td{background:rgba(224,160,48,.13)}tr.act td{background:rgba(76,175,80,.16)}b.tagb,b.taga{font-size:.75em;padding:1px 6px;border-radius:6px;margin-left:4px;white-space:nowrap}
b.tagb{background:rgba(224,160,48,.3)}b.taga{background:rgba(76,175,80,.35)}
.foot{display:flex;flex-wrap:wrap;gap:8px 20px;margin-top:10px;align-items:center}.agree{color:#4caf50;font-size:.85em}.split{color:#e0a030;font-size:.85em}
.ctl{display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin:8px 0}
</style>"""

def page():
    from navbar import navbar
    opts = ''.join(f'<option value="{w}">Week {w.split("wk")[1]}</option>' for w in order)
    return f"""<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fade The Chalk · Book</title>{FONTS}{CSS}{STYLE}
<header><h1><a href="index.html">FADE THE <span>CHALK</span></a></h1><div class="sub">what the book needs · NFL · built {datetime.datetime.now().isoformat(timespec="minutes")}</div></header>{navbar('book', '', None, None, 'nfl')}
<div class="panel top">
<p class="note">For every NFL game: all the crowd’s money on Robinhood’s spread and moneyline, and what the book makes in each of the three results. The book keeps every losing bet and pays every winner’s profit. <b>Book’s side</b> = the spread bet that wins in the book’s best result. <b>Board</b> = the verdict on the Spreads page (fade the spread money). Green headline = the book wins only one way.</p>
<div class="ctl"><label>week <select id="wk">{opts}</select></label><label><input type="checkbox" id="hidedone"> hide finished games</label></div>
{''.join(week_html(w) for w in order)}
<h2 class="mk" style="margin-top:22px">Season so far <small>{len(done_all)} graded games · book’s best result happened {best_all} ({best_all / max(1, len(done_all)):.0%}; chance ≈ 33%) · book net {signed(net_all)}</small></h2>
<div class="wrap"><table class="bt" style="max-width:560px"><thead><tr><th>Bet the book’s side when…</th><th class="num">Record</th><th class="num">1 unit each</th></tr></thead><tbody>{season}</tbody></table></div>
<p class="note">Small samples: a few weeks of games. A cross-check on the board, not a separate pick.</p>
</div>
<script>
const $ = s => document.querySelector(s);
document.querySelectorAll('[data-t]').forEach(e => {{ const t = e.dataset.t; if (t && t !== 'None') e.textContent = new Date(t.replace(/([+-]\\d\\d:\\d\\d|Z)?$/, m => m || 'Z')).toLocaleString([], {{ weekday: 'short', hour: 'numeric', minute: '2-digit' }}); }});
function show(){{ const w = $('#wk').value, hd = $('#hidedone').checked; try {{ localStorage.setItem('ftc_book', JSON.stringify({{ w, hd }})); }} catch (e) {{}}
  document.querySelectorAll('.wk').forEach(d => d.hidden = d.dataset.w !== w); document.querySelectorAll('.card').forEach(c => c.hidden = hd && c.dataset.done === '1'); }}
try {{ const s = JSON.parse(localStorage.getItem('ftc_book') || '{{}}'); if (s.hd) $('#hidedone').checked = true; }} catch (e) {{}}
$('#wk').addEventListener('input', show); $('#hidedone').addEventListener('input', show); show();
</script>"""

if weeks:
    os.makedirs(SITE, exist_ok=True)
    open(os.path.join(SITE, 'book.html'), 'w', encoding='utf-8').write(page())
    print(f"book.html: {len(order)} NFL weeks, {len(allg)} games")
