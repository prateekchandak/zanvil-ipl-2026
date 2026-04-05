"""
cloud_scraper.py
----------------
Runs in GitHub Actions. Uses Playwright to log in to IPL Fantasy
(with OTP from Gmail API), scrape standings, and update index.html.
"""

import json, re, time, os, sys, base64
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────
LEAGUE_ID  = "10310104"
LEAGUE_URL = f"https://fantasy.iplt20.com/classic/league/view/{LEAGUE_ID}"
LOGIN_URL  = "https://fantasy.iplt20.com/classic/home"
EMAIL      = os.environ.get("IPL_EMAIL", "prateekchandak10@gmail.com")
HTML_FILE  = Path(__file__).parent.parent / "index.html"
HIST_FILE  = Path(__file__).parent / "history.json"

# ── Gmail OTP reader ──────────────────────────────────────────────────
def get_otp_from_gmail(max_wait=60):
    """Read the latest OTP from Gmail using Google API."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token"
    )

    service = build("gmail", "v1", credentials=creds)
    start_time = time.time()

    while time.time() - start_time < max_wait:
        results = service.users().messages().list(
            userId="me",
            q="from:noreply subject:OTP newer_than:2m",
            maxResults=1
        ).execute()

        messages = results.get("messages", [])
        if messages:
            msg = service.users().messages().get(
                userId="me", id=messages[0]["id"], format="full"
            ).execute()

            # Extract OTP from email body
            payload = msg.get("payload", {})
            body = ""
            if payload.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
            else:
                for part in payload.get("parts", []):
                    if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                        body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                        break
                    elif part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
                        body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")

            # Find 4-6 digit OTP in body
            import re as _re
            otp_match = _re.search(r'\b(\d{4,6})\b', body)
            if otp_match:
                otp = otp_match.group(1)
                print(f"[GMAIL] Found OTP: {'*' * (len(otp)-2)}{otp[-2:]}")
                return otp

        print(f"[GMAIL] Waiting for OTP email... ({int(time.time()-start_time)}s)")
        time.sleep(5)

    raise RuntimeError("Timed out waiting for OTP email")


# ── Playwright login + scrape ─────────────────────────────────────────
def scrape():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # ── Login flow ────────────────────────────────────────────
        print("[LOGIN] Navigating to login page...")
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        time.sleep(3)

        # Check if already logged in (unlikely in fresh browser)
        if "league" in page.url or "home" in page.url:
            title = page.title()
            if "Login" not in title:
                print("[LOGIN] Already authenticated!")
            else:
                print(f"[LOGIN] On login page, entering email: {EMAIL[:3]}***")
                # Enter email
                page.fill("#email_input", EMAIL)
                time.sleep(1)
                page.click("#registerCTA")
                print("[LOGIN] Email submitted, waiting for OTP...")
                time.sleep(5)

                # Get OTP from Gmail
                otp = get_otp_from_gmail(max_wait=90)
                print("[LOGIN] Entering OTP...")
                page.fill("#otpInputField", otp)
                time.sleep(1)
                page.click("#verifyOtp")
                print("[LOGIN] OTP submitted, waiting for login...")
                page.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(5)

        # ── Navigate to league ────────────────────────────────────
        print("[SCRAPE] Navigating to league page...")
        page.goto(LEAGUE_URL, wait_until="networkidle", timeout=30000)
        time.sleep(8)

        if "Login" in page.title():
            raise RuntimeError("Login failed - still on login page after OTP")

        # ── Call API from browser context ─────────────────────────
        print("[SCRAPE] Calling leaderboard API...")
        result = page.evaluate("""() => {
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/classic/api/live/mixapi?lang=en', false);
            xhr.send();
            var mix = JSON.parse(xhr.responseText);
            var gd = mix.Data && mix.Data.Value ? mix.Data.Value.GamedayId : 0;

            xhr.open('GET', '/classic/api/user/leagues/live/""" + LEAGUE_ID + """/leaderboard?optType=1&gamedayId=' + gd + '&phaseId=1&pageNo=1&topNo=500&pageChunk=500&pageOneChunk=500&minCount=8&leagueId=""" + LEAGUE_ID + """', false);
            xhr.send();
            var lb = JSON.parse(xhr.responseText);

            var standings = [];
            if (lb.Data && lb.Data.Value) {
                for (var i = 0; i < lb.Data.Value.length; i++) {
                    var e = lb.Data.Value[i];
                    standings.push({rank: e.rank, name: e.temname, pts: e.points});
                }
            }
            var fixtures = (mix.Data && mix.Data.Value) ? (mix.Data.Value.LiveFixture || []) : [];
            var f = fixtures[0] || {};
            return {
                standings: standings,
                gameday: gd,
                t1: f.HomeTeamShortName || '?',
                t2: f.AwayTeamShortName || '?',
                success: lb.Meta && lb.Meta.Success
            };
        }""")

        browser.close()

        if not result or not result.get("standings"):
            raise RuntimeError(f"API returned no data: {result}")

        standings = sorted(result["standings"], key=lambda x: x["rank"])
        next_match = {
            "no": result.get("gameday", 0),
            "teams": [result.get("t1", "?"), result.get("t2", "?")],
            "time": ""
        }
        print(f"[SCRAPE] Got {len(standings)} teams (gameday {next_match['no']})")
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

    updated = re.sub(
        r'<!-- DATA_START -->.*?<!-- DATA_END -->',
        new_data_block,
        html,
        flags=re.S
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
