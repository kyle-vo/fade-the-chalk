"""+EV finder: every price we can bet vs Pinnacle's de-vigged fair price, for MLB, NFL and NBA moneylines, spreads and totals.

Venues: Kalshi / Robinhood (same contracts; cost = ask + Kalshi's taker fee 0.07 x p x (1-p)) on every market, plus the sportsbook
moneylines The Odds API returns (DraftKings, FanDuel, BetMGM, BetRivers, Bovada, BetOnline, ...).
EV = fair chance x payout per $1 staked - 1.

Every run (from lines.py, after all boards are refreshed) it logs each side priced at EV >= 2% into backtest/ev_log.json, keeping the
first price it was seen at, and keeps updating every logged side's latest price and Pinnacle fair until the game starts. The last
fair before the start is the closing line: closing-line value (CLV) = the closing fair against the price we flagged. CLV is the
honest scorecard for +EV betting: if flagged prices keep beating the close, the edge is real well before wins and losses settle it."""
import os, json, glob, datetime, re
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest')
J = lambda p: json.load(open(p, encoding='utf-8'))
LOG = os.path.join(BT, 'ev_log.json')
MIN_EV = 0.02
kfee = lambda p: 0.07 * p * (1 - p)

def dec(american):
    a = float(american); return 1 + (a / 100 if a > 0 else 100 / -a)

MAX_KALSHI_EV = 0.15   # a main-line Kalshi price 15%+ better than Pinnacle is a mismatched or empty market, not an edge

def ev_kalshi(fair, ask):
    if not ask or not 0.02 <= ask <= 0.98 or fair is None: return None
    ev = fair / (ask + kfee(ask)) - 1
    return None if ev > MAX_KALSHI_EV else ev

def ev_book(fair, american):
    if american is None or fair is None: return None
    return fair * dec(american) - 1

def started(t, now):
    return datetime.datetime.fromisoformat(t.replace('Z', '+00:00')) <= now

def sides(now):
    """every (sport, game, market, side, venue) we can price right now, with its fair, price and EV. Upcoming games only."""
    out = []
    def add(sport, src, gid, game, time, market, side, venue, fair, price, ev, **kw):
        if ev is None or started(time, now): return
        out.append(dict(key=f'{sport}|{gid}|{market}|{side}|{venue}', sport=sport, src=src, id=str(gid), game=game, time=time, market=market, side=side,
                        venue=venue, fair=round(fair, 4), price=price, ev=round(ev, 4), **kw))
    today = datetime.date.today()
    tags = [today.isoformat()]                                                              # MLB: today's Pacific date
    wk = sorted(glob.glob(os.path.join(BT, 'ml_2026_wk*.json')), key=lambda p: int(re.search(r'wk(\d+)', p).group(1)))
    if wk: tags.append(os.path.basename(wk[-1])[3:-5])                                      # NFL: the current week
    for tag in tags:
        sport = 'NFL' if 'wk' in tag else 'MLB'
        mp = os.path.join(BT, f'ml_{tag}.json')
        for r in (J(mp) if os.path.exists(mp) else []):
            if r.get('sharpSrc') != 'pinnacle' or r.get('sharpHome') is None: continue
            gid = r.get('gamePk') or r.get('eventId'); game = f"{r['away']} @ {r['home']}"
            for side, team, fair, ask, bk in (('home', r['home'], r['sharpHome'], r.get('kalshiAsk'), 'home'), ('away', r['away'], 1 - r['sharpHome'], r.get('kalshiAwayAsk'), 'away')):
                add(sport, f'ml_{tag}', gid, game, r['time'], 'ML', team, 'Kalshi', fair, ask, ev_kalshi(fair, ask), home=side == 'home')
                for book, o in (r.get('books') or {}).items():
                    if book == 'pinnacle' or not o.get(bk): continue
                    add(sport, f'ml_{tag}', gid, game, r['time'], 'ML', team, book, fair, o[bk], ev_book(fair, o[bk]), home=side == 'home')
        lp = os.path.join(BT, f'lines_{tag}.json')
        for r in (J(lp) if os.path.exists(lp) else []):
            gid = r.get('gamePk') or r.get('eventId'); game = f"{r['away']} @ {r['home']}"; s, t = r.get('spread') or {}, r.get('total') or {}
            # NFL spreads only at Pinnacle's own line: a half point across 3 or 7 is worth far more than the flat ~2.5-point adjustment
            # (about 9% of games land on exactly 3), so an alt-line NFL spread would show an edge that isn't there
            if s.get('ticker') and s.get('pinFavFair') is not None and not (sport == 'NFL' and s.get('shift')):
                for nm, fair, ask in ((f"{s['fav']} -{s['line']}", s['pinFavFair'], s.get('favAsk')), (f"{s['dog']} +{s['line']}", s['pinDogFair'], s.get('dogAsk'))):
                    add(sport, f'lines_{tag}', gid, game, r['time'], 'Spread', nm, 'Kalshi', fair, ask, ev_kalshi(fair, ask), fav=nm.startswith(s['fav'] + ' '), pinLine=s.get('pinLine') if s.get('shift') else None)
            if t.get('ticker') and t.get('pinOverFair') is not None:
                for nm, fair, ask in ((f"Over {t['line']}", t['pinOverFair'], t.get('overAsk')), (f"Under {t['line']}", t['pinUnderFair'], t.get('underAsk'))):
                    add(sport, f'lines_{tag}', gid, game, r['time'], 'Total', nm, 'Kalshi', fair, ask, ev_kalshi(fair, ask), pinLine=t.get('pinLine') if t.get('shift') else None)
    for d in (today, today + datetime.timedelta(days=1)):
        np_ = os.path.join(BT, f'nba_{d.isoformat()}.json')
        for r in (J(np_) if os.path.exists(np_) else []):
            gid = r['eventId']; game = f"{r['away']} @ {r['home']}"; m, s, t = r.get('ml') or {}, r.get('spread') or {}, r.get('total') or {}
            src = f'nba_{d.isoformat()}'
            if m.get('pinHome') is not None:
                for team, fair, ask, h in ((r['home'], m['pinHome'], m.get('homeAsk'), True), (r['away'], m['pinAway'], m.get('awayAsk'), False)):
                    add('NBA', src, gid, game, r['time'], 'ML', team, 'Kalshi', fair, ask, ev_kalshi(fair, ask), home=h)
            if s.get('pinFavFair') is not None and s.get('ticker'):
                for nm, fair, ask in ((f"{s['fav']} -{s['line']}", s['pinFavFair'], s.get('favAsk')), (f"{s['dog']} +{s['line']}", s['pinDogFair'], s.get('dogAsk'))):
                    add('NBA', src, gid, game, r['time'], 'Spread', nm, 'Kalshi', fair, ask, ev_kalshi(fair, ask), fav=nm.startswith(s['fav'] + ' '), pinLine=s.get('pinLine') if s.get('shift') else None)
            if t.get('pinOverFair') is not None and t.get('ticker'):
                for nm, fair, ask in ((f"Over {t['line']}", t['pinOverFair'], t.get('overAsk')), (f"Under {t['line']}", t['pinUnderFair'], t.get('underAsk'))):
                    add('NBA', src, gid, game, r['time'], 'Total', nm, 'Kalshi', fair, ask, ev_kalshi(fair, ask), pinLine=t.get('pinLine') if t.get('shift') else None)
    # ---- NBA player props (nbaprops.py): every bettable book's price vs Pinnacle (or the sharp-book consensus), exact same line only
    import nbaprops as NP
    for d in (today - datetime.timedelta(days=1), today):
        pp = os.path.join(BT, f'nbaprops_{d.isoformat()}.json')
        for eid, g in (J(pp) if os.path.exists(pp) else {}).items():
            fair = NP.fair_prices(g['books'])
            for book, rows in g['books'].items():
                if book == 'pinnacle': continue
                for pl, mk, side, line, price in rows:
                    f3 = fair.get((pl, mk, line))
                    if not f3 or side not in ('Over', 'Under'): continue
                    fp = f3[0] if side == 'Over' else f3[1]; ev = ev_book(fp, price)
                    if ev is None or ev > 0.20: continue                                      # 20%+ on a prop = a stale or mismatched line
                    add('NBA', f'nbaprops_{d.isoformat()}', eid, g['game'], g['time'], 'Prop', f"{pl} {side} {line} {NP.LABEL.get(mk, mk)}", book, fp, price, ev,
                        player=pl, stat=mk, line=line, over=side == 'Over', fairSrc=f3[2])
    return out

def run():
    now = datetime.datetime.now(datetime.timezone.utc); at = now.isoformat(timespec='minutes')
    log = J(LOG) if os.path.exists(LOG) else {}
    cur = sides(now); n_new = 0
    for x in cur:
        e = log.get(x['key'])
        if e is None and x['ev'] >= MIN_EV:                                                  # first time this side is +EV: log the price it was seen at
            e = log[x['key']] = {k: x[k] for k in ('sport', 'src', 'id', 'game', 'time', 'market', 'side', 'venue') if k in x} | {k: x[k] for k in ('home', 'fav', 'pinLine', 'player', 'stat', 'line', 'over', 'fairSrc') if k in x}
            e.update(at=at, price=x['price'], fair=x['fair'], ev=x['ev']); n_new += 1
        if e is not None:                                                                    # every logged side: keep the latest pre-game view (the close)
            e.update(lastAt=at, lastPrice=x['price'], closeFair=x['fair'], lastEv=x['ev'])
    json.dump(log, open(LOG, 'w', encoding='utf-8'))
    json.dump({'at': at, 'sides': cur}, open(os.path.join(BT, 'ev_now.json'), 'w', encoding='utf-8'))
    live = [x for x in cur if x['ev'] >= MIN_EV]
    print(f"  ev: {len(cur)} prices vs Pinnacle, {len(live)} at +{MIN_EV:.0%} EV or better, {n_new} newly logged ({len(log)} tracked)")

if __name__ == '__main__':
    run()
