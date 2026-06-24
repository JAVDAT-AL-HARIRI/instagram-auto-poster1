import os
import csv
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
IG_USER_ID = os.environ["IG_USER_ID"]
CSV_FILE = "posts.csv"

BASE_URL = "https://graph.instagram.com/v23.0"
SAUDI_TZ = ZoneInfo("Asia/Riyadh")


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


def wait_for_container(creation_id, max_wait_seconds=300, check_every_seconds=10):
    """
    ينتظر حتى يصبح Media Container جاهز للنشر.
    لا تنشر قبل أن تكون الحالة FINISHED.
    """

    waited = 0

    while waited <= max_wait_seconds:
        response = requests.get(
            f"{BASE_URL}/{creation_id}",
            params={
                "fields": "status_code",
                "access_token": ACCESS_TOKEN,
            },
            timeout=60,
        )

        data = response.json()
        status = data.get("status_code")

        print(f"Container status: {status} | waited: {waited}s")

        if status == "FINISHED":
            return True

        if status == "ERROR":
            raise Exception(f"Container processing error: {data}")

        if status == "EXPIRED":
            raise Exception(f"Container expired: {data}")

        time.sleep(check_every_seconds)
        waited += check_every_seconds

    raise Exception(f"Container not ready after {max_wait_seconds}s")


def publish_post(image_url, caption):
    create_response = requests.post(
        f"{BASE_URL}/{IG_USER_ID}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": ACCESS_TOKEN,
        },
        timeout=60,
    )

    create_data = create_response.json()
    print("Create media response:", create_data)

    if "id" not in create_data:
        raise Exception(f"Create media error: {create_data}")

    creation_id = create_data["id"]

    wait_for_container(
        creation_id,
        max_wait_seconds=300,
        check_every_seconds=10,
    )

    publish_response = requests.post(
        f"{BASE_URL}/{IG_USER_ID}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": ACCESS_TOKEN,
        },
        timeout=60,
    )

    publish_data = publish_response.json()
    print("Publish response:", publish_data)

    if "id" not in publish_data:
        raise Exception(f"Publish error: {publish_data}")

    print("Published post:", publish_data["id"])


def main():
    now = datetime.now(SAUDI_TZ)
    print("Saudi time now:", now.strftime("%Y-%m-%d %H:%M"))

    rows = []
    posted_one = False

    with open(CSV_FILE, newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames

        for row in reader:
            scheduled_dt = parse_time(row["scheduled_time"])
            posted = row["posted"].strip().lower()

            if not posted_one and posted == "no" and scheduled_dt <= now:
                print("Publishing:", row["image_name"])

                publish_post(
                    row["image_url"],
                    row["caption"],
                )

                row["posted"] = "yes"
                posted_one = True

            rows.append(row)

    with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
