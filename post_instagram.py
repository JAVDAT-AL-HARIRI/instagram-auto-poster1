import os
import csv
import time
import sys
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv


load_dotenv()

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

CSV_FILE = os.getenv("POSTS_FILE", "posts.csv")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Riyadh")
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v23.0")

BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
SAUDI_TZ = ZoneInfo(TIMEZONE)


def fail(message):
    print(f"ERROR: {message}")
    sys.exit(1)


def check_env():
    if not ACCESS_TOKEN:
        fail("ACCESS_TOKEN is missing. Put it in .env")
    if not IG_USER_ID:
        fail("IG_USER_ID is missing. Put it in .env")
    if not os.path.exists(CSV_FILE):
        fail(f"{CSV_FILE} not found")


def parse_time(value):
    value = value.strip()

    formats = [
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y %I:%M %p",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=SAUDI_TZ)
        except ValueError:
            pass

    raise ValueError(f"Wrong time format: {value}")


def request_json(method, url, **kwargs):
    try:
        response = requests.request(method, url, timeout=60, **kwargs)
    except requests.RequestException as e:
        raise Exception(f"Network error: {e}")

    try:
        data = response.json()
    except ValueError:
        raise Exception(f"Non-JSON response: HTTP {response.status_code} | {response.text}")

    return data


def wait_for_container(creation_id, max_wait_seconds=300, check_every_seconds=10):
    waited = 0

    while waited <= max_wait_seconds:
        data = request_json(
            "GET",
            f"{BASE_URL}/{creation_id}",
            params={
                "fields": "status_code",
                "access_token": ACCESS_TOKEN,
            },
        )

        status = data.get("status_code")

        print(f"Container status: {status} | waited: {waited}s")

        if status == "FINISHED":
            return True

        if status == "PUBLISHED":
            return True

        if status == "ERROR":
            raise Exception(f"Container processing error: {data}")

        if status == "EXPIRED":
            raise Exception(f"Container expired: {data}")

        if "error" in data:
            raise Exception(f"Container status error: {data}")

        time.sleep(check_every_seconds)
        waited += check_every_seconds

    raise Exception(f"Container not ready after {max_wait_seconds}s")


def publish_post(image_url, caption):
    create_data = request_json(
        "POST",
        f"{BASE_URL}/{IG_USER_ID}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": ACCESS_TOKEN,
        },
    )

    print("Create media response:", create_data)

    if "id" not in create_data:
        raise Exception(f"Create media error: {create_data}")

    creation_id = create_data["id"]

    wait_for_container(
        creation_id,
        max_wait_seconds=300,
        check_every_seconds=10,
    )

    publish_data = request_json(
        "POST",
        f"{BASE_URL}/{IG_USER_ID}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": ACCESS_TOKEN,
        },
    )

    print("Publish response:", publish_data)

    if "id" not in publish_data:
        raise Exception(f"Publish error: {publish_data}")

    print("Published post:", publish_data["id"])
    return publish_data["id"]


def main():
    check_env()

    now = datetime.now(SAUDI_TZ)
    print("Saudi time now:", now.strftime("%Y-%m-%d %H:%M"))
    print("CSV file:", CSV_FILE)
    print("API:", BASE_URL)

    rows = []
    posted_one = False

    with open(CSV_FILE, newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames

        if not fieldnames:
            fail("CSV file has no header")

        required_columns = ["image_name", "image_url", "caption", "scheduled_time", "posted"]

        for column in required_columns:
            if column not in fieldnames:
                fail(f"Missing CSV column: {column}")

        for row in reader:
            try:
                scheduled_dt = parse_time(row["scheduled_time"])
            except ValueError as e:
                print(f"Skipping row because time is wrong: {e}")
                rows.append(row)
                continue

            posted = row["posted"].strip().lower()

            if not posted_one and posted == "no" and scheduled_dt <= now:
                image_name = row["image_name"].strip()
                image_url = row["image_url"].strip()
                caption = row["caption"].strip()

                if not image_url:
                    raise Exception(f"image_url is empty for: {image_name}")

                if not caption:
                    raise Exception(f"caption is empty for: {image_name}")

                print("Publishing:", image_name)

                published_id = publish_post(image_url, caption)

                row["posted"] = "yes"

                if "published_id" in fieldnames:
                    row["published_id"] = published_id

                posted_one = True

            rows.append(row)

    with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    if not posted_one:
        print("No due posts now.")


if __name__ == "__main__":
    main()
