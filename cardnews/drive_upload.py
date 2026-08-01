import sys
import json
import pickle
from pathlib import Path

import requests
from google.auth.transport.requests import Request

BASE = Path(__file__).parent
TOKEN_FILE = BASE / "secrets" / "drive_token.pickle"


def get_creds():
    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
    return creds


def upload(local_path, name, mimetype="video/mp4"):
    creds = get_creds()
    headers = {"Authorization": f"Bearer {creds.token}"}

    metadata = {"name": name}
    files = {
        "metadata": (None, json.dumps(metadata), "application/json"),
        "file": (name, open(local_path, "rb"), mimetype),
    }
    r = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
        headers=headers,
        files=files,
    )
    r.raise_for_status()
    file_id = r.json()["id"]
    print("uploaded, file id:", file_id)

    # make public
    r2 = requests.post(
        f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
        headers={**headers, "Content-Type": "application/json"},
        data=json.dumps({"role": "reader", "type": "anyone"}),
    )
    r2.raise_for_status()

    direct_url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download"
    print(direct_url)
    return direct_url


if __name__ == "__main__":
    local_path = sys.argv[1]
    name = sys.argv[2]
    upload(local_path, name)
