import argparse
import datetime
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import pickle

BASE = Path(__file__).parent
CLIENT_SECRET = BASE / "secrets" / "youtube_client_secret.json"
TOKEN_FILE = BASE / "secrets" / "youtube_token.pickle"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_credentials():
    creds = None
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
    return creds


def upload_video(video_path, title, description, tags, publish_at_kst=None):
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    status = {"selfDeclaredMadeForKids": False}
    if publish_at_kst:
        # publish_at_kst: datetime in KST (UTC+9), naive
        publish_at_utc = publish_at_kst - datetime.timedelta(hours=9)
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at_utc.strftime("%Y-%m-%dT%H:%M:%S.0Z")
    else:
        status["privacyStatus"] = "public"

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",
        },
        "status": status,
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status_progress, response = request.next_chunk()
        if status_progress:
            print(f"업로드 중... {int(status_progress.progress() * 100)}%")

    print(f"완료! video id: {response['id']}")
    print(f"URL: https://youtu.be/{response['id']}")
    return response


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--tags", default="")
    parser.add_argument("--publish-at", default=None, help="KST datetime, e.g. '2026-07-27 17:00'")
    args = parser.parse_args()

    publish_at = None
    if args.publish_at:
        publish_at = datetime.datetime.strptime(args.publish_at, "%Y-%m-%d %H:%M")

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    upload_video(args.video, args.title, args.description, tags, publish_at)
