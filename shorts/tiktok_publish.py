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
    video_path = Path(sys.argv[1])
    title = sys.argv[2]

    env = load_env()
    token = env["TIKTOK_ACCESS_TOKEN"]

    video_size = video_path.stat().st_size
    chunk_size = video_size  # single chunk, TikTok allows up to 64MB in one chunk

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
            "chunk_size": chunk_size,
            "total_chunk_count": 1,
        },
    }

    r = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json=init_body,
    )
    print("init status:", r.status_code, r.text)
    r.raise_for_status()
    data = r.json()
    print("init:", data)
    if data.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"init failed: {data}")

    publish_id = data["data"]["publish_id"]
    upload_url = data["data"]["upload_url"]

    with open(video_path, "rb") as f:
        video_bytes = f.read()

    up = requests.put(
        upload_url,
        headers={
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
        },
        data=video_bytes,
    )
    print("upload status:", up.status_code, up.text[:500])
    up.raise_for_status()

    for _ in range(15):
        time.sleep(5)
        s = requests.post(
            "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={"publish_id": publish_id},
        ).json()
        status = s.get("data", {}).get("status")
        print(status, s)
        if status in ("PUBLISH_COMPLETE", "FAILED"):
            break


if __name__ == "__main__":
    main()
