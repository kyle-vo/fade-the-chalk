"""Render output/board.json into a self-contained output/board.html (paste book odds + public %, get verdicts)."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, 'output')
board = json.load(open(os.path.join(OUT, 'board.json'), encoding='utf-8'))

TEMPLATE = r"""<meta charset="utf-8">
<title>Fade The Chalk</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;800&family=IBM+Plex+Sans:wght@400;600;700&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>
:root{--bg:#0b0d10;--panel:#14181e;--line:#232a33;--ink:#e6e9ee;--mute:#8a94a3;--acc:#ffb020;--good:#2fd47a;--bad:#ff4d5e;--warn:#ffb020;--blue:#4aa3ff;--font:"IBM Plex Sans",ui-sans-serif,system-ui,"Segoe UI",sans-serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;--disp:"Barlow Condensed","Arial Narrow",Impact,sans-serif;color-scheme:dark}
body{background:var(--bg);color:var(--ink);font-family:var(--font);margin:0;padding:0 0 60px}
header{padding:22px 26px 12px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:14px;align-items:baseline}
h1{margin:0;font-family:var(--disp);font-size:34px;font-weight:800;letter-spacing:1.5px;line-height:1}h1 span{color:var(--acc)}
.sub{color:var(--mute);font-size:13px}
.tabs{display:flex;gap:6px;padding:14px 26px 0}
.tab{font-family:var(--disp);font-size:17px;letter-spacing:.6px;text-transform:uppercase;padding:8px 16px;border:1px solid var(--line);border-bottom:none;border-radius:8px 8px 0 0;background:var(--panel);color:var(--mute);cursor:pointer;font-weight:600}
.tab.on{color:var(--ink);background:#1b2129;border-color:#2f3944}
.panel{margin:0 26px;border:1px solid var(--line);background:var(--panel);border-radius:0 10px 10px 10px;padding:14px}
.ctl{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px;font-size:13px}
.ctl input[type=text],.ctl input[type=number],.ctl select{background:#0e1115;border:1px solid var(--line);color:var(--ink);padding:6px 8px;border-radius:6px;font:inherit}
.ctl label{color:var(--mute)}
textarea{width:100%;box-sizing:border-box;background:#0e1115;color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:8px;font:12px var(--mono);min-height:64px}
details.paste{margin-bottom:12px;font-size:13px;color:var(--mute)}details.paste summary{cursor:pointer;color:var(--ink);font-weight:600}
button{background:#1b2129;border:1px solid #2f3944;color:var(--ink);padding:6px 12px;border-radius:6px;cursor:pointer;font:inherit}button:hover{border-color:var(--acc)}
.wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:1100px}
th{font-size:11px;text-transform:uppercase;letter-spacing:.6px;position:sticky;top:0;background:#1b2129;text-align:left;padding:8px 8px;border-bottom:1px solid var(--line);color:var(--mute);font-weight:600;cursor:pointer;white-space:nowrap}
th.on{color:var(--acc)}
td{padding:7px 8px;border-bottom:1px solid #1a2028;vertical-align:middle;white-space:nowrap}
tr.row:hover td{background:#181e26}
td.num{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right}
.nm{font-weight:700}.tm{color:var(--mute);font-size:12px}
input.odds,input.pub{width:64px;background:#0e1115;border:1px solid var(--line);color:var(--ink);padding:4px 6px;border-radius:5px;font:12px var(--mono);text-align:right}
.bar{display:inline-block;height:8px;border-radius:4px;background:#2b3440;width:70px;vertical-align:middle;position:relative;overflow:hidden}.bar i{position:absolute;left:0;top:0;bottom:0;background:linear-gradient(90deg,#4aa3ff,#ff4d5e)}
.v{display:inline-block;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:800;letter-spacing:.4px}
.v.SLEEPER{background:#123d26;color:var(--good)}.v.VALUE{background:#12304a;color:var(--blue)}.v.TRAP{background:#4a1218;color:var(--bad)}.v.FADE{background:#4a1218;color:var(--bad)}.v.CHALK{background:#463610;color:var(--warn)}.v.PASS{background:#20262e;color:var(--mute)}.v.DONE{background:#20262e;color:var(--mute)}
.pos{color:var(--good)}.neg{color:var(--bad)}
tr.det td{background:#0e1115;color:var(--mute);white-space:normal;font-size:12px;padding:8px 14px 10px}
tr.det .f{display:inline-block;margin:2px 10px 2px 0;font-family:var(--mono)}
.legend{font-size:12px;color:var(--mute);margin:10px 0 0;line-height:1.7}
.legend b{color:var(--ink)}
.kpi{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}.kpi div{background:#0e1115;border:1px solid var(--line);border-radius:8px;padding:8px 12px;font-size:12px;color:var(--mute)}.kpi b{display:block;font-size:22px;color:var(--ink);font-family:var(--disp);font-weight:800;letter-spacing:.5px}
@media(max-width:700px){header,.tabs,.panel{padding-left:10px;padding-right:10px}.panel{margin:0 6px}}
</style>
<header><h1>FADE THE <span>CHALK</span></h1><div class="sub">MLB HR + NFL anytime TD | model prob vs. the price vs. the crowd | generated __GEN__</div></header>
<div class="tabs"><div class="tab on" data-t="mlb">MLB Home Runs</div><div class="tab" data-t="nfl">NFL Anytime TD</div></div>
<div class="panel">
<div class="kpi" id="kpi"></div>
<details class="paste"><summary>Paste the book's odds board / public bet % (optional)</summary>
<p>One player per line: <code>Kyle Schwarber +165</code> or <code>Schwarber +165 62%</code> (third token = public bet %). Names are fuzzy-matched. Saved in this browser.</p>
<textarea id="paste" placeholder="Aaron Judge +210 58%&#10;Jahmyr Gibbs -115 71%"></textarea>
<div style="margin-top:6px;display:flex;gap:8px"><button id="apply">Apply</button><button id="clear">Clear all entered odds</button></div>
</details>
<div class="ctl">
<label>search <input type="text" id="q" placeholder="player / team / game"></label>
<label>min model % <input type="number" id="minp" value="0" min="0" max="100" style="width:56px"></label>
<label>max heat <input type="number" id="maxh" value="100" min="0" max="100" style="width:56px"></label>
<label><input type="checkbox" id="hidedone" checked> hide finished / live games</label>
<label><input type="checkbox" id="onlyplays"> only SLEEPER / VALUE / TRAP</label>
<label>sort <select id="sort"><option value="nasty">nasty score</option><option value="prob">model %</option><option value="edge">edge</option><option value="heat">public heat</option><option value="time">game time</option></select></label>
</div>
<div class="wrap"><table id="tbl"><thead></thead><tbody></tbody></table></div>
<div class="legend">
<b>Model %</b> = what the numbers say. <b>Fair</b> = the odds that % deserves. <b>Book</b> = what you were offered (type it). <b>Edge</b> = model % minus the book's implied %.
<b>Heat</b> = how obvious / over-bet the name is today (leaderboard rank, hot streak, narrative park, primetime). Enter a real public-bet % and it replaces heat.<br>
<b>SLEEPER</b> = edge with low heat (nobody's on him). <b>VALUE</b> = edge, some heat. <b>TRAP</b> = crowd is on him and the price has no edge. <b>FADE</b> = public 60%+ and negative edge. <b>CHALK</b> = hot name, no price entered yet - get a number before touching it.
<b>Nasty score</b> = model % + 1.5x edge - a penalty for how much the crowd is on him. The whole point: if the world is on one guy, the price already ate the value.
</div>
</div>
<script>
const BOARD = __BOARD__;
const $ = s => document.querySelector(s);
let tab = 'mlb', sortKey = 'nasty', sortDir = -1;
let entered = {};
try { entered = JSON.parse(localStorage.getItem('ftc_odds') || '{}'); } catch (e) { entered = {}; }
function saveEntered(){ try { localStorage.setItem('ftc_odds', JSON.stringify(entered)); } catch (e) {} }
const norm = s => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z ]/g, '').replace(/\s+/g, ' ').trim();
const implied = o => { o = +o; if (!o || isNaN(o)) return null; return o < 0 ? (-o) / (-o + 100) : 100 / (o + 100); };
const amer = p => { p = Math.min(Math.max(p, .005), .995); return p >= .5 ? Math.round(-100 * p / (1 - p)) : Math.round(100 * (1 - p) / p); };
const fmtOdds = o => o > 0 ? '+' + o : '' + o;
const key = r => r.sport + ':' + r.id;
function verdict(r){
  const e = entered[key(r)] || {}; const imp = implied(e.odds); const edge = imp == null ? null : r.prob - imp;
  const heat = e.pub != null && e.pub !== '' ? +e.pub : r.heat;
  const live = r.state && !/SCHEDULED|Pre-Game|Scheduled|Warmup/i.test(r.state) && r.sport === 'NFL' ? true : (r.sport === 'MLB' && /Final|Progress|Game Over|Completed/i.test(r.state));
  let v = 'PASS';
  if (live) v = 'DONE';
  else if (edge != null) {
    if (edge >= .04 && heat < 45) v = 'SLEEPER';
    else if (edge >= .03) v = 'VALUE';
    else if (e.pub != null && e.pub !== '' && +e.pub >= 60 && edge < 0) v = 'FADE';
    else if (heat >= 60 && edge <= 0.01) v = 'TRAP';
  } else if (heat >= 65) v = 'CHALK';
  else if (r.prob >= .3 && heat < 40) v = 'SLEEPER';
  const nasty = r.prob * 100 + (edge == null ? 0 : edge * 150) - heat * 0.2;
  return { edge, heat, v, nasty, imp, live };
}
const COLS = {
  mlb: [['Player','name'],['Slot','slot'],['Game','game'],['vs SP','pitcher'],['Season','hr'],['L15','l15hr'],['Model %','prob'],['Fair','fair'],['Book','odds'],['Edge','edge'],['Heat','heat'],['Public %','pub'],['Verdict','v'],['Nasty','nasty']],
  nfl: [['Player','name'],['Pos','pos'],['Game','game'],['Line','spread'],['Team imp.','implied'],['2025 TD','prevTD'],['Share','share'],['Model %','prob'],['Fair','fair'],['Book','odds'],['Edge','edge'],['Heat','heat'],['Public %','pub'],['Verdict','v'],['Nasty','nasty']]
};
function render(){
  const rows = BOARD[tab].map(r => ({ r, ...verdict(r) }));
  const q = norm($('#q').value), minp = +$('#minp').value / 100, maxh = +$('#maxh').value, hide = $('#hidedone').checked, only = $('#onlyplays').checked;
  let list = rows.filter(x => (!hide || !x.live) && x.r.prob >= minp && x.heat <= maxh && (!only || ['SLEEPER','VALUE','TRAP','FADE'].includes(x.v)) &&
      (!q || norm(x.r.name).includes(q) || norm(x.r.team).includes(q) || norm(x.r.game).includes(q) || norm(x.r.teamName || '').includes(q)));
  const get = x => ({ nasty: x.nasty, prob: x.r.prob, edge: x.edge == null ? -9 : x.edge, heat: x.heat, time: x.r.time, name: x.r.name, slot: x.r.slot, hr: x.r.hr, l15hr: x.r.l15hr, fair: x.r.fair, prevTD: x.r.prevTD, share: x.r.share, implied: x.r.implied, v: x.v, game: x.r.game, pitcher: x.r.pitcher, pos: x.r.pos, spread: x.r.spread, odds: (entered[key(x.r)]||{}).odds || 0, pub: (entered[key(x.r)]||{}).pub || 0 })[sortKey];
  list.sort((a, b) => { const A = get(a), B = get(b); return (A > B ? 1 : A < B ? -1 : 0) * sortDir; });
  $('#tbl thead').innerHTML = '<tr>' + COLS[tab].map(([l, k]) => `<th data-k="${k}" class="${k === sortKey ? 'on' : ''}">${l}${k === sortKey ? (sortDir < 0 ? ' ▼' : ' ▲') : ''}</th>`).join('') + '</tr>';
  const tb = $('#tbl tbody'); tb.innerHTML = '';
  const n = { s: 0, v: 0, t: 0 };
  for (const x of list) {
    const r = x.r, e = entered[key(r)] || {}; if (x.v === 'SLEEPER') n.s++; if (x.v === 'VALUE') n.v++; if (x.v === 'TRAP' || x.v === 'FADE') n.t++;
    const when = new Date(r.time).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
    const tr = document.createElement('tr'); tr.className = 'row';
    const common = `<td><span class="nm">${r.name}</span> <span class="tm">${r.team}${r.inj ? ' · ' + r.inj : ''}</span></td>`;
    const tail = `<td class="num">${(r.prob * 100).toFixed(1)}%</td><td class="num">${fmtOdds(r.fair)}</td>
      <td><input class="odds" data-k="${key(r)}" data-f="odds" value="${e.odds || ''}" placeholder="+000"></td>
      <td class="num ${x.edge == null ? '' : x.edge >= 0 ? 'pos' : 'neg'}">${x.edge == null ? '—' : (x.edge >= 0 ? '+' : '') + (x.edge * 100).toFixed(1)}</td>
      <td><span class="bar"><i style="width:${x.heat}%"></i></span> <span class="tm">${Math.round(x.heat)}</span></td>
      <td><input class="pub" data-k="${key(r)}" data-f="pub" value="${e.pub || ''}" placeholder="%"></td>
      <td><span class="v ${x.v}">${x.v}</span></td><td class="num">${x.nasty.toFixed(1)}</td>`;
    if (tab === 'mlb') tr.innerHTML = common + `<td class="num">${r.slot}${r.lineupPosted ? '' : '*'}</td><td class="tm">${r.game.replace(/ at /, ' @ ')}<br>${when}${x.live ? ' · ' + r.state : ''}</td><td class="tm">${r.pitcher} (${r.pHand})</td><td class="num">${r.hr} HR / ${r.pa} PA</td><td class="num">${r.l15hr}</td>` + tail;
    else tr.innerHTML = common + `<td>${r.pos}</td><td class="tm">${r.game}<br>${when}${x.live ? ' · ' + r.state : ''}</td><td class="tm">${r.spread || '—'} / ${r.total || '—'}</td><td class="num">${r.implied}</td><td class="num">${r.prevTD} in ${r.prevGP}g${r.prevTeam && r.prevTeam !== r.team ? ' (' + r.prevTeam + ')' : ''}</td><td class="num">${(r.share * 100).toFixed(0)}%</td>` + tail;
    const det = document.createElement('tr'); det.className = 'det'; det.hidden = true;
    const facts = r.factors ? Object.entries(r.factors).map(([k, v]) => `<span class="f">${k} ${v}</span>`).join('') : '';
    det.innerHTML = `<td colspan="${COLS[tab].length}">${(r.notes || []).filter(Boolean).join(' &nbsp;|&nbsp; ')}<br>${facts}</td>`;
    tr.addEventListener('click', ev => { if (ev.target.tagName !== 'INPUT') det.hidden = !det.hidden; });
    tb.appendChild(tr); tb.appendChild(det);
  }
  $('#kpi').innerHTML = `<div>rows<b>${list.length}</b></div><div>sleepers<b>${n.s}</b></div><div>value<b>${n.v}</b></div><div>traps / fades<b>${n.t}</b></div><div>with a price<b>${list.filter(x => x.edge != null).length}</b></div>`;
  tb.querySelectorAll('input').forEach(i => i.addEventListener('change', () => { const k = i.dataset.k; entered[k] = entered[k] || {}; entered[k][i.dataset.f] = i.value.trim(); saveEntered(); render(); }));
  $('#tbl thead').querySelectorAll('th').forEach(th => th.addEventListener('click', () => { const k = th.dataset.k; if (sortKey === k) sortDir = -sortDir; else { sortKey = k; sortDir = -1; } render(); }));
}
function applyPaste(){
  const all = [...BOARD.mlb, ...BOARD.nfl];
  for (const line of $('#paste').value.split('\n')) {
    const m = line.match(/^(.+?)\s+([-+]\d{3,4})(?:\s+(\d{1,3})%?)?\s*$/); if (!m) continue;
    const nm = norm(m[1]); let best = null, bs = 0;
    for (const r of all) { const rn = norm(r.name); let s = 0; if (rn === nm) s = 3; else if (rn.includes(nm) || nm.includes(rn)) s = 2; else if (rn.split(' ').pop() === nm.split(' ').pop()) s = 1; if (s > bs) { bs = s; best = r; } }
    if (best) { entered[key(best)] = entered[key(best)] || {}; entered[key(best)].odds = m[2]; if (m[3]) entered[key(best)].pub = m[3]; }
  }
  saveEntered(); render();
}
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => { document.querySelectorAll('.tab').forEach(x => x.classList.remove('on')); t.classList.add('on'); tab = t.dataset.t; render(); }));
['#q', '#minp', '#maxh', '#hidedone', '#onlyplays'].forEach(s => $(s).addEventListener('input', render));
$('#sort').addEventListener('change', () => { sortKey = $('#sort').value; sortDir = sortKey === 'time' ? 1 : -1; render(); });
$('#apply').addEventListener('click', applyPaste);
$('#clear').addEventListener('click', () => { entered = {}; saveEntered(); render(); });
render();
</script>
"""
html = TEMPLATE.replace('__BOARD__', json.dumps(board).replace('</', '<\\/')).replace('__GEN__', board['generated'])
open(os.path.join(OUT, 'board.html'), 'w', encoding='utf-8').write(html)
print("wrote", os.path.join(OUT, 'board.html'), len(html) // 1024, "KB")
