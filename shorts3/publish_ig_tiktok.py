import sys
import time
from pathlib import Path

import requests

BASE = Path(__file__).parent
ENV_PATH = BASE.parent / ".env"


def load_env():
    env = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k] = v
    return env


def save_env(env):
    lines = []
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k = line.split("=", 1)[0]
            if k in env:
                lines.append(f"{k}={env[k]}")
                continue
        lines.append(line)
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def publish_instagram(env, video_url, caption):
    account_id = env["INSTAGRAM_ACCOUNT_ID"]
    token = env["INSTAGRAM_ACCESS_TOKEN"]

    r = requests.post(
        f"https://graph.instagram.com/v21.0/{account_id}/media",
        data={"media_type": "REELS", "video_url": video_url, "caption": caption, "access_token": token},
    )
    print("IG init:", r.status_code, r.text[:300])
    r.raise_for_status()
    container_id = r.json()["id"]

    for _ in range(20):
        time.sleep(8)
        s = requests.get(
            f"https://graph.instagram.com/v21.0/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
        ).json()
        print("IG status:", s)
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"IG container failed: {s}")
    else:
        raise RuntimeError("IG timed out waiting for container")

    p = requests.post(
        f"https://graph.instagram.com/v21.0/{account_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
    )
    p.raise_for_status()
    print("IG published:", p.json())


def refresh_tiktok_token(env):
    r = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": env["TIKTOK_CLIENT_KEY"],
            "client_secret": env["TIKTOK_CLIENT_SECRET"],
            "grant_type": "refresh_token",
            "refresh_token": env["TIKTOK_REFRESH_TOKEN"],
        },
    )
    r.raise_for_status()
    data = r.json()
    print("TikTok token refreshed")
    env["TIKTOK_ACCESS_TOKEN"] = data["access_token"]
    env["TIKTOK_REFRESH_TOKEN"] = data["refresh_token"]
    save_env(env)
    return env


def publish_tiktok(env, video_path, title):
    token = env["TIKTOK_ACCESS_TOKEN"]
    video_path = Path(video_path)
    video_size = video_path.stat().st_size

    init_body = {
        "post_info": {
            "title": title,
            "privacy_level": "SELF_ONLY",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1,
        },
    }
    r = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
        json=init_body,
    )
    print("TikTok init:", r.status_code, r.text[:300])
    r.raise_for_status()
    data = r.json()
    publish_id = data["data"]["publish_id"]
    upload_url = data["data"]["upload_url"]

    with open(video_path, "rb") as f:
        video_bytes = f.read()
    up = requests.put(
        upload_url,
        headers={"Content-Type": "video/mp4", "Content-Range": f"bytes 0-{video_size - 1}/{video_size}"},
        data=video_bytes,
    )
    print("TikTok upload:", up.status_code)
    up.raise_for_status()

    for _ in range(15):
        time.sleep(5)
        s = requests.post(
            "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
            json={"publish_id": publish_id},
        ).json()
        print("TikTok status:", s)
        status = s.get("data", {}).get("status")
        if status in ("PUBLISH_COMPLETE", "FAILED"):
            break


if __name__ == "__main__":
    env = load_env()

    ig_video_url = "https://drive.usercontent.google.com/download?id=1hFdclwNruGSPBSszXwggN0PoloAwC3uP&export=download"
    ig_caption = Path(sys.argv[1]).read_text(encoding="utf-8")
    tiktok_video_path = sys.argv[2]
    tiktok_title = sys.argv[3]

    publish_instagram(env, ig_video_url, ig_caption)

    env = refresh_tiktok_token(env)
    publish_tiktok(env, tiktok_video_path, tiktok_title)

    print("ALL DONE")
