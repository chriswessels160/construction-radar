import json
import urllib.request

DATA_URL = "https://data.cincinnati-oh.gov/resource/uhjb-xac9.json?$limit=5"


def main():
    print("Testing Cincinnati permit API...")
    print(f"URL: {DATA_URL}")

    request = urllib.request.Request(
        DATA_URL,
        headers={
            "User-Agent": "ConstructionRadar/1.0"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        records = json.loads(response.read().decode("utf-8"))

    print(f"Downloaded {len(records)} test records.")

    if not records:
        print("No records returned.")
        return

    print("\nAVAILABLE FIELD NAMES:")
    print("----------------------")

    for field in sorted(records[0].keys()):
        print(field)

    print("\nFIRST SAMPLE RECORD:")
    print("--------------------")
    print(json.dumps(records[0], indent=2))


if __name__ == "__main__":
    main()
