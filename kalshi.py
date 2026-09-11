"""Kalshi prediction-market prices for player props = the public's opinion with money behind it.
No key needed (public read API). Writes data/kalshi.json and appends a snapshot to backtest/kalshi_<date>.json.
MLB: series KXMLBHR   ('<Player>: 1+ home runs?')      NFL: series KXNFLGAMETD when it has open markets."""
import os, re, json, datetime, unicodedata, requests
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data'); BT = os.path.join(HERE, 'backtest')
API = "https://api.elections.kalshi.com/trade-api/v2/markets"
norm = lambda s: re.sub(r'[^a-z ]', '', unicodedata.normalize('NFD', s or '').encode('ascii', 'ignore').decode().lower()).strip()
MON = {m: i for i, m in enumerate(('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'), 1)}
def f(x):
    try: return float(x)
    except (TypeError, ValueError): return 0.0

def pull(series, want=re.compile(r'^(.*?): 1\+ (home run|touchdown)')):
    out, cursor = {}, None
    while True:
        p = {'series_ticker': series, 'status': 'open', 'limit': 200}
        if cursor: p['cursor'] = cursor
        r = requests.get(API, params=p, timeout=40); r.raise_for_status(); d = r.json()
        for m in d.get('markets', []):
            mt = want.match(m.get('title', ''))
            if not mt: continue
            # event ticker like KXMLBHR-26SEP111420PITCHC -> game date 2026-09-11 (local start time follows)
            em = re.search(r'-(\d\d)([A-Z]{3})(\d\d)', m.get('event_ticker', ''))
            if not em: continue
            date = f"20{em.group(1)}-{MON[em.group(2)]:02d}-{em.group(3)}"
            bid, ask = f(m.get('yes_bid_dollars')), f(m.get('yes_ask_dollars')); last = f(m.get('last_price_dollars'))
            px = (bid + ask) / 2 if bid and ask else (ask or last)
            if not px: continue
            out.setdefault(date, {})[norm(mt.group(1))] = {'yes': round(px, 3), 'bid': bid, 'ask': ask, 'last': last,
                'vol': round(f(m.get('volume_fp'))), 'vol24': round(f(m.get('volume_24h_fp'))), 'oi': round(f(m.get('open_interest_fp'))), 'ticker': m['ticker']}
        cursor = d.get('cursor')
        if not cursor: break
    return out

if __name__ == '__main__':
    res = {'_at': datetime.datetime.now().isoformat(timespec='minutes'), 'MLB': pull('KXMLBHR'), 'NFL': pull('KXNFLGAMETD')}
    for sp in ('MLB', 'NFL'):
        for date, ms in sorted(res[sp].items()): print(f"  Kalshi {sp} {date}: {len(ms)} players, ${sum(v['vol'] for v in ms.values()):,} traded")
    json.dump(res, open(os.path.join(DATA, 'kalshi.json'), 'w', encoding='utf-8'))
    for sp in ('MLB', 'NFL'):
        for date, ms in res[sp].items():
            sp_path = os.path.join(BT, f'kalshi_{sp.lower()}_{date}.json')
            snaps = json.load(open(sp_path, encoding='utf-8')) if os.path.exists(sp_path) else []
            snaps.append({'at': res['_at'], 'markets': ms}); json.dump(snaps, open(sp_path, 'w', encoding='utf-8'))
