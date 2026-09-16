import requests
H = [{'User-Agent': 'Mozilla/5.0'},
     {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36', 'Accept': 'application/json, text/plain, */*', 'Accept-Language': 'en-US,en;q=0.9', 'Referer': 'https://www.espn.com/', 'Origin': 'https://www.espn.com'}]
U = ['https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard',
     'https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard',
     'https://cdn.espn.com/core/nfl/scoreboard?xhr=1',
     'https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events?limit=5',
     'https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard']
for u in U:
    for i, h in enumerate(H):
        try: r = requests.get(u, headers=h, timeout=20); print(r.status_code, 'hdr' + str(i), u, r.text[:60].replace('\n', ' '))
        except Exception as e: print('ERR', 'hdr' + str(i), u, e)
