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
    """Read the latest UNSEEN OTP from Gmail using IMAP + App Password.
    Old OTP emails should be marked as read before calling this."""
    import imaplib
    import email as emaillib

    imap_user = os.environ.get("IPL_EMAIL", EMAIL)
    imap_pass = os.environ["GMAIL_APP_PASSWORD"]

    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(imap_user, imap_pass)
            mail.select("inbox")

            # Search for any unread email with OTP/verification/code in subject
            _, msg_ids = mail.search(None, '(UNSEEN SUBJECT "OTP")')
            if not msg_ids[0]:
                _, msg_ids = mail.search(None, '(UNSEEN SUBJECT "verification")')
            if not msg_ids[0]:
                _, msg_ids = mail.search(None, '(UNSEEN SUBJECT "code")')

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

    # Step 0: Mark ALL recent unread emails as read to avoid stale OTPs
    print("[LOGIN] Clearing old OTP/verification emails...")
    import imaplib
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.environ.get("IPL_EMAIL", EMAIL), os.environ["GMAIL_APP_PASSWORD"])
        mail.select("inbox")
        total_marked = 0
        for search in ['(UNSEEN SUBJECT "OTP")', '(UNSEEN SUBJECT "verification")',
                       '(UNSEEN SUBJECT "code")', '(UNSEEN SUBJECT "confirm")']:
            _, msg_ids = mail.search(None, search)
            if msg_ids[0]:
                for mid in msg_ids[0].split():
                    mail.store(mid, '+FLAGS', '\\Seen')
                total_marked += len(msg_ids[0].split())
        if total_marked:
            print(f"[LOGIN] Marked {total_marked} old emails as read")
        mail.logout()
    except Exception as e:
        print(f"[LOGIN] Could not clear old emails: {e}")

    # Step 1: Send OTP to email
    print(f"[LOGIN] Sending OTP to {EMAIL[:3]}***")
    resp = session.post(
        f"{BASE_URL}/my11c/api/fl/auth/tokenize/v1/external/sendEmail",
        json={"email": EMAIL}
    )
    print(f"[LOGIN] sendEmail status: {resp.status_code}")
    print(f"[LOGIN] sendEmail headers: {dict(resp.headers)}")
    raw_text = resp.text
    print(f"[LOGIN] sendEmail body: {raw_text[:500]}")

    # Try to parse as JSON
    try:
        send_data = resp.json()
    except:
        send_data = {}

    # Extract session token - could be at various paths
    session_token = None
    if isinstance(send_data, dict):
        session_token = send_data.get("Session")
        if not session_token and isinstance(send_data.get("data"), dict):
            session_token = send_data["data"].get("Session")
        if not session_token:
            # Check all string values for session-like tokens
            for k, v in send_data.items():
                if isinstance(v, str) and len(v) > 50:
                    print(f"[LOGIN] Potential session in field '{k}': {v[:30]}...")
    print(f"[LOGIN] Session token: {'found' if session_token else 'not found'}")

    # Step 2: Wait for OTP email and retrieve it
    print("[LOGIN] Waiting for OTP email (20s for delivery)...")
    time.sleep(20)  # Must wait for NEW email to arrive
    otp = get_otp_from_gmail(max_wait=120)

    # Step 3: Verify OTP with Cognito session
    print(f"[LOGIN] Verifying OTP with session...")

    # The Cognito verifyEmailOtp needs: email, otp (called "answer"), Session
    # Try different field name variations
    payloads_to_try = [
        {"email": EMAIL, "answer": otp, "Session": session_token},
        {"email": EMAIL, "otp": otp, "Session": session_token},
        {"email": EMAIL, "answer": otp, "session": session_token},
        {"Username": EMAIL, "ConfirmationCode": otp, "Session": session_token},
    ]

    verify_data = {}
    for i, payload in enumerate(payloads_to_try):
        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}
        resp = session.post(
            f"{BASE_URL}/my11c/api/fl/auth/tokenize/v1/external/verifyEmailOtp",
            json=payload
        )
        print(f"[LOGIN] verify attempt {i+1}: {resp.status_code} - {resp.text[:300]}")

        # Check if cookies were set
        if session.cookies.get("my11c-authToken"):
            print("[LOGIN] Got auth cookie!")
            break

        try:
            verify_data = resp.json()
            if verify_data.get("success"):
                break
        except:
            pass

    # Extract auth from response data if cookies weren't set
    if not session.cookies.get("my11c-authToken"):
        try:
            auth_data = resp.json().get("data", {})
            if isinstance(auth_data, dict):
                uid = auth_data.get("uid") or auth_data.get("userId")
                token = auth_data.get("authToken") or auth_data.get("token") or auth_data.get("AccessToken")
                if uid:
                    session.cookies.set("my11c-uid", str(uid), domain="fantasy.iplt20.com")
                if token:
                    session.cookies.set("my11c-authToken", str(token), domain="fantasy.iplt20.com")
                print(f"[LOGIN] Manual auth: uid={'found' if uid else 'missing'}, token={'found' if token else 'missing'}")
        except:
            pass

    print(f"[LOGIN] Final cookies: {[c.name for c in session.cookies]}")

    # Step 4: Get gameday from mixapi, next match from tour-fixtures
    print("[SCRAPE] Getting gameday info...")
    resp = session.get(f"{BASE_URL}/classic/api/live/mixapi?lang=en")
    mix = resp.json()
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

        now_ts = datetime.utcnow().timestamp()

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
    lb = resp.json()
    print(f"[SCRAPE] Leaderboard response: success={lb.get('Meta', {}).get('Success')}, msg={lb.get('Meta', {}).get('Message', '')}")

    if not lb.get("Meta", {}).get("Success"):
        print(f"[SCRAPE] Leaderboard failed: {json.dumps(lb.get('Meta', {}))}")
        raise RuntimeError(f"Leaderboard API failed: {lb.get('Meta', {}).get('Message', 'unknown')}")

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
