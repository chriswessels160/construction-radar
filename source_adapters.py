"""Source adapters and failure-isolated orchestration."""

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from permit_schema import SCHEMA_VERSION, validate_project


@dataclass
class AdapterResult:
    source_id: str
    status: str
    projects: list = field(default_factory=list)
    message: str = ""


class CincinnatiHamiltonAdapter:
    source_id = "cincinnati-building-permits"

    def __init__(self, fetch_permits, fetch_contacts, build_lookup, relevant, normalize):
        self.fetch_permits = fetch_permits
        self.fetch_contacts = fetch_contacts
        self.build_lookup = build_lookup
        self.relevant = relevant
        self.normalize = normalize

    def run(self, geocode_cache):
        permits = self.fetch_permits()
        try:
            contacts = self.fetch_contacts(permits)
        except Exception as error:
            print(f"WARNING [{self.source_id}]: contractor contacts failed: {error}")
            contacts = []

        contractor_map = self.build_lookup(contacts)
        projects = [
            self.normalize(record, contractor_map, geocode_cache)
            for record in permits
            if self.relevant(record)
        ]
        return AdapterResult(self.source_id, "success", projects)


class LouisvilleJeffersonAdapter:
    """Official Louisville Metro ArcGIS active-construction-permits adapter."""

    source_id = "louisville-metro-active-construction-permits"
    layer_url = (
        "https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/"
        "active_construction_permits/FeatureServer/0"
    )
    source_url = (
        "https://louisville-metro-opendata-lojic.hub.arcgis.com/datasets/"
        "LOJIC::louisville-metro-ky-active-construction-permits"
    )

    def __init__(self, relevant, classify_market, electrical_score, parse_money, format_money, days_back=60):
        self.relevant = relevant
        self.classify_market = classify_market
        self.electrical_score = electrical_score
        self.parse_money = parse_money
        self.format_money = format_money
        self.days_back = days_back

    def fetch_records(self):
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=self.days_back)
        ).strftime("%Y-%m-%d")
        records = []
        offset = 0

        while True:
            query = {
                "where": f"ISSUE_DATE >= DATE '{cutoff}'",
                "outFields": "*",
                "returnGeometry": "false",
                "orderByFields": "ISSUE_DATE DESC",
                "resultOffset": str(offset),
                "resultRecordCount": "1000",
                "f": "json",
            }
            url = f"{self.layer_url}/query?{urllib.parse.urlencode(query)}"
            request = urllib.request.Request(
                url, headers={"User-Agent": "ConstructionRadar/1.0"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))

            if payload.get("error"):
                raise RuntimeError(payload["error"].get("message", "ArcGIS query failed"))
            batch = [feature.get("attributes", {}) for feature in payload.get("features", [])]
            records.extend(batch)
            if len(batch) < 1000:
                break
            offset += len(batch)

        return records

    @staticmethod
    def _text(value, default="Unknown"):
        text = str(value).strip() if value is not None else ""
        return text or default

    @staticmethod
    def _issued_date(value):
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, timezone.utc).strftime("%Y-%m-%d")
        return LouisvilleJeffersonAdapter._text(value)

    def normalize_record(self, record):
        permit_number = self._text(record.get("PERMIT_NUMBER"))
        permit_type = self._text(record.get("PERMIT_TYPE"))
        work_class = self._text(record.get("WORK_TYPE"))
        proposed_use = self._text(record.get("CATEGORY_NAME"))
        address = self._text(record.get("ADDRESS"))
        city = self._text(record.get("CITY"), "Louisville")
        state = self._text(record.get("STATE"), "KY")
        contractor = self._text(record.get("CONTRACTOR"))
        value = self.parse_money(record.get("PROJECT_COSTS"))
        description = " - ".join(
            part for part in (work_class, proposed_use) if part != "Unknown"
        ) or "Construction Permit"
        market = self.classify_market(description, proposed_use, permit_type, work_class)
        score, reason = self.electrical_score(description, proposed_use, work_class, value)
        contractors = []
        if contractor.upper() not in {"UNKNOWN", "OWNER", "N/A", "NONE"}:
            contractors.append({
                "name": contractor,
                "role": "contractor",
                "source": "Louisville Metro Active Construction Permits",
                "source_field": "CONTRACTOR",
            })
        else:
            contractor = "Unknown"

        project = {
            "schema_version": SCHEMA_VERSION,
            "record_id": f"{self.source_id}:{permit_number}",
            "source_id": self.source_id,
            "project": f"{proposed_use} - {address}" if proposed_use != "Unknown" else f"{description[:70]} - {address}",
            "address": address,
            "city": city,
            "county": "Jefferson",
            "state": state,
            "latitude": record.get("LATITUDE"),
            "longitude": record.get("LONGITUDE"),
            "type": permit_type,
            "market": market,
            "work_class": work_class,
            "proposed_use": proposed_use,
            "status": self._text(record.get("PERMIT_STATUS")),
            "value": self.format_money(value),
            "value_numeric": value,
            "permit_number": permit_number,
            "issued_date": self._issued_date(record.get("ISSUE_DATE")),
            "description": description,
            "company": contractor,
            "contractor": contractor,
            "contractors": contractors,
            "general_contractor": contractor,
            "electrical_contractor": contractor if "elect" in f"{permit_type} {work_class}".lower() else "Unknown",
            "bid_date": "Unknown",
            "opportunity": f"{score}/10",
            "opportunity_score": score,
            "opportunity_reason": reason,
            "source": "Louisville Metro Active Construction Permits",
            "source_url": self.source_url,
            "contractor_source": contractors[0]["source"] if contractors else "Unknown",
            "date_discovered": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }
        return validate_project(project)

    def run(self, geocode_cache):
        del geocode_cache
        records = self.fetch_records()
        projects = []
        for record in records:
            relevance_record = {
                "description": record.get("WORK_TYPE"),
                "proposeduse": record.get("CATEGORY_NAME"),
                "permittype": record.get("PERMIT_TYPE"),
                "workclass": record.get("WORK_TYPE"),
                "estprojectcostdec": record.get("PROJECT_COSTS"),
            }
            if self.relevant(relevance_record):
                projects.append(self.normalize_record(record))
        return AdapterResult(self.source_id, "success", projects)


class UnverifiedCountyAdapter:
    """Safe scaffold: documents a source without making network requests."""

    def __init__(self, source_id, jurisdiction, official_url, reason):
        self.source_id = source_id
        self.jurisdiction = jurisdiction
        self.official_url = official_url
        self.reason = reason

    def run(self, geocode_cache):
        del geocode_cache
        return AdapterResult(
            self.source_id,
            "skipped",
            message=(
                f"{self.jurisdiction} disabled: {self.reason} "
                f"Official information: {self.official_url}"
            ),
        )


def run_adapters(adapters, geocode_cache):
    """Run every source independently; one failure cannot block the others."""
    results = []
    for adapter in adapters:
        try:
            result = adapter.run(geocode_cache)
        except Exception as error:
            result = AdapterResult(adapter.source_id, "failed", message=str(error))
        results.append(result)
        print(f"SOURCE [{result.source_id}] {result.status}: {result.message}")
    return results


def kentucky_scaffolds():
    common_reason = (
        "no authoritative public bulk/API feed with verified automated-access "
        "terms has been identified"
    )
    return [
        UnverifiedCountyAdapter(
            "boone-county-ky-permits",
            "Boone County, Kentucky",
            "https://www.boonecountyky.org/departments/building_department/index.php",
            common_reason,
        ),
        UnverifiedCountyAdapter(
            "kenton-county-ky-permits",
            "Kenton County, Kentucky",
            "https://www.pdskc.org/services/one-stop-shop/",
            common_reason,
        ),
        UnverifiedCountyAdapter(
            "campbell-county-ky-permits",
            "Campbell County, Kentucky",
            "https://campbellcountyky.gov/department/index.php?structureid=37",
            common_reason,
        ),
    ]
