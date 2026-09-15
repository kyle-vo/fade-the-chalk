"""Pull every raw feed the model needs into data/*.json (public MLB StatsAPI + ESPN)."""
import json, os, sys, datetime, concurrent.futures as cf
import requests

S = requests.Session(); S.headers['User-Agent'] = 'Mozilla/5.0'
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data'); os.makedirs(DATA, exist_ok=True)
MLB = "https://statsapi.mlb.com/api/v1"
ESPN = "https://site.api.espn.com/apis/site/v2/sports"
ESPNW = "https://site.web.api.espn.com/apis/common/v3/sports"

def get(url, **p):
    r = S.get(url, params=p, timeout=40); r.raise_for_status(); return r.json()
def save(name, obj):
    with open(os.path.join(DATA, name), 'w', encoding='utf-8') as f: json.dump(obj, f)
    print(f"  saved {name}")

def today(): return os.environ.get('EDGE_DATE') or datetime.date.today().isoformat()

# ---------------- MLB ----------------
def fetch_mlb():
    d = today(); print(f"[MLB] {d}")
    sched = get(f"{MLB}/schedule", sportId=1, date=d, hydrate="probablePitcher,venue,weather,lineups,team")
    games = sched['dates'][0]['games'] if sched.get('dates') else []
    save('mlb_schedule.json', games)
    yr = d[:4]
    hit = get(f"{MLB}/stats", stats="season", group="hitting", season=yr, sportId=1, limit=2000, playerPool="all")['stats'][0]['splits']
    pit = get(f"{MLB}/stats", stats="season", group="pitching", season=yr, sportId=1, limit=2000, playerPool="all")['stats'][0]['splits']
    save('mlb_hitting.json', hit); save('mlb_pitching.json', pit)
    ids = set()
    for g in games:
        for side in ('home', 'away'):
            pp = g['teams'][side].get('probablePitcher')
            if pp: ids.add(pp['id'])
        for k in ('homePlayers', 'awayPlayers'):
            for p in g.get('lineups', {}).get(k, []): ids.add(p['id'])
    # if a lineup is not posted yet, take the team's top hitters by PA as a stand-in
    team_ids = {g['teams'][s]['team']['id'] for g in games for s in ('home', 'away')}
    posted = {g['teams'][s]['team']['id'] for g in games for s, k in (('home', 'homePlayers'), ('away', 'awayPlayers')) if g.get('lineups', {}).get(k)}
    for tid in team_ids - posted:
        rows = sorted([h for h in hit if h['team']['id'] == tid], key=lambda h: -h['stat']['plateAppearances'])[:10]
        for h in rows: ids.add(h['player']['id'])
    people = []
    idl = list(ids)
    for i in range(0, len(idl), 100):
        people += get(f"{MLB}/people", personIds=",".join(map(str, idl[i:i+100])))['people']
    save('mlb_people.json', people)
    def hsplit(pid):
        try:
            r = get(f"{MLB}/people/{pid}/stats", stats="statSplits,lastXGames", group="hitting", season=yr, sitCodes="vl,vr", limit=15)
            return pid, r.get('stats', [])
        except Exception: return pid, []
    def psplit(pid):
        try:
            r = get(f"{MLB}/people/{pid}/stats", stats="statSplits,lastXGames", group="pitching", season=yr, sitCodes="vl,vr", limit=5)
            return pid, r.get('stats', [])
        except Exception: return pid, []
    is_p = lambda p: p.get('primaryPosition', {}).get('type') == 'Pitcher' or p.get('primaryPosition', {}).get('abbreviation') == 'TWP'
    hitters = [p['id'] for p in people if not is_p(p) or p.get('primaryPosition', {}).get('abbreviation') == 'TWP']
    pitchers = [p['id'] for p in people if is_p(p)]
    with cf.ThreadPoolExecutor(12) as ex:
        hs = dict(ex.map(hsplit, hitters)); ps = dict(ex.map(psplit, pitchers))
    save('mlb_hitter_splits.json', {str(k): v for k, v in hs.items()}); save('mlb_pitcher_splits.json', {str(k): v for k, v in ps.items()})
    teams = get(f"{MLB}/teams", sportId=1)['teams']
    tp = {}
    def tstat(t):
        try:
            r = get(f"{MLB}/teams/{t['id']}/stats", stats="season", group="pitching", season=yr)
            return str(t['id']), r['stats'][0]['splits'][0]['stat']
        except Exception: return str(t['id']), None
    with cf.ThreadPoolExecutor(8) as ex: tp = {k: v for k, v in ex.map(tstat, teams) if v}
    save('mlb_team_pitching.json', tp); save('mlb_teams.json', teams)
    try:
        sb = get(f"{ESPN}/baseball/mlb/scoreboard", dates=d.replace('-', ''))
        odds = {}
        for e in sb['events']:
            c = e['competitions'][0]; o = (c.get('odds') or [{}])[0]
            odds[e['name']] = {'details': o.get('details'), 'total': o.get('overUnder'),
                               'home': next((x['team']['abbreviation'] for x in c['competitors'] if x['homeAway'] == 'home'), None),
                               'away': next((x['team']['abbreviation'] for x in c['competitors'] if x['homeAway'] == 'away'), None),
                               'homeML': (o.get('homeTeamOdds') or {}).get('moneyLine'), 'awayML': (o.get('awayTeamOdds') or {}).get('moneyLine')}
        save('mlb_odds.json', odds)
    except Exception as e: print("  mlb odds failed", e)

# ---------------- NFL ----------------
def fetch_nfl():
    print("[NFL]")
    wk = os.environ.get('NFL_WEEK')          # NFL_WEEK=2 pulls a specific week; default = ESPN's current week
    sb = get(f"{ESPN}/football/nfl/scoreboard", **({'week': int(wk), 'seasontype': 2, 'dates': datetime.date.today().year} if wk else {}))
    save('nfl_scoreboard.json', sb); print(f"  NFL week {sb['week']['number']}: {len(sb['events'])} games")
    season_prev = sb['season']['year'] - 1
    stats = {}
    for cat, sort in (('scoring', 'scoring.totalTouchdowns:desc'),):
        out = []
        for page in range(1, 6):
            p = dict(season=season_prev, seasontype=2, category=cat, limit=200, page=page)
            if sort: p['sort'] = sort
            r = get(f"{ESPNW}/football/nfl/statistics/byathlete", **p)
            out += r.get('athletes', [])
            if len(r.get('athletes', [])) < 200: break
        stats[cat] = {'categories': r.get('categories'), 'athletes': out}
        print(f"  {cat}: {len(out)} athletes ({season_prev})")
    save('nfl_stats_prev.json', stats)
    teams = get(f"{ESPN}/football/nfl/teams")['sports'][0]['leagues'][0]['teams']
    def roster(t):
        tid = t['team']['id']
        r = get(f"{ESPN}/football/nfl/teams/{tid}/roster")
        rows = []
        for grp in r.get('athletes', []):
            for a in grp.get('items', []):
                rows.append({'id': a['id'], 'name': a['displayName'], 'pos': a.get('position', {}).get('abbreviation'),
                             'status': a.get('status', {}).get('type'), 'injuries': [i.get('status') for i in a.get('injuries', [])],
                             'team': t['team']['abbreviation'], 'teamId': tid, 'exp': a.get('experience', {}).get('years')})
        return rows
    with cf.ThreadPoolExecutor(8) as ex: rosters = sum(ex.map(roster, teams), [])
    save('nfl_rosters.json', rosters)
    def depth(t):
        """offense depth chart: {athleteId: {'pos': 'RB', 'rank': 1}} (rank = order listed at that slot; wr1/wr2/wr3 are all starters)"""
        try: d = get(f"https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/teams/{t['team']['id']}/depthcharts")
        except Exception: return t['team']['abbreviation'], {}
        out = {}
        for grp in d.get('depthchart', []):
            for slot, v in grp.get('positions', {}).items():
                pos = v.get('position', {}).get('abbreviation')
                if pos not in ('QB', 'RB', 'WR', 'TE', 'FB'): continue
                for i, a in enumerate(v.get('athletes', [])):
                    cur = out.get(a['id'])
                    if not cur or i + 1 < cur['rank']: out[a['id']] = {'pos': pos, 'rank': i + 1, 'slot': slot}
        return t['team']['abbreviation'], out
    with cf.ThreadPoolExecutor(8) as ex: depths = dict(ex.map(depth, teams))
    save('nfl_depth.json', depths); print(f"  depth charts: {sum(1 for v in depths.values() if v)} teams")
    def tstat(t):
        try: return t['team']['abbreviation'], get(f"{ESPN}/football/nfl/teams/{t['team']['id']}/statistics", season=season_prev)
        except Exception: return t['team']['abbreviation'], None
    with cf.ThreadPoolExecutor(8) as ex: tstats = {k: v for k, v in ex.map(tstat, teams) if v}
    save('nfl_team_stats_prev.json', tstats)

if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    try:
        if which in ('all', 'mlb'): fetch_mlb()
    except Exception as e:
        print(f"MLB fetch failed: {e}")
    try:
        if which in ('all', 'nfl'): fetch_nfl()
    except Exception as e:
        print(f"NFL fetch failed: {e}")
    print("done")
