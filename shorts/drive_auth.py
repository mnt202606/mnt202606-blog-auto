import pickle
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

BASE = Path(__file__).parent
CLIENT_SECRET = BASE / "secrets" / "youtube_client_secret.json"
TOKEN_FILE = BASE / "secrets" / "drive_token.pickle"

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
creds = flow.run_local_server(port=0)
with open(TOKEN_FILE, "wb") as f:
    pickle.dump(creds, f)
print("OK")
