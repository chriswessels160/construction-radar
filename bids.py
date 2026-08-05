"""Fetch current City of Cincinnati business opportunities."""

import json
import os
import tempfile
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from zoneinfo import ZoneInfo


SOURCE_URL = "https://www.cincinnati-oh.gov/noncms/cmgr/business-opportunities/"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "bids.json")
LOCAL_ZONE = ZoneInfo("America/New_York")


class CincinnatiBidTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.row_attrs = {}
        self.cells = []
        self.cell_parts = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table" and attrs.get("id") == "projects":
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.in_row = True
            self.row_attrs = attrs
            self.cells = []
        elif self.in_row and tag == "td":
            self.in_cell = True
            self.cell_parts = []

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


def classify_bid(name, department):
    text = f"{name} {department}".lower()
    electrical_terms = (
        "electric", "lighting", "signal", "generator", "transformer",
        "switchgear", "cabling", "fiber optic", "fire alarm", "solar",
        "controls", "hvac", "rtu",
    )
    construction_terms = (
        "construction", "renovation", "repair", "replacement", "install",
        "rehabilitation", "building", "roof", "sewer", "water main",
        "bridge", "demolition", "restoration", "treatment plant",
    )
    if any(term in text for term in electrical_terms):
        return "Electrical match"
    if any(term in text for term in construction_terms):
        return "Construction match"
    return "Other city bid"


def parse_open_bids(html, now=None):
    parser = CincinnatiBidTableParser()
    parser.feed(html)
    now = now or datetime.now(timezone.utc)
    bids = []
    for attrs, cells in parser.rows:
        bid_number, status, name, department, buyer, procurement_type, inclusion, due_text, _award = cells[:9]
        if status.casefold() != "accepting bids":
            continue
        try:
            due = datetime.strptime(due_text, "%m/%d/%Y %I:%M %p").replace(
                tzinfo=LOCAL_ZONE
            )
        except ValueError:
            continue
        if due <= now:
            continue
        bids.append({
            "record_id": f"cincinnati-open-bids:{bid_number}",
            "source_id": "cincinnati-open-bids",
            "bid_number": bid_number,
            "status": status,
            "project_name": name,
            "department": department or "City of Cincinnati",
            "buyer": buyer or "Unknown",
            "procurement_type": procurement_type or "Unknown",
            "inclusion": inclusion or "None published",
            "due_at": due.isoformat().replace("+00:00", "Z"),
            "due_display": due_text,
            "match_type": classify_bid(name, department),
            "source": "City of Cincinnati Office of Procurement",
            "source_url": SOURCE_URL,
            "document_code": attrs.get("data-doccd", ""),
            "department_id": attrs.get("data-deptid", ""),
        })
    return sorted(bids, key=lambda bid: bid["due_at"])


def fetch_open_bids():
    request = urllib.request.Request(
        SOURCE_URL, headers={"User-Agent": "ConstructionRadar/1.0"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        html = response.read().decode("utf-8", errors="replace")
    return parse_open_bids(html)


def write_bids(bids):
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_url": SOURCE_URL,
        "count": len(bids),
        "bids": bids,
    }
    output_dir = os.path.dirname(OUTPUT_PATH)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix="bids-", suffix=".json", dir=output_dir
    )
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
    current_bids = fetch_open_bids()
    if not current_bids:
        raise RuntimeError("Cincinnati source returned no current open bids")
    write_bids(current_bids)
    print(f"Wrote {len(current_bids)} current Cincinnati bids to {OUTPUT_PATH}")
