import sys
import time
from pathlib import Path

import requests

from drive_upload import upload as drive_upload

BASE = Path(__file__).parent
ENV_PATH = BASE.parent / ".env"
SLIDES = BASE / "slides"


def load_env():
    env = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k] = v
    return env


def create_carousel_item(env, image_url):
    account_id = env["INSTAGRAM_ACCOUNT_ID"]
    token = env["INSTAGRAM_ACCESS_TOKEN"]
    r = requests.post(
        f"https://graph.instagram.com/v21.0/{account_id}/media",
        data={"image_url": image_url, "is_carousel_item": "true", "access_token": token},
    )
    print("item init:", r.status_code, r.text[:300])
    r.raise_for_status()
    return r.json()["id"]


def create_carousel_container(env, children, caption):
    account_id = env["INSTAGRAM_ACCOUNT_ID"]
    token = env["INSTAGRAM_ACCESS_TOKEN"]
    r = requests.post(
        f"https://graph.instagram.com/v21.0/{account_id}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(children),
            "caption": caption,
            "access_token": token,
        },
    )
    print("carousel init:", r.status_code, r.text[:300])
    r.raise_for_status()
    return r.json()["id"]


def publish(env, creation_id):
    account_id = env["INSTAGRAM_ACCOUNT_ID"]
    token = env["INSTAGRAM_ACCESS_TOKEN"]
    p = requests.post(
        f"https://graph.instagram.com/v21.0/{account_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
    )
    print("publish:", p.status_code, p.text[:300])
    p.raise_for_status()
    return p.json()


def main():
    caption_path = sys.argv[1]
    caption = Path(caption_path).read_text(encoding="utf-8")

    env = load_env()

    slide_paths = sorted(SLIDES.glob("slide_*.jpg"), key=lambda p: int(p.stem.split("_")[1]))
    print(f"found {len(slide_paths)} slides")

    image_urls = []
    for p in slide_paths:
        url = drive_upload(str(p), p.name, mimetype="image/jpeg")
        image_urls.append(url)

    children = []
    for url in image_urls:
        item_id = create_carousel_item(env, url)
        children.append(item_id)
        time.sleep(1)

    creation_id = create_carousel_container(env, children, caption)

    for _ in range(20):
        time.sleep(5)
        s = requests.get(
            f"https://graph.instagram.com/v21.0/{creation_id}",
            params={"fields": "status_code,status", "access_token": env["INSTAGRAM_ACCESS_TOKEN"]},
        ).json()
        print("status:", s)
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"container failed: {s}")

    result = publish(env, creation_id)
    print("PUBLISHED:", result)


if __name__ == "__main__":
    main()
