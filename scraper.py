import json
import urllib.request

CONTACTS_URL = (
    "https://data.cincinnati-oh.gov/resource/vmk6-gy84.json?$limit=10"
)

def main():
    print("Testing Cincinnati permit contacts API...")
    print(f"URL: {CONTACTS_URL}")

    request = urllib.request.Request(
        CONTACTS_URL,
        headers={
            "User-Agent": "ConstructionRadar/1.0"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        records = json.loads(
            response.read().decode("utf-8")
        )

    print(f"Downloaded {len(records)} test contact records.")

    if not records:
        print("No contact records returned.")
        return

    print()
    print("AVAILABLE FIELD NAMES:")
    print("----------------------")

    all_fields = set()

    for record in records:
        all_fields.update(record.keys())

    for field in sorted(all_fields):
        print(field)

    print()
    print("SAMPLE RECORDS:")
    print("----------------------")

    for i, record in enumerate(records[:5], start=1):
        print()
        print(f"RECORD {i}")
        print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
