"""Fetch public-sector bid opportunities with per-source failure isolation."""

import html as html_module
import hashlib
import json
import os
import re
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from zoneinfo import ZoneInfo


OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "bids.json")
LOCAL_ZONE = ZoneInfo("America/New_York")
USER_AGENT = "ConstructionRadar/1.0 (+public procurement aggregation)"

BID_SOURCES = [
    {"source_id": "cincinnati-business-opportunities", "name": "City of Cincinnati", "url": "https://www.cincinnati-oh.gov/noncms/cmgr/business-opportunities/", "kind": "cincinnati"},
    {"source_id": "nky-sd1-bids", "name": "Sanitation District No. 1", "url": "https://www.sd1.org/bids.aspx", "kind": "civicplus"},
    {"source_id": "florence-ky-bids", "name": "City of Florence", "url": "https://florence-ky.gov/publication-of-bid-solicitations-enacted-ordinances/", "kind": "florence"},
    {"source_id": "newport-ky-bids", "name": "City of Newport", "url": "https://www.newportky.gov/bids.aspx", "kind": "civicplus"},
    {"source_id": "kenton-county-ky-bids", "name": "Kenton County", "url": "https://procurement.opengov.com/portal/kentoncounty", "fetch_url": "https://procurement.opengov.com/portal/embed/kentoncounty/project-list?departmentId=all&status=all&limit=100", "kind": "opengov"},
    {"source_id": "campbell-county-ky-bids", "name": "Campbell County", "url": "https://campbellcountyky.gov/division/blocks.php?structureid=99", "kind": "monitor"},
    {"source_id": "covington-ky-bids", "name": "City of Covington", "url": "https://covingtonky.bonfirehub.com/portal/?tab=openOpportunities", "fetch_url": "https://covingtonky.bonfirehub.com/PublicPortal/getOpenPublicOpportunitiesSectionData", "kind": "bonfire"},
    {"source_id": "cvg-airport-bids", "name": "CVG Airport", "url": "https://procurement.opengov.com/portal/cvgairport", "fetch_url": "https://procurement.opengov.com/portal/embed/cvgairport/project-list?departmentId=all&status=all&limit=100", "kind": "opengov"},
    {"source_id": "nku-bids", "name": "Northern Kentucky University", "url": "https://www.nkuplanroom.com/View/ViewJobList.aspx?group_id=public_all", "kind": "nku"},
]


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(html_module.unescape(value).split())


def parse_datetime(value, formats=()):
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=LOCAL_ZONE) if parsed.tzinfo is None else parsed
    except ValueError:
        pass
    for date_format in formats:
        try:
            return datetime.strptime(value.strip(), date_format).replace(tzinfo=LOCAL_ZONE)
        except ValueError:
            continue
    return None


def classify_bid(name, department):
    text = f"{name} {department}".lower()
    electrical_terms = (
        "electric", "lighting", "signal", "generator", "transformer",
        "switchgear", "cabling", "fiber optic", "fire alarm", "solar",
        "controls", "hvac", "rtu",
    )
    construction_terms = (
        "construction", "renovation", "remodel", "repair", "replacement", "install",
        "rehabilitation", "building", "roof", "sewer", "water main",
        "bridge", "demolition", "restoration", "treatment plant", "paving",
        "engineering", "architect", "inspection",
    )
    if any(term in text for term in electrical_terms):
        return "Electrical match"
    if any(term in text for term in construction_terms):
        return "Construction match"
    return "Other public bid"


def make_bid(source, record_key, name, status, due=None, **fields):
    now = fields.pop("now", None) or datetime.now(timezone.utc)
    open_statuses = {"open", "accepting bids", "released", "active"}
    is_open = status.casefold() in open_statuses and due is not None and due > now
    bid_number = str(fields.pop("bid_number", "") or record_key)
    department = fields.pop("department", "") or source["name"]
    return {
        "record_id": f"{source['source_id']}:{record_key}",
        "source_id": source["source_id"],
        "bid_number": bid_number,
        "status": status or "Unknown",
        "project_name": name,
        "department": department,
        "buyer": fields.pop("buyer", "") or "Unknown",
        "procurement_type": fields.pop("procurement_type", "") or "Unknown",
        "inclusion": fields.pop("inclusion", "") or "None published",
        "due_at": due.isoformat() if due else "",
        "due_display": fields.pop("due_display", "") or (due.astimezone(LOCAL_ZONE).strftime("%m/%d/%Y %I:%M %p") if due else "Unknown"),
        "is_open": is_open,
        "awarded_contractor": fields.pop("awarded_contractor", "") or "None published",
        "match_type": classify_bid(name, department),
        "source": source["name"],
        "source_url": fields.pop("source_url", "") or source["url"],
        **fields,
    }


class CincinnatiBidTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = self.in_row = self.in_cell = False
        self.row_attrs, self.cells, self.cell_parts, self.rows = {}, [], [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table" and attrs.get("id") == "projects":
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.in_row, self.row_attrs, self.cells = True, attrs, []
        elif self.in_row and tag == "td":
            self.in_cell, self.cell_parts = True, []

    def handle_data(self, data):
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.in_cell:
            self.cells.append(" ".join("".join(self.cell_parts).split()))
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if len(self.cells) >= 9:
                self.rows.append((self.row_attrs, self.cells))
            self.in_row = False
        elif tag == "table" and self.in_table:
            self.in_table = False


def parse_bids(html, now=None):
    """Parse Cincinnati's complete current and historical table."""
    source = BID_SOURCES[0]
    parser = CincinnatiBidTableParser()
    parser.feed(html)
    now = now or datetime.now(timezone.utc)
    bids = []
    for attrs, cells in parser.rows:
        number, status, name, department, buyer, kind, inclusion, due_text, award = cells[:9]
        due = parse_datetime(due_text, ("%m/%d/%Y %I:%M %p",))
        record_key = attrs.get("data-docid") or number
        bids.append(make_bid(
            source, record_key, name, status, due, now=now, bid_number=number,
            department=department, buyer=buyer, procurement_type=kind,
            inclusion=inclusion, due_display=due_text, awarded_contractor=award,
            document_code=attrs.get("data-doccd", ""),
            department_id=attrs.get("data-deptid", ""),
        ))
    duplicate_ids = {
        record_id for record_id in (bid["record_id"] for bid in bids)
        if sum(item["record_id"] == record_id for item in bids) > 1
    }
    for bid in bids:
        if bid["record_id"] in duplicate_ids:
            fingerprint = hashlib.sha1(
                f"{bid['bid_number']}|{bid['due_display']}|{bid['project_name']}".encode("utf-8")
            ).hexdigest()[:10]
            bid["record_id"] = f"{bid['record_id']}:{fingerprint}"
    return bids


def parse_open_bids(html, now=None):
    return sorted((bid for bid in parse_bids(html, now) if bid["is_open"]), key=lambda bid: bid["due_at"])


def parse_civicplus_bids(html, source, now=None):
    bids_by_id = {}
    card_pattern = re.compile(r'<div class="listItemsRow bid[^\"]*">(.*?)(?=<div class="listItemsRow bid|</div>\s*</div>\s*<script)', re.I | re.S)
    for card in card_pattern.findall(html):
        link = re.search(r'<a href="([^"]*bidID=(\d+)[^"]*)">(.*?)</a>', card, re.I | re.S)
        if not link:
            continue
        detail_url = urllib.parse.urljoin(source["url"], html_module.unescape(link.group(1)))
        name, record_key = clean_text(link.group(3)), link.group(2)
        number_match = re.search(r'<strong>Bid No\.</strong>\s*([^<]+)', card, re.I)
        status_block = re.search(r'class="bidStatus".*?<div>.*?</div>\s*<div>(.*?)</div>', card, re.I | re.S)
        values = re.findall(r'<span[^>]*>(.*?)</span>', status_block.group(1), re.I | re.S) if status_block else []
        status = clean_text(values[0]) if values else "Unknown"
        due_text = clean_text(values[1]) if len(values) > 1 else ""
        due = parse_datetime(due_text, ("%m/%d/%Y %I:%M %p",))
        bids_by_id[record_key] = make_bid(
            source, record_key, name, status, due, now=now,
            bid_number=clean_text(number_match.group(1)) if number_match else record_key,
            due_display=due_text, source_url=detail_url,
        )
    return list(bids_by_id.values())


def parse_florence_bids(html, source, now=None):
    bids_by_id = {}
    sections = [
        ("current", re.search(r'Current Bid Solicitations(.*?)(?:Title VI Program Plan|Inactive/Prior Bid Solicitations)', html, re.I | re.S)),
        ("history", re.search(r'Inactive/Prior Bid Solicitations(.*?)(?:Property Tax Info|</main>)', html, re.I | re.S)),
    ]
    for section_name, match in sections:
        if not match:
            continue
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', match.group(1), re.I | re.S)
        for index, row in enumerate(rows):
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.I | re.S)
            if len(cells) < 2:
                continue
            name, due_text = clean_text(cells[0]), clean_text(cells[1])
            if not name or name.casefold().startswith("bid/rfp"):
                continue
            due = parse_datetime(due_text, ("%m-%d-%y", "%m/%d/%y", "%m-%d-%Y"))
            link = re.search(r'href=["\']([^"\']+)', row, re.I)
            record_key = re.sub(r"[^a-z0-9]+", "-", f"{due_text}-{name}".lower()).strip("-")
            bids_by_id[record_key or str(index)] = make_bid(
                source, record_key or str(index), name,
                "Accepting Bids" if section_name == "current" else "Closed",
                due, now=now, bid_number="Not published", due_display=due_text,
                source_url=urllib.parse.urljoin(source["url"], html_module.unescape(link.group(1))) if link else source["url"],
            )
    return list(bids_by_id.values())


def extract_opengov_projects(html):
    marker = "window.__data="
    start = html.find(marker)
    if start < 0:
        return []
    serialized = html[start + len(marker):]
    # OpenGov serializes a harmless Redux no-op callback alongside otherwise
    # valid JSON. It carries no public data, so replace only that exact shape.
    serialized = re.sub(
        r"function\s+noop\(\)\s*\{\s*// No operation performed\.\s*\}",
        "null",
        serialized,
    )
    serialized = re.sub(r"(?<=:)undefined(?=[,}])", "null", serialized)
    data, _ = json.JSONDecoder().raw_decode(serialized)
    projects = {}

    def visit(value):
        if isinstance(value, dict):
            if {"id", "title", "status", "government", "department"}.issubset(value):
                projects[str(value["id"])] = value
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(data)
    return list(projects.values())


def parse_opengov_bids(html, source, now=None):
    bids = []
    for project in extract_opengov_projects(html):
        due = parse_datetime(project.get("proposalDeadline", ""))
        status_raw = str(project.get("status", "Unknown"))
        status = {"open": "Open", "evaluation": "Under Review", "closed": "Closed", "awardpending": "Award Pending"}.get(status_raw.casefold(), status_raw.replace("_", " ").title())
        department = (project.get("department") or {}).get("name", source["name"])
        kind = (project.get("template") or {}).get("title", "Unknown")
        number = project.get("financialId") or str(project["id"])
        detail_url = f"https://procurement.opengov.com/portal/{project.get('government', {}).get('code', '')}/projects/{project['id']}"
        bids.append(make_bid(
            source, project["id"], project["title"], status, due, now=now,
            bid_number=number, department=department, procurement_type=kind,
            source_url=detail_url,
        ))
    return bids


def parse_bonfire_bids(text, source, now=None):
    payload = json.loads(text).get("payload", {})
    projects = payload.get("projects", {})
    if isinstance(projects, dict):
        projects = projects.values()
    bids = []
    for project in projects:
        due = parse_datetime(project.get("DateClose", ""), ("%Y-%m-%d %H:%M:%S",))
        project_id = str(project.get("ProjectID", ""))
        detail_url = f"https://covingtonky.bonfirehub.com/opportunities/{project.get('PrivateProjectID', '')}"
        bids.append(make_bid(
            source, project_id, project.get("ProjectName", "Unnamed opportunity"),
            "Open", due, now=now, bid_number=project.get("ReferenceID", project_id),
            procurement_type="Public solicitation", source_url=detail_url,
        ))
    return bids


def parse_nku_bids(html, source, now=None):
    if "No Projects posted at this time" in html:
        return []
    bids = []
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.I | re.S):
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.I | re.S)
        if len(cells) < 2:
            continue
        name = clean_text(cells[0])
        due_text = next((clean_text(cell) for cell in cells[1:] if re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', clean_text(cell))), "")
        due = parse_datetime(due_text, ("%m/%d/%Y %I:%M %p", "%m/%d/%Y"))
        link = re.search(r'href=["\']([^"\']+)', row, re.I)
        if name and due:
            key = re.sub(r"[^a-z0-9]+", "-", f"{due_text}-{name}".lower()).strip("-")
            bids.append(make_bid(source, key, name, "Open", due, now=now, source_url=urllib.parse.urljoin(source["url"], link.group(1)) if link else source["url"]))
    return bids


def fetch_text(url, headers=None):
    request_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    request = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_source(source, now=None):
    kind = source["kind"]
    if kind == "cincinnati":
        return parse_bids(fetch_text(source["url"]), now)
    if kind == "civicplus":
        separator = "&" if "?" in source["url"] else "?"
        return parse_civicplus_bids(fetch_text(f"{source['url']}{separator}showAllBids=on"), source, now)
    if kind == "florence":
        return parse_florence_bids(fetch_text(source["url"]), source, now)
    if kind == "opengov":
        return parse_opengov_bids(fetch_text(source["fetch_url"]), source, now)
    if kind == "bonfire":
        return parse_bonfire_bids(fetch_text(source["fetch_url"], {"X-Requested-With": "XMLHttpRequest", "Referer": source["url"]}), source, now)
    if kind == "nku":
        return parse_nku_bids(fetch_text(source["url"]), source, now)
    if kind == "monitor":
        fetch_text(source["url"])
        return []
    raise ValueError(f"Unsupported bid source kind: {kind}")


def fetch_bids(now=None, previous_records=None):
    bids, source_results = [], []
    previous_by_source = {}
    if previous_records is None:
        try:
            with open(OUTPUT_PATH, encoding="utf-8") as handle:
                previous_records = json.load(handle).get("bids", [])
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            previous_records = []
    for record in previous_records:
        previous_by_source.setdefault(record.get("source_id"), []).append(record)
    for source in BID_SOURCES:
        try:
            records = fetch_source(source, now)
            bids.extend(records)
            source_results.append({**source, "status": "success", "count": len(records), "open_count": sum(record["is_open"] for record in records)})
            print(f"BID SOURCE [{source['source_id']}] success: {len(records)} records")
        except Exception as error:
            records = previous_by_source.get(source["source_id"], [])
            bids.extend(records)
            source_results.append({**source, "status": "stale" if records else "failed", "count": len(records), "open_count": sum(record.get("is_open", False) for record in records), "error": str(error)})
            print(f"BID SOURCE [{source['source_id']}] failed: {error}; preserved {len(records)} prior records")
    return bids, source_results


def write_bids(bids, sources=None):
    payload = {
        "schema_version": "2.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "count": len(bids),
        "open_count": sum(bid["is_open"] for bid in bids),
        "sources": sources or [],
        "bids": bids,
    }
    descriptor, temporary_path = tempfile.mkstemp(prefix="bids-", suffix=".json", dir=os.path.dirname(OUTPUT_PATH))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary_path, OUTPUT_PATH)
    except Exception:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise


if __name__ == "__main__":
    opportunities, results = fetch_bids()
    if not opportunities:
        raise RuntimeError("All bid sources returned no opportunities")
    write_bids(opportunities, results)
    print(f"Wrote {len(opportunities)} opportunities ({sum(bid['is_open'] for bid in opportunities)} currently open) to {OUTPUT_PATH}")
