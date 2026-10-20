"""NFL player-prop rules, shared by the page (build_fantasy.py) and the backtest so both grade the exact same calls.
Fitted on weeks 1-4 of every Kalshi prop market (research/nflprops_*.json: price at kickoff, settlement), checked on weeks 5-6.

  TD (anytime, 1+):
    BET   YES  no TD yet in 2+ games, his team has LESS of the crowd's spread money, priced under 35c
    FADE  NO   scored earlier this season but blanked his last game (the market overprices the bounce-back)
  yards / receptions (main line = the strike priced nearest 50c):
    UNDER      he cleared 1.5x this line last game (the market chases one big game)
  First-TD and 2+ TD YES lose about a third of the stake (longshots priced far above their real odds): never a bet."""
STAT = {'KXNFLREC': 'rec', 'KXNFLRECYDS': 'recYds', 'KXNFLRSHYDS': 'rushYds', 'KXNFLPASSYDS': 'passYds'}
LABEL = {'KXNFLTD': 'anytime TD', 'KXNFLREC': 'receptions', 'KXNFLRECYDS': 'rec yds', 'KXNFLRSHYDS': 'rush yds', 'KXNFLPASSYDS': 'pass yds'}

def main_lines(markets, price):
    """one market per (player, series): the yardage / reception strike priced nearest 50c, and the 1+ TD market"""
    best = {}
    for m in markets:
        p = price(m)
        if p is None: continue
        s = m['series']
        if s == 'KXNFLTD':
            if m.get('strike') is None or float(m['strike']) > 1: continue
        elif s not in STAT: continue
        k = (m['name'], s); d = abs(p - 0.5) if s != 'KXNFLTD' else 0
        if k not in best or d < best[k][0]: best[k] = (d, m)
    return [m for _, m in best.values()]

def verdict(m, px, ctx):
    """m: market (series, strike); px: YES price; ctx: player context
         gp, last (dict stat -> last game value), tdGames, lastTD (0/1), spTeam (share of spread $ on his team or None)
       -> (call, side, why) with call in BET / FADE / UNDER or None"""
    s, k = m['series'], m.get('strike')
    gp = ctx.get('gp') or 0
    if s == 'KXNFLTD':
        noTD = gp >= 2 and ctx.get('tdGames') == 0
        cold = (ctx.get('tdGames') or 0) >= 1 and ctx.get('lastTD') == 0
        sp = ctx.get('spTeam')
        if noTD and sp is not None and sp < 0.5 and px < 0.35:
            return 'BET', 'YES', f"no TD in {gp} games, {round(sp * 100)}% of the spread $ on his team"
        if cold:
            return 'FADE', 'NO', 'scored earlier this year, blanked last game'
        return None, None, ''
    if s in STAT and k is not None and gp >= 1:
        last = (ctx.get('last') or {}).get(STAT[s])
        if last is not None and float(k) > 0 and last >= 1.5 * float(k):
            return 'UNDER', 'NO', f"had {last:g} last game vs this {float(k):g} line"
    return None, None, ''
