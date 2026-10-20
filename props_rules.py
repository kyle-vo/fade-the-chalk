"""NFL player-prop rule, shared by the page (build_fantasy.py) and its scorecard so both grade the exact same calls.
Found on weeks 1-4 of every Kalshi prop market (research/nflprops_*.json: price at kickoff, settlement), checked on weeks 5-6.

  PROP BET = the main line (strike priced nearest 50c) on a player whose team is the UNDERDOG (Kalshi win price under 45%):
      RB rushing yards UNDER, QB rushing yards UNDER, TE receiving yards UNDER, QB passing yards OVER
    358 bets, +11.8% at the kickoff price plus fee and a cent of slippage; positive in all 6 weeks (+3 / +17 / +21 / +12 / +4 / +13%).
    The same four on favorites were break-even (+0.4%), so they are not bets.

What was tried and dropped: our own projection vs the line (lost at every threshold), fading the crowd's money on the prop, the
under after a big game (+8% weeks 1-4, -13% weeks 5-6), overs in general (-9%), longshot alt lines. First-TD and 2+ TD YES lose
about a third of the stake every week (-35% to -47%). Anytime-TD calls stay on the main board (no TD yet + team the spread crowd is fading)."""
STAT = {'KXNFLREC': 'rec', 'KXNFLRECYDS': 'recYds', 'KXNFLRSHYDS': 'rushYds', 'KXNFLPASSYDS': 'passYds'}
LABEL = {'KXNFLREC': 'receptions', 'KXNFLRECYDS': 'rec yds', 'KXNFLRSHYDS': 'rush yds', 'KXNFLPASSYDS': 'pass yds'}
RULES = {('RB', 'KXNFLRSHYDS'): 'UNDER', ('QB', 'KXNFLRSHYDS'): 'UNDER', ('TE', 'KXNFLRECYDS'): 'UNDER', ('QB', 'KXNFLPASSYDS'): 'OVER'}
DOG = 0.45

def main_lines(markets, mid):
    """one market per (player, series): the yardage / reception strike priced nearest 50c (mid = YES price estimate)"""
    best = {}
    for m in markets:
        if m['series'] not in STAT or m.get('strike') is None: continue
        p = mid(m)
        if p is None or not 0.3 <= p <= 0.7: continue
        k = (m['name'], m['series'])
        if k not in best or abs(p - 0.5) < best[k][0]: best[k] = (abs(p - 0.5), m)
    return [m for _, m in best.values()]

def verdict(pos, series, winP):
    """-> ('BET', 'UNDER'/'OVER') when the rule fires, (None, side) when it is one of the four props on a non-underdog, else (None, None)"""
    side = RULES.get((pos, series))
    if not side: return None, None
    return ('BET' if winP is not None and winP < DOG else None), side
