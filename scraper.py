import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

DATA_URL = "https://data.cincinnati-oh.gov/resource/uhjb-xac9.json"

# Look back this many days for recently issued permits
DAYS_BACK = 60

# Minimum project value we generally care about
MIN_VALUE = 25000

# Words that usually indicate potentially useful commercial construction
COMMERCIAL_KEYWORDS = [
    "commercial",
    "warehouse",
    "industrial",
    "manufacturing",
    "factory",
    "restaurant",
    "retail",
    "store",
    "office",
    "school",
    "university",
    "hospital",
    "medical",
    "clinic",
    "apartment",
    "apartments",
    "multifamily",
    "mixed use",
    "mixed-use",
    "hotel",
    "tenant",
    "renovation",
    "alteration",
    "addition",
    "new building",
    "new construction",
    "distribution",
    "distribution center",
    "community center",
    "church",
    "government",
    "municipal",
]

# Small/residential work that generally creates too much noise
EXCLUDE_KEYWORDS = [
    "single family",
    "single-family",
    "two family",
    "2 family",
    "deck",
    "fence",
    "swimming pool",
    "residential garage",
    "shed",
]


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def parse_money(value):
    try:
        number = float(value or 0)
        return number
    except (TypeError, ValueError):
        return 0


def format_money(number):
    if not number:
        return "Unknown"

    return f"${number:,.0f}"


def electrical_score(description, proposed_use, workclass, value):
    text = " ".join([
        clean_text(description),
        clean_text(proposed_use),
        clean_text(workclass),
    ]).lower()

    score = 3
    reasons = []

    # Project value
    if value >= 20_000_000:
        score += 4
        reasons.append("very large construction value")

    elif value >= 5_000_000:
        score += 3
        reasons.append("large construction value")

    elif value >= 1_000_000:
        score += 2
        reasons.append("significant construction value")

    elif value >= 250_000:
        score += 1
        reasons.append("meaningful commercial project value")

    # Electrically intensive types
    very_high_types = [
        "hospital",
        "manufacturing",
        "factory",
        "data center",
        "industrial",
    ]

    high_types = [
        "school",
        "university",
        "apartment",
        "multifamily",
        "hotel",
        "warehouse",
        "mixed use",
        "mixed-use",
        "distribution",
    ]

    if any(word in text for word in very_high_types):
        score += 3
        reasons.append("electrically intensive project type")

    elif any(word in text for word in high_types):
        score += 2
        reasons.append("strong potential electrical material demand")

    # New construction / additions usually offer more material opportunity
    if "new" in text or "addition" in text:
        score += 1
        reasons.append("new construction or expansion")

    score = min(max(score, 1), 10)

    if not reasons:
        reasons.append("potential commercial electrical material opportunity")

    return score, "; ".join(reasons)


def get_recent_permits():
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
    ).strftime("%Y-%m-%dT00:00:00")

    query = {
        "$limit": "5000",
        "$order": "issueddate DESC",
        "$where": f"issueddate >= '{cutoff}'",
    }

    url = DATA_URL + "?" + urllib.parse.urlencode(query)

    print("Requesting Cincinnati permit data...")
    print(f"Looking back {DAYS_BACK} days.")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ConstructionRadar/1.0"
        }
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        records = json.loads(
            response.read().decode("utf-8")
        )

    return records


def is_relevant(record):
    description = clean_text(record.get("description"))
    proposed_use = clean_text(record.get("proposeduse"))
    permit_type = clean_text(record.get("permittype"))
    workclass = clean_text(record.get("workclass"))

    text = " ".join([
        description,
        proposed_use,
        permit_type,
        workclass,
    ]).lower()

    value = parse_money(record.get("estprojectcostdec"))

    # Remove obvious residential/noise projects
    if any(word in text for word in EXCLUDE_KEYWORDS):
        return False

    keyword_match = any(
        word in text
        for word in COMMERCIAL_KEYWORDS
    )

    # Keep substantial projects even if description is vague
    substantial_project = value >= 250_000

    # Keep smaller projects only when clearly commercial/relevant
    smaller_commercial = (
        value >= MIN_VALUE
        and keyword_match
    )

    return substantial_project or smaller_commercial


def normalize(record):
    description = (
        clean_text(record.get("description"))
        or "Construction Permit"
    )

    address = (
        clean_text(record.get("originaladdress1"))
        or "Unknown"
    )

    city = (
        clean_text(record.get("originalcity"))
        or "Cincinnati"
    )

    state = (
        clean_text(record.get("originalstate"))
        or "OH"
    )

    value = parse_money(
        record.get("estprojectcostdec")
    )

    proposed_use = (
        clean_text(record.get("proposeduse"))
        or "Unknown"
    )

    workclass = (
        clean_text(record.get("workclassmapped"))
        or clean_text(record.get("workclass"))
        or "Unknown"
    )

    permit_type = (
        clean_text(record.get("permittypemapped"))
        or clean_text(record.get("permittype"))
        or "Unknown"
    )

    company = (
        clean_text(record.get("companyname"))
        or "Unknown"
    )

    status = (
        clean_text(record.get("statuscurrentmapped"))
        or clean_text(record.get("statuscurrent"))
        or "Unknown"
    )

    permit_number = (
        clean_text(record.get("permitnum"))
        or "Unknown"
    )

    issued_date = (
        clean_text(record.get("issueddate"))
        or "Unknown"
    )

    score, reason = electrical_score(
        description,
        proposed_use,
        workclass,
        value
    )

    # Create a readable project name
    if proposed_use != "Unknown":
        project_name = f"{proposed_use} - {address}"
    else:
        project_name = f"{description[:70]} - {address}"

    source_link = clean_text(record.get("link"))

    if not source_link:
        source_link = (
            "https://data.cincinnati-oh.gov/"
            "Thriving-Neighborhoods/"
            "Cincinnati-Building-Permits/"
            "uhjb-xac9"
        )

    return {
        "project": project_name,
        "address": address,
        "city": city,
        "county": "Hamilton",
        "state": state,

        "type": permit_type,
        "work_class": workclass,
        "proposed_use": proposed_use,

        "status": status,

        "value": format_money(value),
        "value_numeric": value,

        "permit_number": permit_number,
        "issued_date": issued_date,

        "description": description,

        # IMPORTANT:
        # companyname comes from the permit dataset.
        # We are NOT automatically claiming it is the GC.
        "company": company,

        "contractor": "Unknown",
        "general_contractor": "Unknown",
        "electrical_contractor": "Unknown",

        "bid_date": "Unknown",

        "opportunity": f"{score}/10",
        "opportunity_score": score,
        "opportunity_reason": reason,

        "source": "City of Cincinnati Building Permits",
        "source_url": source_link,

        "date_discovered": datetime.now(
            timezone.utc
        ).strftime("%Y-%m-%d")
    }


def remove_duplicates(projects):
    seen = set()
    unique = []

    for project in projects:

        key = (
            project.get("permit_number"),
            project.get("address"),
        )

        if key not in seen:
            seen.add(key)
            unique.append(project)

    return unique


def main():

    print("=" * 50)
    print("GREATER CINCINNATI CONSTRUCTION RADAR")
    print("=" * 50)

    try:
        records = get_recent_permits()

    except Exception as error:
        print("ERROR downloading Cincinnati permits:")
        print(error)
        raise

    print(
        f"Downloaded {len(records)} recent Cincinnati permits."
    )

    projects = []

    for record in records:

        if is_relevant(record):

            project = normalize(record)

            projects.append(project)

    projects = remove_duplicates(projects)

    # Highest opportunity first, then largest value
    projects.sort(
        key=lambda project: (
            project.get("opportunity_score", 0),
            project.get("value_numeric", 0),
        ),
        reverse=True
    )

    with open(
        "projects.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            projects,
            file,
            indent=2,
            ensure_ascii=False
        )

    high_opportunities = sum(
        1
        for project in projects
        if project.get(
            "opportunity_score",
            0
        ) >= 8
    )

    print()
    print("=" * 50)
    print("UPDATE COMPLETE")
    print("=" * 50)

    print(
        f"Permits downloaded: {len(records)}"
    )

    print(
        f"Relevant projects saved: {len(projects)}"
    )

    print(
        f"High electrical opportunities: "
        f"{high_opportunities}"
    )

    print(
        "projects.json successfully updated."
    )


if __name__ == "__main__":
    main()
