"""
One-time setup: Generate Gmail API refresh token for GitHub Actions.

Steps:
1. Go to https://console.cloud.google.com/
2. Create a project (or use existing)
3. Enable "Gmail API"
4. Go to Credentials > Create Credentials > OAuth 2.0 Client ID
5. Application type: Desktop app
6. Download the JSON, save as 'client_secret.json' in this folder
7. Run this script: python setup_gmail_token.py
8. It will open a browser for you to authorize
9. Copy the printed values into GitHub Secrets
"""

import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0)

print("\n" + "=" * 60)
print("  Add these as GitHub Secrets in your repo:")
print("=" * 60)
print(f"\nGMAIL_CLIENT_ID:\n{creds.client_id}")
print(f"\nGMAIL_CLIENT_SECRET:\n{creds.client_secret}")
print(f"\nGMAIL_REFRESH_TOKEN:\n{creds.refresh_token}")
print(f"\nIPL_EMAIL:\nprateekchandak10@gmail.com")
print("\n" + "=" * 60)
print("Go to: https://github.com/prateekchandak/zanvil-ipl-2026/settings/secrets/actions")
print("Add each secret above.")
