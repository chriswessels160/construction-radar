import json
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone


# ============================================================
# CONFIGURATION
# ============================================================

PERMITS_URL = (
    "https://data.cincinnati-oh.gov/resource/uhjb-xac9.json"
)

CONTACTS_URL = (
    "https://data.cincinnati-oh.gov/resource/vmk6-gy84.json"
)

# How far back we look for construction permits
DAYS_BACK = 60

# Look farther back for contacts so we don't miss a contractor
# whose contact record was created before the permit was issued.
CONTACT_DAYS_BACK = 180

# Ignore most tiny projects unless clearly useful
MIN_VALUE = 25_000


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


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def parse_money(value):
    try:
        return float(value or 0)

    except (TypeError, ValueError):
        return 0


def format_money(number):
    if not number:
        return "Unknown"

    return f"${number:,.0f}"


# ============================================================
# MARKET CLASSIFICATION
# ============================================================

def classify_market(
    description,
    proposed_use,
    permit_type,
    workclass
):

    text = " ".join([
        clean_text(description),
        clean_text(proposed_use),
        clean_text(permit_type),
        clean_text(workclass),
    ]).lower()


    # Industrial
    if any(word in text for word in [
        "manufacturing",
        "factory",
        "industrial",
        "plant",
        "production facility",
        "processing facility",
        "assembly facility",
        "f-1",
        "f-2",
    ]):
        return "Industrial"


    # Warehouse / Logistics
    if any(word in text for word in [
        "warehouse",
        "distribution center",
        "distribution facility",
        "logistics",
        "fulfillment",
        "storage facility",
        "s-1",
        "s-2",
    ]):
        return "Warehouse / Logistics"


    # Healthcare
    if any(word in text for word in [
        "hospital",
        "medical",
        "clinic",
        "healthcare",
        "health care",
        "surgery center",
        "urgent care",
        "nursing",
    ]):
        return "Healthcare"


    # Education
    if any(word in text for word in [
        "school",
        "university",
        "college",
        "education",
        "classroom",
        "campus",
        "daycare",
        "day care",
    ]):
        return "Education"


    # Multifamily / Residential
    if any(word in text for word in [
        "apartment",
        "apartments",
        "multifamily",
        "multi-family",
        "condominium",
        "condominiums",
        "student housing",
        "senior living",
        "r-1",
        "r-2",
        "r-3",
        "1-2-3 fm",
    ]):
        return "Multifamily / Residential"


    # Hospitality
    if any(word in text for word in [
        "hotel",
        "motel",
        "hospitality",
        "lodging",
        "resort",
    ]):
        return "Hospitality"


    # Government / Public
    if any(word in text for word in [
        "government",
        "municipal",
        "city hall",
        "fire station",
        "police station",
        "courthouse",
        "public works",
        "library",
        "community center",
    ]):
        return "Government / Public"


    # Infrastructure / Utility
    if any(word in text for word in [
        "utility",
        "water treatment",
        "wastewater",
        "sewer",
        "substation",
        "infrastructure",
        "transit",
        "pump station",
    ]):
        return "Infrastructure / Utility"


    # Mixed Use
    if any(word in text for word in [
        "mixed use",
        "mixed-use",
    ]):
        return "Mixed-Use"


    # Commercial
    if any(word in text for word in [
        "commercial",
        "office",
        "retail",
        "restaurant",
        "store",
        "tenant",
        "shopping",
        "business",
        "bank",
        "grocery",
        "supermarket",
        "bar",
        "a-1",
        "a-2",
        "a-3",
        "a-4",
        "a-5",
    ]):
        return "Commercial"


    return "Other"


# ============================================================
# ELECTRICAL OPPORTUNITY SCORE
# ============================================================

def electrical_score(
    description,
    proposed_use,
    workclass,
    value
):

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

        reasons.append(
            "very large construction value"
        )


    elif value >= 5_000_000:

        score += 3

        reasons.append(
            "large construction value"
        )


    elif value >= 1_000_000:

        score += 2

        reasons.append(
            "significant construction value"
        )


    elif value >= 250_000:

        score += 1

        reasons.append(
            "meaningful commercial project value"
        )


    # Very electrically intensive markets
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


    if any(
        word in text
        for word in very_high_types
    ):

        score += 3

        reasons.append(
            "electrically intensive project type"
        )


    elif any(
        word in text
        for word in high_types
    ):

        score += 2

        reasons.append(
            "strong potential electrical material demand"
        )


    # New construction / additions
    if (
        "new" in text
        or "addition" in text
    ):

        score += 1

        reasons.append(
            "new construction or expansion"
        )


    score = min(
        max(score, 1),
        10
    )


    if not reasons:

        reasons.append(
            "potential commercial electrical material opportunity"
        )


    return (
        score,
        "; ".join(reasons)
    )


# ============================================================
# DOWNLOAD PERMITS
# ============================================================

def get_recent_permits():

    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(days=DAYS_BACK)
    ).strftime(
        "%Y-%m-%dT00:00:00"
    )


    query = {

        "$limit": "5000",

        "$order":
            "issueddate DESC",

        "$where":
            f"issueddate >= '{cutoff}'",
    }


    url = (
        PERMITS_URL
        + "?"
        + urllib.parse.urlencode(query)
    )


    print(
        "Downloading Cincinnati permits..."
    )


    request = urllib.request.Request(

        url,

        headers={
            "User-Agent":
                "ConstructionRadar/1.0"
        }
    )


    with urllib.request.urlopen(
        request,
        timeout=60
    ) as response:

        return json.loads(
            response
            .read()
            .decode("utf-8")
        )


# ============================================================
# DOWNLOAD CONTRACTOR CONTACTS
# ============================================================

def get_contacts_for_permits(permit_records):

    permit_numbers = []

    for record in permit_records:
        permit_number = clean_text(
            record.get("permitnum")
        )

        if permit_number:
            permit_numbers.append(permit_number)

    # Remove duplicate permit numbers
    permit_numbers = list(set(permit_numbers))

    print(
        f"Looking up contacts for "
        f"{len(permit_numbers)} permit numbers..."
    )

    all_contacts = []

    # Query Cincinnati in small batches
    # so the API URL does not become too long.
    batch_size = 50

    for i in range(
        0,
        len(permit_numbers),
        batch_size
    ):

        batch = permit_numbers[
            i:i + batch_size
        ]

        conditions = []

        for permit_number in batch:

            safe_number = (
                permit_number
                .replace("'", "''")
            )

            conditions.append(
                f"number_key='{safe_number}'"
            )

        where_clause = (
            "("
            + " OR ".join(conditions)
            + ")"
        )

        query = {
            "$limit": "5000",
            "$where": where_clause
        }

        url = (
            CONTACTS_URL
            + "?"
            + urllib.parse.urlencode(query)
        )

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent":
                    "ConstructionRadar/1.0"
            }
        )

        try:

            with urllib.request.urlopen(
                request,
                timeout=60
            ) as response:

                records = json.loads(
                    response
                    .read()
                    .decode("utf-8")
                )

            all_contacts.extend(records)

        except Exception as error:

            print(
                f"WARNING: Contact batch failed: "
                f"{error}"
            )

    print(
        f"Downloaded {len(all_contacts)} "
        f"permit contact records."
    )

    return all_contacts


# ============================================================
# BUILD CONTRACTOR LOOKUP
# ============================================================

def build_contractor_lookup(
    contact_records
):

    contractor_map = defaultdict(list)


    for record in contact_records:

        relationship = clean_text(
            record.get("relationship")
        ).upper()


        if relationship != "CONTRACTOR":
            continue


        permit_number = clean_text(
            record.get("number_key")
        )


        contractor_name = clean_text(
            record.get("name")
        )


        if not permit_number:
            continue


        if not contractor_name:
            continue


        # Ignore obviously useless placeholder names
        if contractor_name.upper() in [
            "OWNER",
            "UNKNOWN",
            "N/A",
            "NONE",
        ]:
            continue


        # Prevent duplicate contractor names
        existing_upper = [
            name.upper()
            for name
            in contractor_map[permit_number]
        ]


        if (
            contractor_name.upper()
            not in existing_upper
        ):

            contractor_map[
                permit_number
            ].append(
                contractor_name
            )


    return contractor_map


# ============================================================
# RELEVANCE FILTER
# ============================================================

def is_relevant(record):

    description = clean_text(
        record.get("description")
    )

    proposed_use = clean_text(
        record.get("proposeduse")
    )

    permit_type = clean_text(
        record.get("permittype")
    )

    workclass = clean_text(
        record.get("workclass")
    )


    text = " ".join([

        description,

        proposed_use,

        permit_type,

        workclass,

    ]).lower()


    value = parse_money(
        record.get(
            "estprojectcostdec"
        )
    )


    # Filter obvious small residential noise
    if any(
        word in text
        for word in EXCLUDE_KEYWORDS
    ):

        return False


    keyword_match = any(

        word in text

        for word
        in COMMERCIAL_KEYWORDS

    )


    substantial_project = (
        value >= 250_000
    )


    smaller_commercial = (

        value >= MIN_VALUE

        and keyword_match

    )


    return (
        substantial_project
        or smaller_commercial
    )


# ============================================================
# NORMALIZE EACH PROJECT
# ============================================================

def normalize(
    record,
    contractor_map
):

    description = (

        clean_text(
            record.get("description")
        )

        or "Construction Permit"

    )


    address = (

        clean_text(
            record.get(
                "originaladdress1"
            )
        )

        or "Unknown"

    )


    city = (

        clean_text(
            record.get(
                "originalcity"
            )
        )

        or "Cincinnati"

    )


    state = (

        clean_text(
            record.get(
                "originalstate"
            )
        )

        or "OH"

    )


    value = parse_money(

        record.get(
            "estprojectcostdec"
        )

    )


    proposed_use = (

        clean_text(
            record.get(
                "proposeduse"
            )
        )

        or "Unknown"

    )


    workclass = (

        clean_text(
            record.get(
                "workclassmapped"
            )
        )

        or clean_text(
            record.get(
                "workclass"
            )
        )

        or "Unknown"

    )


    permit_type = (

        clean_text(
            record.get(
                "permittypemapped"
            )
        )

        or clean_text(
            record.get(
                "permittype"
            )
        )

        or "Unknown"

    )


    status = (

        clean_text(
            record.get(
                "statuscurrentmapped"
            )
        )

        or clean_text(
            record.get(
                "statuscurrent"
            )
        )

        or "Unknown"

    )


    permit_number = (

        clean_text(
            record.get(
                "permitnum"
            )
        )

        or "Unknown"

    )


    issued_date = (

        clean_text(
            record.get(
                "issueddate"
            )
        )

        or "Unknown"

    )


    market = classify_market(

        description,

        proposed_use,

        permit_type,

        workclass

    )


    score, reason = electrical_score(

        description,

        proposed_use,

        workclass,

        value

    )


    # ========================================================
    # CONTRACTOR MATCHING
    # ========================================================

    contractors = contractor_map.get(
        permit_number,
        []
    )


    if contractors:

        contractor_display = ", ".join(
            contractors
        )

    else:

        contractor_display = "Unknown"


    # Keep Cincinnati's original company field separately
    source_company = (

        clean_text(
            record.get(
                "companyname"
            )
        )

        or "Unknown"

    )
    clean_company = source_company.strip('"').strip()

if clean_company.upper() in [
    "OWNER",
    "UNKNOWN",
    "N/A",
    "NONE",
    ""
]:
    contractor_display = "Unknown"
else:
    contractor_display = clean_company


    # ========================================================
    # PROJECT NAME
    # ========================================================

    if proposed_use != "Unknown":

        project_name = (
            f"{proposed_use} - {address}"
        )

    else:

        project_name = (
            f"{description[:70]} - "
            f"{address}"
        )


    source_link = clean_text(
        record.get("link")
    )


    if not source_link:

        source_link = (
            "https://data.cincinnati-oh.gov/"
            "Thriving-Neighborhoods/"
            "Cincinnati-Building-Permits/"
            "uhjb-xac9"
        )


    return {

        "project":
            project_name,

        "address":
            address,

        "city":
            city,

        "county":
            "Hamilton",

        "state":
            state,

        "type":
            permit_type,

        "market":
            market,

        "work_class":
            workclass,

        "proposed_use":
            proposed_use,

        "status":
            status,

        "value":
            format_money(value),

        "value_numeric":
            value,

        "permit_number":
            permit_number,

        "issued_date":
            issued_date,

        "description":
            description,


        # Original company field from permit data
        "company":
            source_company,


        # Verified contractor contacts from
        # Cincinnati Permit Contacts dataset
        "contractor":
            contractor_display,

        "contractors":
    [contractor_display] if contractor_display != "Unknown" else [],


        # Reserved for future, more specific sources
        "general_contractor":
            "Unknown",

        "electrical_contractor":
            "Unknown",

        "bid_date":
            "Unknown",


        "opportunity":
            f"{score}/10",

        "opportunity_score":
            score,

        "opportunity_reason":
            reason,


        "source":
            "City of Cincinnati Building Permits",

        "source_url":
            source_link,

        "contractor_source":
            (
                "Cincinnati Building Permits Contacts"
                if contractors
                else "Unknown"
            ),

        "date_discovered":
            datetime.now(
                timezone.utc
            ).strftime(
                "%Y-%m-%d"
            )

    }


# ============================================================
# REMOVE DUPLICATES
# ============================================================

def remove_duplicates(projects):

    seen = set()

    unique = []


    for project in projects:

        key = (

            project.get(
                "permit_number"
            ),

            project.get(
                "address"
            ),

        )


        if key not in seen:

            seen.add(key)

            unique.append(
                project
            )


    return unique


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)

    print(
        "GREATER CINCINNATI CONSTRUCTION RADAR"
    )

    print("=" * 60)


    # --------------------------------------------------------
    # PERMITS
    # --------------------------------------------------------

    try:

        permit_records = (
            get_recent_permits()
        )

    except Exception as error:

        print(
            "ERROR downloading permits:"
        )

        print(error)

        raise


    print(

        f"Downloaded "
        f"{len(permit_records)} "
        f"recent permits."

    )


    # --------------------------------------------------------
    # CONTRACTORS
    # --------------------------------------------------------

    try:

        contact_records = (
    get_contacts_for_permits(
        permit_records
    )
)

    except Exception as error:

        # Contractor failure should NOT destroy
        # the entire permit update.

        print(
            "WARNING: Contractor contacts "
            "could not be downloaded."
        )

        print(error)

        contact_records = []


    print(

        f"Downloaded "
        f"{len(contact_records)} "
        f"contractor contact records."

    )


    contractor_map = (
        build_contractor_lookup(
            contact_records
        )
    )


    print(

        f"Contractor lookup contains "
        f"{len(contractor_map)} "
        f"permit numbers."

    )


    # --------------------------------------------------------
    # BUILD PROJECT LIST
    # --------------------------------------------------------

    projects = []


    for record in permit_records:

        if is_relevant(record):

            project = normalize(

                record,

                contractor_map

            )

            projects.append(
                project
            )


    projects = remove_duplicates(
        projects
    )


    # Highest opportunity first,
    # then project value
    projects.sort(

        key=lambda project: (

            project.get(
                "opportunity_score",
                0
            ),

            project.get(
                "value_numeric",
                0
            ),

        ),

        reverse=True

    )


    # --------------------------------------------------------
    # SAVE JSON
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    high_opportunities = sum(

        1

        for project
        in projects

        if project.get(
            "opportunity_score",
            0
        ) >= 8

    )


    projects_with_contractors = sum(

        1

        for project
        in projects

        if project.get(
            "contractor"
        ) not in [
            "",
            "Unknown",
            None
        ]

    )


    print()

    print("=" * 60)

    print(
        "UPDATE COMPLETE"
    )

    print("=" * 60)


    print(

        f"Permits downloaded: "
        f"{len(permit_records)}"

    )


    print(

        f"Contract contacts downloaded: "
        f"{len(contact_records)}"

    )


    print(

        f"Relevant projects saved: "
        f"{len(projects)}"

    )


    print(

        f"Projects with contractor matches: "
        f"{projects_with_contractors}"

    )


    print(

        f"High electrical opportunities: "
        f"{high_opportunities}"

    )


    print(

        "projects.json successfully updated."

    )

# ============================================================
# TEMPORARY CONTACT / PERMIT DIAGNOSTIC
# ============================================================

def diagnostic_check():

    print("\n========== DIAGNOSTIC: RECENT PERMITS ==========\n")

    permit_query = urllib.parse.urlencode({
        "$limit": "5",
        "$order": "issueddate DESC"
    })

    permit_url = PERMITS_URL + "?" + permit_query

    request = urllib.request.Request(
        permit_url,
        headers={"User-Agent": "ConstructionRadar/1.0"}
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        permits = json.loads(response.read().decode("utf-8"))

    for i, record in enumerate(permits, 1):
        print(f"\n--- PERMIT {i} ---")
        print(json.dumps(record, indent=2))


    print("\n========== DIAGNOSTIC: RECENT CONTACTS ==========\n")

    contact_query = urllib.parse.urlencode({
        "$limit": "10",
        "$order": "applied_date DESC"
    })

    contact_url = CONTACTS_URL + "?" + contact_query

    request = urllib.request.Request(
        contact_url,
        headers={"User-Agent": "ConstructionRadar/1.0"}
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        contacts = json.loads(response.read().decode("utf-8"))

    for i, record in enumerate(contacts, 1):
        print(f"\n--- CONTACT {i} ---")
        print(json.dumps(record, indent=2))
if __name__ == "__main__":
    main()
    diagnostic_check()
