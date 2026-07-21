import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

DATA_URL = "https://data.cincinnati-oh.gov/resource/uhjb-xac9.json"

DAYS_BACK = 30
MIN_VALUE = 25000

COMMERCIAL_KEYWORDS = [
    "commercial",
    "warehouse",
    "industrial",
    "manufacturing",
    "restaurant",
    "retail",
    "office",
    "school",
    "hospital",
    "medical",
    "apartment",
    "multifamily",
    "mixed use",
    "hotel",
    "tenant",
    "renovation",
    "alteration",
    "addition",
    "new building",
]


def safe_money(value):
    try:
        number = float(value)
        return f"${number:,.0f}", number
    except (TypeError, ValueError):
        return "Unknown", 0


def opportunity_score(description, value):
    text = (description or "").lower()

    score = 4
    reasons = []

    if value >= 10_000_000:
        score += 3
        reasons.append("large project value")
    elif value >= 2_000_000:
        score += 2
        reasons.append("significant project value")
    elif value >= 500_000:
        score += 1
        reasons.append("moderate project value")

    high_intensity = [
        "industrial",
        "manufacturing",
        "hospital",
        "school",
        "warehouse",
        "apartment",
        "multifamily",
        "hotel",
        "mixed use",
    ]

    if any(word in text for word in high_intensity):
        score += 2
        reasons.append("electrically intensive project type")

    score = max(1, min(score, 10))

    reason = ", ".join(reasons) if reasons else "general commercial construction opportunity"

    return score, reason


def get_recent_permits():
    cutoff = (datetime.utcnow() - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%dT00:00:00")

    params = {
        "$limit": "500",
        "$order": "issued_date DESC",
        "$where": f"issued_date >= '{cutoff}'",
    }

    url = DATA_URL + "?" + urllib.parse.urlencode(params)

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ConstructionRadar/1.0"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def is_relevant(record):
    description = " ".join([
        str(record.get("work_description", "")),
        str(record.get("permit_type", "")),
        str(record.get("use", "")),
    ]).lower()

    value_fields = [
        record.get("estimated_cost"),
        record.get("declared_value"),
        record.get("valuation"),
    ]

    value = 0

    for field in value_fields:
        try:
            value = max(value, float(field or 0))
        except (TypeError, ValueError):
            pass

    keyword_match = any(keyword in description for keyword in COMMERCIAL_KEYWORDS)

    return keyword_match and value >= MIN_VALUE


def normalize(record):
    description = (
        record.get("work_description")
        or record.get("description")
        or record.get("permit_type")
        or "Construction project"
    )

    raw_value = (
        record.get("estimated_cost")
        or record.get("declared_value")
        or record.get("valuation")
        or 0
    )

    formatted_value, numeric_value = safe_money(raw_value)

    address_parts = [
        record.get("street_number"),
        record.get("street_direction"),
        record.get("street_name"),
        record.get("street_type"),
    ]

    address = " ".join(
        str(part).strip()
        for part in address_parts
        if part
    ).strip()

    project_name = description[:90]

    score, reason = opportunity_score(description, numeric_value)

    return {
        "project": project_name,
        "address": address or "Unknown",
        "city": "Cincinnati",
        "county": "Hamilton",
        "state": "OH",
        "type": record.get("permit_type", "Unknown"),
        "status": record.get("status", "Permitted"),
        "value": formatted_value,
        "value_numeric": numeric_value,
        "permit_number": (
            record.get("permit_number")
            or record.get("application_number")
            or "Unknown"
        ),
        "description": description,
        "contractor": (
            record.get("contractor_name")
            or record.get("contractor")
            or "Unknown"
        ),
        "bid_date": "Unknown",
        "opportunity": f"{score}/10",
        "opportunity_reason": reason,
        "source": "City of Cincinnati Building Permits",
        "source_url": "https://data.cincinnati-oh.gov/Thriving-Neighborhoods/Cincinnati-Building-Permits/uhjb-xac9",
        "date_discovered": datetime.utcnow().strftime("%Y-%m-%d"),
    }


def main():
    print("Downloading Cincinnati permit data...")

    records = get_recent_permits()

    print(f"Downloaded {len(records)} recent permit records.")

    projects = []

    for record in records:
        if is_relevant(record):
            projects.append(normalize(record))

    projects.sort(
        key=lambda x: x.get("value_numeric", 0),
        reverse=True
    )

    with open("projects.json", "w", encoding="utf-8") as file:
        json.dump(projects, file, indent=2)

    print(f"Saved {len(projects)} relevant construction projects.")


if __name__ == "__main__":
    main()
