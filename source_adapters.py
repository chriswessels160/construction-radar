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


@dataclass(frozen=True)
class ArcGISPermitConfig:
    """Declarative mapping for an official ArcGIS permit layer."""

    source_id: str
    layer_url: str
    source_url: str
    source_name: str
    jurisdiction: str
    county: str
    state: str
    default_city: str
    date_field: str
    fields: dict
    page_size: int = 1000
    return_geometry: bool = False


class ConfigurableArcGISPermitAdapter:
    """Reusable ArcGIS FeatureServer adapter driven by verified field mappings."""

    config = None

    def __init__(self, relevant, classify_market, electrical_score, parse_money, format_money, days_back=60):
        if self.config is None:
            raise TypeError("ArcGIS adapter requires a source configuration")
        self.source_id = self.config.source_id
        self.layer_url = self.config.layer_url
        self.source_url = self.config.source_url
        self.relevant = relevant
        self.classify_market = classify_market
        self.electrical_score = electrical_score
        self.parse_money = parse_money
        self.format_money = format_money
        self.days_back = days_back

    def _field(self, logical_name):
        return self.config.fields.get(logical_name)

    def _value(self, record, logical_name):
        field_name = self._field(logical_name)
        return record.get(field_name) if field_name else None

    def fetch_records(self):
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=self.days_back)
        ).strftime("%Y-%m-%d")
        records = []
        offset = 0

        while True:
            query = {
                "where": f"{self.config.date_field} >= DATE '{cutoff}'",
                "outFields": "*",
                "returnGeometry": str(self.config.return_geometry).lower(),
                "orderByFields": f"{self.config.date_field} DESC",
                "resultOffset": str(offset),
                "resultRecordCount": str(self.config.page_size),
                "f": "json",
            }
            if self.config.return_geometry:
                query["outSR"] = "4326"

            url = f"{self.layer_url}/query?{urllib.parse.urlencode(query)}"
            request = urllib.request.Request(
                url, headers={"User-Agent": "ConstructionRadar/1.0"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))

            if payload.get("error"):
                raise RuntimeError(payload["error"].get("message", "ArcGIS query failed"))

            batch = []
            for feature in payload.get("features", []):
                record = dict(feature.get("attributes", {}))
                geometry = feature.get("geometry") or {}
                record["_geometry_x"] = geometry.get("x")
                record["_geometry_y"] = geometry.get("y")
                batch.append(record)

            records.extend(batch)
            if not payload.get("exceededTransferLimit") and len(batch) < self.config.page_size:
                break
            if not batch:
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
        return ConfigurableArcGISPermitAdapter._text(value)

    def normalize_record(self, record):
        permit_number = self._text(self._value(record, "permit_number"))
        if permit_number == "Unknown":
            raise ValueError(f"{self.source_id} record is missing its permit number")

        permit_type = self._text(self._value(record, "permit_type"))
        work_class = self._text(self._value(record, "work_class"))
        proposed_use = self._text(self._value(record, "proposed_use"))
        address = self._text(self._value(record, "address"))
        city = self._text(self._value(record, "city"), self.config.default_city)
        state = self._text(self._value(record, "state"), self.config.state)
        contractor = self._text(self._value(record, "contractor"))
        value = self.parse_money(self._value(record, "value"))
        description = " - ".join(
            part for part in (work_class, proposed_use) if part != "Unknown"
        ) or "Construction Permit"
        market = self.classify_market(description, proposed_use, permit_type, work_class)
        score, reason = self.electrical_score(description, proposed_use, work_class, value)
        contractors = []
        contractor_field = self._field("contractor")

        if contractor_field and contractor.upper() not in {"UNKNOWN", "OWNER", "N/A", "NONE"}:
            contractors.append({
                "name": contractor,
                "role": "contractor",
                "source": self.config.source_name,
                "source_field": contractor_field,
            })
        else:
            contractor = "Unknown"

        applicant = self._text(
            self._value(record, "applicant_business") or self._value(record, "applicant_name")
        )
        latitude = self._value(record, "latitude")
        longitude = self._value(record, "longitude")
        if latitude is None:
            latitude = record.get("_geometry_y")
        if longitude is None:
            longitude = record.get("_geometry_x")
        record_source_url = self._text(self._value(record, "record_url"), self.config.source_url)

        project = {
            "schema_version": SCHEMA_VERSION,
            "record_id": f"{self.source_id}:{permit_number}",
            "source_id": self.source_id,
            "project": f"{proposed_use} - {address}" if proposed_use != "Unknown" else f"{description[:70]} - {address}",
            "address": address,
            "city": city,
            "jurisdiction": self.config.jurisdiction,
            "county": self.config.county,
            "state": state,
            "latitude": latitude,
            "longitude": longitude,
            "type": permit_type,
            "market": market,
            "work_class": work_class,
            "proposed_use": proposed_use,
            "status": self._text(self._value(record, "status")),
            "value": self.format_money(value),
            "value_numeric": value,
            "permit_number": permit_number,
            "issued_date": self._issued_date(self._value(record, "issued_date")),
            "description": description,
            "company": contractor,
            "contractor": contractor,
            "contractors": contractors,
            "general_contractor": contractor,
            "electrical_contractor": contractor if "elect" in f"{permit_type} {work_class}".lower() else "Unknown",
            "applicant": applicant,
            "applicant_source": self.config.source_name if applicant != "Unknown" else "Unknown",
            "bid_date": "Unknown",
            "opportunity": f"{score}/10",
            "opportunity_score": score,
            "opportunity_reason": reason,
            "source": self.config.source_name,
            "source_url": record_source_url,
            "contractor_source": contractors[0]["source"] if contractors else "Unknown",
            "date_discovered": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }
        return validate_project(project)

    def run(self, geocode_cache):
        del geocode_cache
        projects = []
        for record in self.fetch_records():
            relevance_record = {
                "description": self._value(record, "proposed_use"),
                "proposeduse": self._value(record, "proposed_use"),
                "permittype": self._value(record, "permit_type"),
                "workclass": self._value(record, "work_class"),
                "estprojectcostdec": self._value(record, "value"),
            }
            if self.relevant(relevance_record):
                projects.append(self.normalize_record(record))
        return AdapterResult(self.source_id, "success", projects)


class LouisvilleJeffersonAdapter(ConfigurableArcGISPermitAdapter):
    """Official Louisville Metro active-construction-permits source."""

    source_id = "louisville-metro-active-construction-permits"
    layer_url = (
        "https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/"
        "active_construction_permits/FeatureServer/0"
    )
    source_url = (
        "https://louisville-metro-opendata-lojic.hub.arcgis.com/datasets/"
        "LOJIC::louisville-metro-ky-active-construction-permits"
    )
    config = ArcGISPermitConfig(
        source_id=source_id,
        layer_url=layer_url,
        source_url=source_url,
        source_name="Louisville Metro Active Construction Permits",
        jurisdiction="Louisville Metro",
        county="Jefferson",
        state="KY",
        default_city="Louisville",
        date_field="ISSUE_DATE",
        fields={
            "permit_number": "PERMIT_NUMBER",
            "permit_type": "PERMIT_TYPE",
            "status": "PERMIT_STATUS",
            "contractor": "CONTRACTOR",
            "proposed_use": "CATEGORY_NAME",
            "work_class": "WORK_TYPE",
            "value": "PROJECT_COSTS",
            "address": "ADDRESS",
            "city": "CITY",
            "state": "STATE",
            "latitude": "LATITUDE",
            "longitude": "LONGITUDE",
            "issued_date": "ISSUE_DATE",
        },
    )


class ColumbusBuildingPermitsAdapter(ConfigurableArcGISPermitAdapter):
    """Official City of Columbus nightly building-permit source."""

    source_id = "columbus-building-permits"
    layer_url = (
        "https://services1.arcgis.com/9yy6msODkIBzkUXU/arcgis/rest/services/"
        "Building_Permits/FeatureServer/0"
    )
    source_url = "https://www.arcgis.com/home/item.html?id=f7a785b863454d96a0fe3f5aa5368e7d"
    config = ArcGISPermitConfig(
        source_id=source_id,
        layer_url=layer_url,
        source_url=source_url,
        source_name="City of Columbus Building Permits",
        jurisdiction="Columbus",
        county="Unknown",
        state="OH",
        default_city="Columbus",
        date_field="ISSUED_DT",
        return_geometry=True,
        page_size=2000,
        fields={
            "permit_number": "B1_ALT_ID",
            "permit_type": "GENERAL_TYPE",
            "status": "PERMIT_STATUS",
            "proposed_use": "VALUE_DESC",
            "work_class": "B1_PER_SUB_TYPE",
            "value": "G3_VALUE_TTL",
            "address": "SITE_ADDRESS",
            "issued_date": "ISSUED_DT",
            "record_url": "ACA_URL",
            "applicant_business": "APPLICANT_BUS_NAME",
            "applicant_name": "APPLICANT_FULL_NAME",
        },
    )


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
