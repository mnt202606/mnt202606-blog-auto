import os
import sys
import time
from pathlib import Path

import requests

BASE = Path(__file__).parent


def load_env():
    env = {}
    for line in (BASE.parent / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k] = v
    return env


def main():
    video_url = sys.argv[1]
    caption = Path(sys.argv[2]).read_text(encoding="utf-8")

    env = load_env()
    account_id = env["INSTAGRAM_ACCOUNT_ID"]
    token = env["INSTAGRAM_ACCESS_TOKEN"]

    r = requests.post(
        f"https://graph.instagram.com/v21.0/{account_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": token,
        },
    )
    r.raise_for_status()
    container_id = r.json()["id"]
    print("container:", container_id)

    for _ in range(20):
        time.sleep(8)
        s = requests.get(
            f"https://graph.instagram.com/v21.0/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
        ).json()
        print(s)
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"container failed: {s}")
    else:
        raise RuntimeError("timed out waiting for container to finish")

    p = requests.post(
        f"https://graph.instagram.com/v21.0/{account_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
    )
    p.raise_for_status()
    media_id = p.json()["id"]
    print("published, media id:", media_id)

    perm = requests.get(
        f"https://graph.instagram.com/v21.0/{media_id}",
        params={"fields": "permalink", "access_token": token},
    ).json()
    print("permalink:", perm.get("permalink"))


if __name__ == "__main__":
    main()
