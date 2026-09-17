"""Contrarian HR / anytime-TD engine.

Two layers per player:
  1. TRUE PROB  - what the numbers say (rates, matchup, park, weather, lineup slot / implied team total, TD share).
  2. PUBLIC HEAT - how obvious / over-bet the name is. The board price bakes in the obvious pick, so
     the play is the gap between the two: high prob + low heat = SLEEPER, high heat + no edge = TRAP.
Outputs output/board.json consumed by build_html.py.
"""
import json, math, os, re, datetime, collections

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data'); OUT = os.path.join(HERE, 'output'); os.makedirs(OUT, exist_ok=True)
def L(n, default=None):
    try:
        return json.load(open(os.path.join(DATA, n), encoding='utf-8'))
    except FileNotFoundError:
        if default is not None: return default
        raise
def f(x, d=0.0):
    try: return float(x)
    except (TypeError, ValueError): return d
def ip(s):  # "123.1" innings -> 123.333
    s = str(s or '0'); w, _, r = s.partition('.'); return f(w) + {'1': 1/3, '2': 2/3}.get(r, 0)
def american(p):
    p = min(max(p, 0.005), 0.995)
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)
def clamp(x, lo, hi): return max(lo, min(hi, x))

# ---------------------------------------------------------------- MLB ----
# 3-yr HR park factors (100 = neutral) keyed by venue-name fragment. Unknown venues -> 100.
PARK = {'Coors': 112, 'Great American': 130, 'Yankee': 120, 'Citizens Bank': 116, 'Dodger': 110, 'Truist': 106, 'Globe Life': 104,
        'Guaranteed Rate': 112, 'Rate Field': 112, 'Angel': 108, 'Rogers': 108, 'Camden': 100, 'Fenway': 92, 'Wrigley': 100,
        'American Family': 108, 'Citi': 100, 'Nationals': 100, 'Minute Maid': 104, 'Daikin': 104, 'Chase': 100, 'Petco': 94,
        'Oracle': 78, 'T-Mobile': 90, 'Kauffman': 86, 'Comerica': 90, 'PNC': 86, 'Busch': 92, 'Target': 98, 'Progressive': 96,
        'loanDepot': 88, 'Tropicana': 96, 'Steinbrenner': 108, 'Sutter': 114, 'Truist Park': 106}
DOMES = ('Tropicana', 'Rogers', 'Minute Maid', 'Daikin', 'Chase', 'American Family', 'Globe Life', 'loanDepot', 'T-Mobile')
SLOT_PA = [4.65, 4.55, 4.45, 4.35, 4.25, 4.15, 4.05, 3.95, 3.85]   # expected PA by lineup slot (home); away +0.10
SLOT_SP = [2.75, 2.7, 2.65, 2.6, 2.55, 2.5, 2.4, 2.35, 2.3]        # of which vs the starting pitcher

def park_factor(venue):
    for k, v in PARK.items():
        if k.lower() in venue.lower(): return v / 100
    return 1.0

def weather_factor(w, venue):
    if not w or any(d.lower() in venue.lower() for d in DOMES): return 1.0, 'dome/none'
    t = f(w.get('temp'), 72); fac = 1 + 0.006 * (t - 70)
    wind = w.get('wind', ''); m = re.match(r'(\d+)\s*mph,?\s*(.*)', wind or ''); note = f"{int(t)}F"
    if m:
        mph, d = f(m.group(1)), m.group(2).lower(); note += f" wind {int(mph)} {d}"
        if 'out' in d: fac *= 1 + 0.022 * max(0, mph - 4)
        elif 'in' in d: fac *= 1 - 0.018 * max(0, mph - 4)
    return clamp(fac, 0.75, 1.35), note

def mlb():
    games = L('mlb_schedule.json'); hit = L('mlb_hitting.json'); pit = L('mlb_pitching.json'); people = {p['id']: p for p in L('mlb_people.json')}
    hs = L('mlb_hitter_splits.json', {}); ps = L('mlb_pitcher_splits.json', {}); tp = L('mlb_team_pitching.json', {}); odds = L('mlb_odds.json', {})
    H = {h['player']['id']: h['stat'] for h in hit}; P = {p['player']['id']: p['stat'] for p in pit}
    lg_hr = sum(h['stat']['homeRuns'] for h in hit); lg_pa = sum(h['stat']['plateAppearances'] for h in hit); LG = lg_hr / lg_pa   # league HR/PA
    lg_hr_rank = {h['player']['id']: i + 1 for i, h in enumerate(sorted(hit, key=lambda h: -h['stat']['homeRuns']))}
    def split(store, pid, code, key='homeRuns', den='plateAppearances'):
        for st in store.get(str(pid), []):
            if st['type']['displayName'] == 'statSplits':
                for x in st['splits']:
                    if x.get('split', {}).get('code') == code: return x['stat'].get(key, 0), x['stat'].get(den, 0)
        return 0, 0
    def last15(pid):
        for st in hs.get(str(pid), []):
            if st['type']['displayName'] == 'lastXGames' and st['splits']:
                s = st['splits'][0]['stat']; return s.get('homeRuns', 0), s.get('plateAppearances', 0)
        return 0, 0
    rows = []
    for g in games:
        state = g['status']['detailedState']
        venue = g['venue']['name']; pf = park_factor(venue); wf, wnote = weather_factor(g.get('weather'), venue)
        gname = f"{g['teams']['away']['team']['name']} at {g['teams']['home']['team']['name']}"; o = odds.get(gname, {})
        total = f(o.get('total'), 0) or None
        run_env = clamp(total / 8.6, 0.85, 1.2) if total else 1.0
        for side, opp in (('home', 'away'), ('away', 'home')):
            team = g['teams'][side]['team']; oppteam = g['teams'][opp]['team']
            sp = g['teams'][opp].get('probablePitcher'); spid = sp['id'] if sp else None
            spst = P.get(spid, {}); sp_hand = people.get(spid, {}).get('pitchHand', {}).get('code', 'R') if spid else 'R'
            # starter HR/BF, regressed to league (k=350 BF)
            sp_bf = f(spst.get('battersFaced')); sp_hr = f(spst.get('homeRuns'))
            sp_rate = (sp_hr + 350 * LG) / (sp_bf + 350) if spid else LG
            bp = tp.get(str(oppteam['id']), {}); bp_rate = (f(bp.get('homeRuns')) + 500 * LG) / (f(bp.get('battersFaced')) + 500) if bp else LG
            lineup = g.get('lineups', {}).get(f'{side}Players', [])
            posted = bool(lineup)
            if not posted:
                cand = sorted([h for h in hit if h['team']['id'] == team['id']], key=lambda h: -h['stat']['plateAppearances'])[:9]
                lineup = [{'id': h['player']['id'], 'fullName': h['player']['fullName']} for h in cand]
            for slot, pl in enumerate(lineup[:9]):
                pid = pl['id']; st = H.get(pid); per = people.get(pid, {})
                if not st or st['plateAppearances'] < 30: continue
                bat = per.get('batSide', {}).get('code', 'R')
                if bat == 'S': bat_eff = 'L' if sp_hand == 'R' else 'R'
                else: bat_eff = bat
                pa, hr = st['plateAppearances'], st['homeRuns']
                base = (hr + 120 * LG) / (pa + 120)                       # regressed season HR/PA (k=120: own rate matters more than league)
                # calibration from graded days 9/3-9/10: weak hitters (< 0.8x league) homered far less than a league-mean pull implied
                weak = 1.0 if base / LG >= 0.8 else max(0.45, 0.45 + (base / LG - 0.6) / 0.2 * 0.55)
                CAL = 0.92 * weak                                            # 0.92 = global level correction (model ran ~12% hot)
                code = 'vl' if sp_hand == 'L' else 'vr'
                shr, spa = split(hs, pid, code)
                plat = ((shr + 150 * base) / (spa + 150)) / base if spa else 1.0
                plat = clamp(plat, 0.7, 1.4)
                # pitcher platoon: HR allowed vs this batter side, regressed to his overall
                pcode = 'vl' if bat_eff == 'L' else 'vr'
                phr, pbf = split(ps, spid, pcode, den='battersFaced') if spid else (0, 0)
                sp_plat = ((phr + 150 * sp_rate) / (pbf + 150)) / sp_rate if pbf else 1.0
                sp_fac = clamp(sp_rate * math.sqrt(clamp(sp_plat, 0.7, 1.4)) / LG, 0.55, 1.7)
                bp_fac = clamp(bp_rate / LG, 0.7, 1.4)
                l15hr, l15pa = last15(pid); hot = (l15hr / l15pa) if l15pa else 0
                form = clamp(1 + 0.10 * ((hot / LG) - (base / LG)) / 3, 0.92, 1.10)   # hot hand is mostly noise: tiny weight
                exp_pa = SLOT_PA[slot] + (0.10 if side == 'away' else 0); sp_pa = SLOT_SP[slot]
                p_sp = clamp(base * plat * sp_fac * pf * wf * run_env * form * CAL, 0, 0.25)
                p_bp = clamp(base * plat * bp_fac * pf * wf * run_env * form * CAL, 0, 0.25)
                prob = 1 - (1 - p_sp) ** sp_pa * (1 - p_bp) ** (exp_pa - sp_pa)
                if pa >= 200: prob = max(prob, 0.04)                       # floor: stacked penalties overshoot on real regulars (Guerrero at 2%)
                # ---- public heat: how obvious is this name today (0-100) ----
                rank = lg_hr_rank.get(pid, 400)
                heat = 0
                heat += 40 * clamp(1 - (rank - 1) / 40, 0, 1)                     # star power (HR leaderboard)
                heat += 25 * clamp(l15hr / 5, 0, 1)                                # recency: HRs in last 15 games
                heat += 15 * clamp((pf - 1) / 0.25, 0, 1)                          # "he's in Coors / Yankee Stadium" narrative
                heat += 12 * clamp((sp_rate / LG - 1) / 0.5, 0, 1)                 # "bad pitcher" narrative
                heat += 8 * (1 if slot < 4 else 0)
                rows.append({'sport': 'MLB', 'gamePk': g['gamePk'], 'date': g.get('officialDate') or g['gameDate'][:10], 'id': pid, 'name': pl.get('fullName') or per.get('fullName'), 'team': team['abbreviation'] if 'abbreviation' in team else team['name'],
                             'teamName': team['name'], 'opp': oppteam['name'], 'game': gname, 'state': state, 'time': g['gameDate'], 'venue': venue,
                             'slot': slot + 1, 'lineupPosted': posted, 'bat': bat, 'pitcher': sp['fullName'] if sp else 'TBD', 'pHand': sp_hand,
                             'hr': hr, 'pa': pa, 'hrRank': rank, 'l15hr': l15hr, 'l15pa': l15pa,
                             'prob': round(prob, 4), 'fair': american(prob), 'heat': round(heat),
                             'factors': {'base': round(base / LG, 2), 'platoon': round(plat, 2), 'pitcher': round(sp_fac, 2), 'bullpen': round(bp_fac, 2),
                                         'park': round(pf, 2), 'weather': round(wf, 2), 'runEnv': round(run_env, 2), 'form': round(form, 2), 'cal': round(CAL, 2), 'expPA': round(exp_pa, 1)},
                             'notes': [f"SP {sp['fullName'] if sp else 'TBD'} ({sp_hand}) HR/BF {sp_rate / LG:.2f}x lg" + (f", vs {bat_eff}HB {sp_plat:.2f}x" if pbf else ''),
                                       f"{'S' if bat == 'S' else bat}HB vs {sp_hand}HP {plat:.2f}x own rate", f"park {pf:.2f} | {wnote}",
                                       f"last 15 g: {l15hr} HR / {l15pa} PA", 'lineup posted' if posted else 'LINEUP NOT POSTED - projected by PA']})
    return rows

# ---------------------------------------------------------------- NFL ----
POS_PRIOR = {'RB': 0.20, 'WR': 0.14, 'TE': 0.10, 'QB': 0.06, 'FB': 0.03}
TD_PER_PT = 0.115   # offensive TDs per point of implied team total (Week 1 2026 ran 61 scorers vs 53 modeled at 0.108)

def parse_spread(details, home, away):
    if not details: return None
    m = re.match(r'([A-Z]+)\s*([-+]?\d+(?:\.\d+)?)', details)
    if not m: return None
    fav, n = m.group(1), f(m.group(2))
    return n if fav == home else -n   # home spread (negative = home favored)

def nfl():
    sb = L('nfl_scoreboard.json', {'events': []}); st = L('nfl_stats_prev.json', {'scoring': {'athletes': [], 'categories': None}})['scoring']; ro = L('nfl_rosters.json', []); ts = L('nfl_team_stats_prev.json', {})
    names = st['categories'] if st.get('categories') else None
    # 2025 player TDs
    prev = {}
    for a in st['athletes']:
        sc = next((c for c in a['categories'] if c['name'] == 'scoring'), None); gp = next((c for c in a['categories'] if c['name'] == 'general'), None)
        if not sc: continue
        v = sc['values']; g = f(gp['values'][0], 17) if gp else 17
        prev[a['athlete']['id']] = {'rush': f(v[0]), 'rec': f(v[1]), 'ret': f(v[2]), 'td': f(v[3]), 'gp': max(g, 1), 'prevTeam': a['athlete'].get('teamShortName')}
    td_rank = {pid: i + 1 for i, (pid, d) in enumerate(sorted(prev.items(), key=lambda kv: -(kv[1]['rush'] + kv[1]['rec'])))}
    # 2025 team offensive TDs
    team_off = {}
    for ab, t in ts.items():
        cats = t['results']['stats']['categories']
        sc = next((c for c in cats if c['name'] == 'scoring'), None)
        if sc:
            d = {s['name']: f(s.get('value')) for s in sc['stats']}
            team_off[ab] = d.get('rushingTouchdowns', 0) + d.get('receivingTouchdowns', 0)
    lg_team_td = sum(team_off.values()) / max(len(team_off), 1)
    depth = L('nfl_depth.json') if os.path.exists(os.path.join(DATA, 'nfl_depth.json')) else {}
    DEPTH_MULT = {'RB': {1: 1.35, 2: 0.45, 3: 0.2}, 'WR': {1: 0.95, 2: 0.6, 3: 0.3}, 'TE': {1: 1.25, 2: 0.5, 3: 0.2}, 'QB': {1: 1.2, 2: 0.0, 3: 0.0}, 'FB': {1: 0.6, 2: 0.3, 3: 0.15}}   # v2: re-weighted on Week 1 2026 results (starters under-modeled, backups over-modeled)
    # ---- this season's usage -> a usage-based TD share per team ----
    # expected TDs from opportunity: league rates ~0.044 TD per target, ~0.032 per carry; actual TDs get a quarter of the weight (red-zone role shows up there first).
    cur = L('nfl_stats_cur.json', {'players': {}}).get('players', {})
    def usage_score(c): return 0.75 * (0.044 * c['tgt'] + 0.032 * c['att']) + 0.25 * (c['rushTD'] + c['recTD'])
    team_usage = collections.defaultdict(float); team_games = collections.defaultdict(float)
    for c in cur.values():
        if c.get('team'): team_usage[c['team']] += usage_score(c); team_games[c['team']] = max(team_games[c['team']], c.get('gp') or 0)
    def w_cur(team):                                                  # weight on 2026: 25% after one game, +10 points a game, capped at 75%
        gp = team_games.get(team, 0); return 0.0 if gp < 1 else min(0.75, 0.15 + 0.10 * gp)
    roster_by_team = collections.defaultdict(list)
    for r in ro: roster_by_team[r['team']].append(r)
    # implied totals from odds
    games = []
    for e in sb['events']:
        c = e['competitions'][0]; o = (c.get('odds') or [{}])[0]
        home = next(x for x in c['competitors'] if x['homeAway'] == 'home'); away = next(x for x in c['competitors'] if x['homeAway'] == 'away')
        hs, aw = home['team']['abbreviation'], away['team']['abbreviation']
        total = f(o.get('overUnder'), 0); spread = parse_spread(o.get('details'), hs, aw)
        if total and spread is not None: h_pts, a_pts = (total - spread) / 2, (total + spread) / 2
        else: h_pts = a_pts = 22.0
        games.append({'eventId': e['id'], 'name': e['shortName'], 'date': e['date'], 'state': c['status']['type']['name'], 'home': hs, 'away': aw, 'total': total or None, 'spread': o.get('details'),
                      'implied': {hs: h_pts, aw: a_pts}, 'prime': e['date'][11:13] in ('00', '01') or e['date'][:10] >= '2026-09-15'})
    rows = []
    for g in games:
        for team in (g['home'], g['away']):
            opp = g['away'] if team == g['home'] else g['home']
            team_td = TD_PER_PT * g['implied'][team]
            cands = []
            for r in roster_by_team[team]:
                pos = r['pos'] or ''
                if pos not in POS_PRIOR: continue
                inj = (r['injuries'] or [''])[0]
                if inj in ('Out', 'Injured Reserve', 'Suspension', 'Doubtful', 'Physically Unable to Perform') or r['status'] != 'active': continue
                p = prev.get(r['id'])
                prior = POS_PRIOR[pos]
                if p:
                    tdpg = (p['rush'] + p['rec']) / p['gp']
                    prev_team_tdpg = team_off.get(p['prevTeam'], lg_team_td) / 17
                    raw = tdpg / max(prev_team_tdpg, 0.5)
                    share = (raw * p['gp'] + prior * 6) / (p['gp'] + 6)
                    if pos == 'QB' and p['rush'] == 0 and p['gp'] < 4: share = 0.02
                elif r.get('exp') in (0, None) and pos in ('RB', 'WR', 'TE'):
                    share = prior * 0.5  # rookie / no 2025 line: half a positional prior
                else:
                    share = prior * 0.25
                if inj == 'Questionable': share *= 0.85
                if pos == 'QB': share = min(share, 0.08)                      # a QB rarely owns more than ~11% of his team's TDs (rushing only)
                dc = depth.get(team, {}).get(r['id'])
                if depth.get(team):                                   # chart exists for this team
                    if dc: share *= DEPTH_MULT.get(dc['pos'], DEPTH_MULT['WR']).get(min(dc['rank'], 3), 0.1); r['depth'] = dc.get('label') or f"{dc['pos']}{dc['rank']}"
                    else: share *= 0.08; r['depth'] = 'not on chart'
                # blend in this season. The 2026 share already reflects role, so it is NOT depth-multiplied; injuries still apply.
                c = cur.get(r['id']); w = w_cur(team); r['usage26'] = None
                if w and team_usage.get(team):
                    if c and c.get('team') == team:
                        cs = 0.95 * usage_score(c) / team_usage[team]
                        if inj == 'Questionable': cs *= 0.85
                        if pos == 'QB': cs = min(cs, 0.08)
                        r['share25'] = share; share = (1 - w) * share + w * cs
                        r['usage26'] = {'gp': c['gp'], 'tgt': c['tgt'], 'att': c['att'], 'td': c['rushTD'] + c['recTD'], 'share': round(cs, 3), 'w': round(w, 2)}
                    elif not (dc and dc['rank'] == 1):                 # no 2026 touches and not a listed starter: he isn't part of the offense yet
                        r['share25'] = share; share = (1 - w) * share
                        r['usage26'] = {'gp': 0, 'tgt': 0, 'att': 0, 'td': 0, 'share': 0.0, 'w': round(w, 2)}
                cands.append((r, p, share, inj))
            tot = sum(s for _, _, s, _ in cands) or 1
            scale = 0.95 / tot if tot > 0.95 else 1.0   # a team's TD shares can't sum past ~95% (rest = defense/ST/randoms)
            for r, p, share, inj in cands:
                share *= scale; lam = share * team_td; prob = 1 - math.exp(-lam)
                if prob < 0.04: continue
                rank = td_rank.get(r['id'], 400)
                heat = 40 * clamp(1 - (rank - 1) / 30, 0, 1) + 15 * (1 if g['prime'] else 0) + 15 * clamp((g['implied'][team] - 20) / 10, 0, 1)
                heat += 20 * clamp((prob - 0.3) / 0.4, 0, 1) + 10 * (1 if r['pos'] == 'RB' else 0)
                rows.append({'sport': 'NFL', 'eventId': g['eventId'], 'id': r['id'], 'name': r['name'], 'team': team, 'opp': opp, 'pos': r['pos'], 'game': g['name'], 'state': g['state'], 'time': g['date'],
                             'spread': g['spread'], 'total': g['total'], 'implied': round(g['implied'][team], 1), 'teamTD': round(team_td, 2),
                             'prevTD': (p['rush'] + p['rec']) if p else 0, 'prevGP': p['gp'] if p else 0, 'prevTeam': p['prevTeam'] if p else None, 'tdRank': rank,
                             'share': round(share, 3), 'lam': round(lam, 3), 'prob': round(prob, 4), 'fair': american(prob), 'heat': round(heat), 'inj': inj or '', 'depth': r.get('depth', ''), 'usage26': r.get('usage26'),
                             'notes': [f"team implied {g['implied'][team]:.1f} pts -> {team_td:.2f} off. TDs", f"2025: {int(p['rush'] + p['rec']) if p else 0} TD in {int(p['gp']) if p else 0} g" + (f" ({p['prevTeam']})" if p and p['prevTeam'] != team else ''),
                                       (f"2026: {int(r['usage26']['tgt'])} tgt, {int(r['usage26']['att'])} car, {int(r['usage26']['td'])} TD in {int(r['usage26']['gp'])} g -> usage share {r['usage26']['share']:.0%}, weighted {r['usage26']['w']:.0%} (2025-based share was {r.get('share25', 0):.0%})" if r.get('usage26') else '2026 usage: not blended (no team games yet, or starter with no line)'), f"TD share {share:.0%} -> {lam:.2f} exp. TDs", (f"INJURY: {inj}" if inj else 'healthy'), f"depth chart: {r.get('depth', '?')}", 'PRIMETIME' if g['prime'] else '']})
    return rows, games

if __name__ == '__main__':
    m = mlb(); n, games = nfl()
    board = {'generated': datetime.datetime.now().isoformat(timespec='minutes'), 'mlb': sorted(m, key=lambda r: -r['prob']), 'nfl': sorted(n, key=lambda r: -r['prob']), 'nflGames': games}
    json.dump(board, open(os.path.join(OUT, 'board.json'), 'w', encoding='utf-8'), indent=1)
    print(f"MLB rows {len(m)} | NFL rows {len(n)}")
    for r in board['mlb'][:8]: print(f"  MLB {r['name']:22s} {r['team']:4s} slot{r['slot']} p={r['prob']:.3f} fair {r['fair']:+d} heat {r['heat']}")
    for r in board['nfl'][:8]: print(f"  NFL {r['name']:22s} {r['team']:4s} {r['pos']} p={r['prob']:.3f} fair {r['fair']:+d} heat {r['heat']} share {r['share']}")
