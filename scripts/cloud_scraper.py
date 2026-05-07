"""
cloud_scraper.py
----------------
Runs in GitHub Actions. Auths to IPL Fantasy by replaying a long-lived
`my11_classic_game` cookie (extracted once from a logged-in browser).
The /classic/ API checks only this cookie for user identity, so we skip
the whole my11c OTP/Cognito flow.

Refresh the cookie if API auth ever starts failing — it lasts ~9 months.
"""

import json, os, re
import requests
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────
LEAGUE_ID  = "10310104"
BASE_URL   = "https://fantasy.iplt20.com"
HTML_FILE  = Path(__file__).parent.parent / "index.html"
HIST_FILE  = Path(__file__).parent / "history.json"

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/146.0.7680.178 Safari/537.36")


# ── Auth: replay the long-lived classic-game cookie ──────────────────
def make_session():
    """Build a requests.Session pre-authed via the IPL_CLASSIC_COOKIE secret.

    The cookie value is the raw URL-encoded JSON that My11Circle stores in
    the `my11_classic_game` cookie. Pull it from the env, paste it as-is.
    """
    cookie_value = os.environ.get("IPL_CLASSIC_COOKIE", "").strip()
    if not cookie_value:
        raise RuntimeError(
            "IPL_CLASSIC_COOKIE secret is empty. Extract it from a logged-in "
            "browser (cookie name `my11_classic_game` on fantasy.iplt20.com)."
        )
    # Sanity log so we can spot truncation/whitespace issues without leaking value.
    print(f"[AUTH] Cookie length={len(cookie_value)}, "
          f"starts={cookie_value[:6]!r}, ends={cookie_value[-6:]!r}")

    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    s.cookies.set("my11_classic_game", cookie_value,
                  domain="fantasy.iplt20.com", path="/")
    return s


# ── Scrape ───────────────────────────────────────────────────────────
def scrape():
    session = make_session()
    print("[SCRAPE] Getting gameday info...")
    resp = session.get(f"{BASE_URL}/classic/api/live/mixapi?lang=en")
    try:
        mix = resp.json()
    except Exception as e:
        print(f"[SCRAPE] mixapi JSON parse failed: {e}, body[:200]={resp.text[:200]!r}")
        mix = {}
    gd = 0
    if mix.get("Data", {}).get("Value"):
        gd = mix["Data"]["Value"].get("GamedayId", 0)

    # Get next upcoming match from tour-fixtures (future MatchdateTime)
    t1, t2, match_no = "?", "?", gd
    try:
        fix_resp = session.get(f"{BASE_URL}/classic/api/feed/tour-fixtures?lang=en")
        fix_data = fix_resp.json()
        fix_list = (fix_data.get("Data") or {}).get("Value") or {}
        if isinstance(fix_list, dict):
            fix_list = fix_list.get("Fixtures") or fix_list.get("fixtures") or []
        elif not isinstance(fix_list, list):
            fix_list = []

        now_ts = datetime.now(timezone.utc).timestamp()

        def _parse_ts(fx):
            mdt = fx.get("MatchdateTime", "") or fx.get("Matchdate", "")
            if not mdt:
                return 0
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(mdt[:19], fmt).timestamp()
                except ValueError:
                    pass
            return 0

        future = [fx for fx in fix_list
                  if isinstance(fx, dict) and fx.get("HomeTeamShortName") and _parse_ts(fx) > now_ts]
        if future:
            future.sort(key=_parse_ts)
            f = future[0]
        else:
            # fallback: first unlocked
            f = next((fx for fx in fix_list
                      if isinstance(fx, dict) and fx.get("IsLocked") == 0 and fx.get("HomeTeamShortName")), {})
        if f:
            t1 = f.get("HomeTeamShortName", "?")
            t2 = f.get("AwayTeamShortName", "?")
            match_no = f.get("Gameday") or gd
    except Exception as e:
        print(f"[SCRAPE] tour-fixtures failed: {e}")

    print(f"[SCRAPE] Gameday: {gd}, Next: {t1} vs {t2} (Match {match_no})")

    # Step 5: Get leaderboard
    print("[SCRAPE] Fetching leaderboard...")
    lb_url = (
        f"{BASE_URL}/classic/api/user/leagues/live/{LEAGUE_ID}/leaderboard"
        f"?optType=1&gamedayId={gd}&phaseId=1&pageNo=1&topNo=500"
        f"&pageChunk=500&pageOneChunk=500&minCount=8&leagueId={LEAGUE_ID}"
    )
    resp = session.get(lb_url)
    try:
        lb = resp.json()
    except Exception as e:
        print(f"[SCRAPE] leaderboard JSON parse failed: {e}, body[:500]={resp.text[:500]!r}")
        raise RuntimeError("Leaderboard returned non-JSON")
    meta = lb.get('Meta', {})
    if not meta.get("Success"):
        # Most common cause: the long-lived cookie expired. Refresh
        # IPL_CLASSIC_COOKIE by re-extracting from a logged-in browser.
        print(f"[SCRAPE] Leaderboard auth failed: {json.dumps(meta)}")
        raise RuntimeError(
            f"Leaderboard API failed: {meta.get('Message', 'unknown')} — "
            "the IPL_CLASSIC_COOKIE secret may have expired."
        )

    standings = []
    for e in lb.get("Data", {}).get("Value", []):
        standings.append({"rank": e["rank"], "name": e["temname"], "pts": e["points"]})

    standings = sorted(standings, key=lambda x: x["rank"])
    next_match = {"no": match_no, "teams": [t1, t2], "time": ""}
    print(f"[SCRAPE] Got {len(standings)} teams")
    return standings, next_match


# ── Update HTML ───────────────────────────────────────────────────────
def load_history():
    if HIST_FILE.exists():
        return json.loads(HIST_FILE.read_text(encoding="utf-8"))
    return {"labels": [], "teams": {}, "playerData": {}}

def save_history(h):
    HIST_FILE.write_text(json.dumps(h, indent=2, ensure_ascii=False), encoding="utf-8")

def update_html(standings, next_match):
    if not HTML_FILE.exists():
        print(f"[!] HTML not found: {HTML_FILE}")
        return

    html = HTML_FILE.read_text(encoding="utf-8")
    today_label = datetime.now().strftime("%d %b %Y")
    match_no = next_match.get("no", 0)
    completed_match = match_no - 1 if match_no > 0 else 0
    today_key = f"Match {completed_match}" if completed_match > 0 else datetime.now().strftime("%d %b")

    hist = load_history()
    if today_key not in hist.get("labels", []):
        hist.setdefault("labels", []).append(today_key)
    hist.setdefault("teams", {})

    for s in standings:
        hist["teams"].setdefault(s["name"], [])
        while len(hist["teams"][s["name"]]) < len(hist["labels"]) - 1:
            hist["teams"][s["name"]].append(None)
        day_idx = hist["labels"].index(today_key)
        if len(hist["teams"][s["name"]]) > day_idx:
            hist["teams"][s["name"]][day_idx] = s["pts"]
        else:
            hist["teams"][s["name"]].append(s["pts"])

    save_history(hist)

    standings_js = json.dumps(
        [{"rank": s["rank"], "name": s["name"], "pts": s["pts"]} for s in standings],
        ensure_ascii=False
    )
    cum_labels = json.dumps(hist["labels"])
    cum_data_js = json.dumps({n: p for n, p in hist["teams"].items()}, ensure_ascii=False)

    t = next_match.get("teams", ["?", "?"])
    new_data_block = f"""<!-- DATA_START -->
<script>
const D = {{
  lastUpdated: "{today_label}",
  leagueName: "Zanvil IPL 2026",
  nextMatch: {{ no:{next_match.get('no','?')}, t1:"{t[0]}", t1full:"", t2:"{t[1] if len(t) > 1 else '?'}", t2full:"", time:"{next_match.get('time','')}" }},
  todayTeams: {json.dumps(t)},
  standings: {standings_js},
  matchPts: {{
    labels: {cum_labels},
    perMatch: {{}},
    cumulative: {cum_data_js}
  }},
  teams: TEAMS_PLACEHOLDER
}};
</script>
<!-- DATA_END -->"""

    teams_m = re.search(r'teams:\s*\{(.*?)\n\s*\}\s*\};', html, re.S)
    if teams_m:
        new_data_block = new_data_block.replace(
            "teams: TEAMS_PLACEHOLDER",
            "teams:{\n" + teams_m.group(1) + "\n  }"
        )
    else:
        new_data_block = new_data_block.replace("teams: TEAMS_PLACEHOLDER", "teams:{}")

    # Use a lambda so backslash sequences (e.g. \s) inside the JSON payload
    # aren't misinterpreted as backreferences by re.sub.
    updated = re.sub(
        r'<!-- DATA_START -->.*?<!-- DATA_END -->',
        lambda _: new_data_block,
        html,
        flags=re.S,
    )
    HTML_FILE.write_text(updated, encoding="utf-8")
    print(f"[OK] HTML updated: {today_label}")


# ── MAIN ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  Zanvil IPL 2026 - Cloud Scraper")
    print(f"  {datetime.now().strftime('%d %b %Y  %H:%M UTC')}")
    print("=" * 50)

    standings, next_match = scrape()
    update_html(standings, next_match)

    print("\nStandings:")
    for s in standings:
        print(f"  {s['rank']}. {s['name']}: {s['pts']}")
    print("\n[DONE]")
