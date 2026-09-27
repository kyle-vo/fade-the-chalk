"""One navigation bar for every page: pick the sport once (MLB / NFL), then the page (props, moneyline, spreads & totals), then the slate.
The sport choice rides in the URL hash (#mlb / #nfl) and in localStorage, so moving between pages keeps it.

page   : 'props' | 'ml' | 'lines' | 'track' | 'archive'
root   : '' or '../' (day and week pages live one folder down)
slates : {'mlb': [(value, label, href)], 'nfl': [...]}; href '' means the page switches in place through window.onNavSlate(sport, value)
cur    : {'mlb': value, 'nfl': value}, the slate this page shows first for each sport
fixed  : 'mlb' / 'nfl' when the page holds one sport only (day and week pages)

Pages hook in with window.onNavSport(sport) (return false to let the bar navigate instead) and call window.navSport(sport, slate) when they switch."""
import json

CSS = """<style>
nav.nb{display:flex;flex-wrap:wrap;align-items:center;gap:10px 22px;padding:10px 26px;border-bottom:1px solid var(--line);background:#0e1115;font-size:14px;position:sticky;top:0;z-index:5}
.nb .sp{display:inline-flex;background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:3px;gap:2px}
.nb .sp a{padding:6px 16px;border-radius:999px;color:var(--mute);font-weight:800;letter-spacing:1px;font-size:12px;cursor:pointer;text-decoration:none;user-select:none}
.nb .sp a:hover{color:var(--ink)}
.nb .sp a.on[data-sp=mlb]{background:#18293d;color:#8cc2ff}.nb .sp a.on[data-sp=nfl]{background:#153325;color:#86e8ad}
.nb .pg,.nb .aux{display:flex;flex-wrap:wrap;gap:2px 18px}
.nb .pg a,.nb .aux a{color:var(--mute);text-decoration:none;padding:7px 0;border-bottom:2px solid transparent;font-weight:600;white-space:nowrap}
.nb .pg a:hover,.nb .aux a:hover{color:var(--ink)}
.nb .pg a.on,.nb .aux a.on{color:var(--ink);border-bottom-color:var(--acc)}
.nb .sl{display:flex;align-items:center;gap:6px;color:var(--mute);font-size:12px;text-transform:uppercase;letter-spacing:.6px}
.nb .sl select{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:5px 8px;font:600 13px var(--font);text-transform:none;letter-spacing:0;cursor:pointer}
.nb .aux{margin-left:auto}
.panel.top{margin-top:16px}
@media(max-width:700px){nav.nb{padding:8px 10px;gap:8px 14px;position:static}.nb .aux{margin-left:0}}
</style>"""

JS = r"""<script>(function(){
const NAV = __NAV__;
const PAGES = { props: 'index.html', ml: 'ml.html', lines: 'lines.html' };
const h = (location.hash || '').slice(1).split(':')[0];
let sp = NAV.fixed || ((h === 'mlb' || h === 'nfl') ? h : null);
if (!sp) { try { sp = localStorage.getItem('ftc_sport'); } catch (e) {} }
if (sp !== 'mlb' && sp !== 'nfl') sp = 'mlb';
window.NAV_SPORT = sp;
const link = (pg, s) => NAV.root + PAGES[pg] + '#' + s;
window.navSport = function(s, cur){
  sp = s; window.NAV_SPORT = s; window.__navSet = true; try { localStorage.setItem('ftc_sport', s); } catch (e) {}
  document.querySelectorAll('nav.nb .sp a').forEach(a => a.classList.toggle('on', a.dataset.sp === s));
  document.querySelectorAll('nav.nb .pg a').forEach(a => { a.href = link(a.dataset.pg, s); });
  const pr = document.querySelector('nav.nb .pg a[data-pg=props]'); if (pr) pr.textContent = s === 'mlb' ? 'Home runs' : 'Touchdowns';
  const sel = document.querySelector('nav.nb .sl select'), box = document.querySelector('nav.nb .sl');
  const opts = (NAV.slates || {})[s] || [];
  if (sel) { sel.innerHTML = opts.map(o => `<option value="${o[0]}">${o[1]}</option>`).join(''); const c = cur || (NAV.cur || {})[s]; if (c != null) sel.value = c; box.hidden = !opts.length; }
};
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('nav.nb .sp a').forEach(a => a.addEventListener('click', ev => {
    ev.preventDefault(); const s = a.dataset.sp;
    if (NAV.page === 'track' || NAV.page === 'archive') { navSport(s); return; }
    if (!(window.onNavSport && window.onNavSport(s) !== false)) location.href = link(NAV.page, s);
  }));
  const sel = document.querySelector('nav.nb .sl select');
  if (sel) sel.addEventListener('change', () => {
    const o = ((NAV.slates || {})[sp] || []).find(x => x[0] === sel.value); if (!o) return;
    if (o[2]) location.href = o[2]; else if (window.onNavSlate) window.onNavSlate(sp, o[0]);
  });
  if (!window.__navSet) navSport(sp);
});
})();</script>"""


def navbar(page, root='', slates=None, cur=None, fixed=None):
    on = lambda p: ' class="on"' if page == p else ''
    cfg = json.dumps({'page': page, 'root': root, 'slates': slates or {}, 'cur': cur or {}, 'fixed': fixed}).replace('</', '<\\/')
    slate = '' if not slates else '<label class="sl">slate <select></select></label>'
    return (CSS + '<nav class="nb">'
            '<div class="sp"><a data-sp="mlb" href="#mlb">MLB</a><a data-sp="nfl" href="#nfl">NFL</a></div>'
            f'<div class="pg"><a data-pg="props" href="{root}index.html"{on("props")}>Home runs</a><a data-pg="ml" href="{root}ml.html"{on("ml")}>Moneyline</a><a data-pg="lines" href="{root}lines.html"{on("lines")}>Spreads &amp; Totals</a></div>'
            f'{slate}'
            f'<div class="aux"><a href="{root}track.html"{on("track")}>Track</a><a href="{root}archive.html"{on("archive")}>Archive</a></div>'
            '</nav>' + JS.replace('__NAV__', cfg))


def day_label(d):
    import datetime
    try: return datetime.date.fromisoformat(d).strftime('%a %b ') + str(int(d[8:]))
    except ValueError: return d


def week_label(w):
    return 'Week ' + w.split('wk')[1] if 'wk' in w else w
