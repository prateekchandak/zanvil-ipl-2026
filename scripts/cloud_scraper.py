"""
cloud_scraper.py
----------------
Runs in GitHub Actions. Uses direct API calls to authenticate with
IPL Fantasy (email OTP via Gmail IMAP) and fetch league standings.
No browser needed.
"""

import json, re, time, os, sys
import requests
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────
LEAGUE_ID  = "10310104"
BASE_URL   = "https://fantasy.iplt20.com"
EMAIL      = os.environ.get("IPL_EMAIL", "prateekchandak10@gmail.com")
HTML_FILE  = Path(__file__).parent.parent / "index.html"
HIST_FILE  = Path(__file__).parent / "history.json"

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/my11c/static/login.html",
}


# ── Gmail OTP reader (via IMAP) ──────────────────────────────────────
def get_otp_from_gmail(max_wait=120):
    """Read the latest OTP from Gmail using IMAP + App Password.
    Marks old OTP emails as read first, then waits for a fresh one."""
    import imaplib
    import email as emaillib

    imap_user = os.environ.get("IPL_EMAIL", EMAIL)
    imap_pass = os.environ["GMAIL_APP_PASSWORD"]

    # Mark all existing OTP emails as read
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(imap_user, imap_pass)
        mail.select("inbox")
        _, msg_ids = mail.search(None, '(UNSEEN SUBJECT "OTP")')
        if msg_ids[0]:
            for mid in msg_ids[0].split():
                mail.store(mid, '+FLAGS', '\\Seen')
            print(f"[GMAIL] Marked {len(msg_ids[0].split())} old OTP emails as read")
        mail.logout()
    except Exception as e:
        print(f"[GMAIL] Could not clear old OTPs: {e}")

    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(imap_user, imap_pass)
            mail.select("inbox")

            _, msg_ids = mail.search(None, '(UNSEEN SUBJECT "OTP")')
            if not msg_ids[0]:
                _, msg_ids = mail.search(None, '(UNSEEN SUBJECT "verification")')

            ids = msg_ids[0].split()
            if ids:
                _, msg_data = mail.fetch(ids[-1], "(RFC822)")
                raw = msg_data[0][1]
                msg = emaillib.message_from_bytes(raw)

                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ct = part.get_content_type()
                        if ct in ("text/plain", "text/html"):
                            try:
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                if body:
                                    break
                            except:
                                pass
                else:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

                otp_match = re.search(r'\b(\d{4,6})\b', body)
                if otp_match:
                    otp = otp_match.group(1)
                    print(f"[GMAIL] Found OTP: {'*' * (len(otp)-2)}{otp[-2:]}")
                    mail.store(ids[-1], '+FLAGS', '\\Seen')
                    mail.logout()
                    return otp

            mail.logout()
        except Exception as e:
            print(f"[GMAIL] IMAP error: {e}")

        print(f"[GMAIL] Waiting for OTP email... ({int(time.time()-start_time)}s)")
        time.sleep(5)

    raise RuntimeError("Timed out waiting for OTP email")


# ── API-based login + scrape ─────────────────────────────────────────
def scrape():
    session = requests.Session()
    session.headers.update(HEADERS)

    # Step 1: Send OTP to email
    print(f"[LOGIN] Sending OTP to {EMAIL[:3]}***")
    resp = session.post(
        f"{BASE_URL}/my11c/api/fl/auth/tokenize/v1/external/sendEmail",
        json={"email": EMAIL}
    )
    print(f"[LOGIN] sendEmail response: {resp.status_code}")
    send_data = resp.json()
    print(f"[LOGIN] sendEmail result: success={send_data.get('success')}, msg={send_data.get('errorMessage', send_data.get('message', 'ok'))}")

    if not send_data.get("success", True) and send_data.get("errorCode") not in (None, 200):
        # If sendEmail fails, try alternate endpoint
        print("[LOGIN] Trying alternate login endpoint...")
        resp = session.post(
            f"{BASE_URL}/my11c/api/fl/auth/v3/getOtp",
            json={"Mobile": EMAIL, "loginid": EMAIL}
        )
        print(f"[LOGIN] getOtp response: {resp.status_code} - {resp.text[:200]}")
        send_data = resp.json()

    # Extract session token if present
    session_token = send_data.get("data", {}).get("Session") if isinstance(send_data.get("data"), dict) else None
    print(f"[LOGIN] Session token: {'found' if session_token else 'not in response'}")

    # Step 2: Get OTP from Gmail
    print("[LOGIN] Waiting for OTP email...")
    time.sleep(10)  # Give time for email delivery
    otp = get_otp_from_gmail(max_wait=120)

    # Step 3: Verify OTP
    print(f"[LOGIN] Verifying OTP...")
    verify_payload = {"email": EMAIL, "otp": otp}
    if session_token:
        verify_payload["Session"] = session_token

    resp = session.post(
        f"{BASE_URL}/my11c/api/fl/auth/tokenize/v1/external/verifyEmailOtp",
        json=verify_payload
    )
    print(f"[LOGIN] verifyOtp response: {resp.status_code}")
    verify_data = resp.json()
    print(f"[LOGIN] verifyOtp result: success={verify_data.get('success')}")

    if not verify_data.get("success"):
        # Try alternate verify endpoint
        print(f"[LOGIN] Verify failed: {verify_data.get('errorMessage', 'unknown')}")
        print(f"[LOGIN] Full response: {json.dumps(verify_data)[:500]}")

        # Try v3 authenticate
        resp = session.post(
            f"{BASE_URL}/my11c/api/fl/auth/v3/authenticate",
            json={"Mobile": EMAIL, "loginid": EMAIL, "otp": otp}
        )
        print(f"[LOGIN] v3 authenticate: {resp.status_code} - {resp.text[:300]}")
        verify_data = resp.json()

    # Extract auth info
    auth_data = verify_data.get("data", {})
    if isinstance(auth_data, dict):
        uid = auth_data.get("uid") or auth_data.get("userId")
        token = auth_data.get("authToken") or auth_data.get("token")
        if uid:
            session.cookies.set("my11c-uid", uid, domain="fantasy.iplt20.com")
        if token:
            session.cookies.set("my11c-authToken", token, domain="fantasy.iplt20.com")
        print(f"[LOGIN] Auth: uid={'found' if uid else 'missing'}, token={'found' if token else 'missing'}")

    # Also check if cookies were set via Set-Cookie header
    print(f"[LOGIN] Cookies: {[c.name for c in session.cookies]}")

    # Step 4: Get gameday from public API
    print("[SCRAPE] Getting gameday info...")
    resp = session.get(f"{BASE_URL}/classic/api/live/mixapi?lang=en")
    mix = resp.json()
    gd = 0
    t1, t2 = "?", "?"
    if mix.get("Data", {}).get("Value"):
        gd = mix["Data"]["Value"].get("GamedayId", 0)
        fixtures = mix["Data"]["Value"].get("LiveFixture", [])
        if fixtures:
            t1 = fixtures[0].get("HomeTeamShortName", "?")
            t2 = fixtures[0].get("AwayTeamShortName", "?")
    print(f"[SCRAPE] Gameday: {gd}, Next: {t1} vs {t2}")

    # Step 5: Get leaderboard
    print("[SCRAPE] Fetching leaderboard...")
    lb_url = (
        f"{BASE_URL}/classic/api/user/leagues/live/{LEAGUE_ID}/leaderboard"
        f"?optType=1&gamedayId={gd}&phaseId=1&pageNo=1&topNo=500"
        f"&pageChunk=500&pageOneChunk=500&minCount=8&leagueId={LEAGUE_ID}"
    )
    resp = session.get(lb_url)
    lb = resp.json()
    print(f"[SCRAPE] Leaderboard response: success={lb.get('Meta', {}).get('Success')}, msg={lb.get('Meta', {}).get('Message', '')}")

    if not lb.get("Meta", {}).get("Success"):
        print(f"[SCRAPE] Leaderboard failed: {json.dumps(lb.get('Meta', {}))}")
        raise RuntimeError(f"Leaderboard API failed: {lb.get('Meta', {}).get('Message', 'unknown')}")

    standings = []
    for e in lb.get("Data", {}).get("Value", []):
        standings.append({"rank": e["rank"], "name": e["temname"], "pts": e["points"]})

    standings = sorted(standings, key=lambda x: x["rank"])
    next_match = {"no": gd, "teams": [t1, t2], "time": ""}
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
