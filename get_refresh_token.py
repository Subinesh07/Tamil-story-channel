"""Run ONCE on your laptop to get the YouTube refresh token.

1. pip install google-auth-oauthlib
2. Put the OAuth client file you downloaded from Google Cloud next to this script,
   named client_secret.json
3. python get_refresh_token.py
4. A browser opens: sign in with the Google account that OWNS THE YOUTUBE CHANNEL and allow access.
5. Copy the three printed values into GitHub -> Settings -> Secrets and variables -> Actions.
   Then delete client_secret.json from your laptop if you like. Never commit it.
"""
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
client = json.loads(Path("client_secret.json").read_text())
info = client.get("installed") or client.get("web")

print("\nAdd these three GitHub secrets (keep them private):\n")
print("YT_CLIENT_ID      =", info["client_id"])
print("YT_CLIENT_SECRET  =", info["client_secret"])
print("YT_REFRESH_TOKEN  =", creds.refresh_token)
