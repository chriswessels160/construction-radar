"""Source adapters and failure-isolated orchestration."""

import json
import time
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
    where_clause: str = ""
    max_records: int = 5000
    allow_unvalued_commercial: bool = False


class ConfigurableArcGISPermitAdapter:
    """Reusable ArcGIS FeatureServer adapter driven by verified field mappings."""

    config = None

    def __init__(self, relevant, classify_market, electrical_score, parse_money, format_money, days_back=60, config=None):
        if config is not None:
            self.config = config
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
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=self.days_back)).strftime("%Y-%m-%d")
        where = self.config.where_clause.format(
            cutoff=cutoff, year=now.year, month=now.month
        ) if self.config.where_clause else f"{self.config.date_field} >= DATE '{cutoff}'"
        records = []
        offset = 0

        while True:
            query = {
                "where": where,
                "outFields": "*",
                "returnGeometry": str(self.config.return_geometry).lower(),
                "resultOffset": str(offset),
                "resultRecordCount": str(self.config.page_size),
                "f": "json",
                "_ts": str(int(time.time())),
            }
            if self.config.date_field:
                query["orderByFields"] = f"{self.config.date_field} DESC"
            if self.config.return_geometry:
                query["outSR"] = "4326"

            url = f"{self.layer_url}/query?{urllib.parse.urlencode(query)}"
            request = urllib.request.Request(
                url, headers={"User-Agent": "ConstructionRadar/1.0"}
            )
            last_error = None
            for attempt in range(2):
                try:
                    with urllib.request.urlopen(request, timeout=60) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    break
                except Exception as error:
                    last_error = error
                    if attempt == 0:
                        time.sleep(1)
            else:
                raise last_error

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
            if len(records) >= self.config.max_records:
                records = records[:self.config.max_records]
                break
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
        address_number = self._text(self._value(record, "address_number"), "")
        if address_number and address != "Unknown":
            address = f"{address_number} {address}".strip()
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
            relevant = self.relevant(relevance_record)
            if not relevant and self.config.allow_unvalued_commercial:
                text = " ".join(
                    self._text(self._value(record, key), "")
                    for key in ("permit_type", "work_class", "proposed_use")
                ).lower()
                relevant = any(term in text for term in (
                    "commercial", "office", "retail", "industrial", "warehouse",
                    "hospital", "school", "hotel", "restaurant", "multifamily",
                    "multi-family", "apartment", "tenant improvement",
                ))
            if relevant:
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
        source_id=source_id, layer_url=layer_url, source_url=source_url,
        source_name="City of Columbus Building Permits", jurisdiction="Columbus",
        county="Unknown", state="OH", default_city="Columbus", date_field="ISSUED_DT",
        return_geometry=True, page_size=2000,
        fields={
            "permit_number": "B1_ALT_ID", "permit_type": "GENERAL_TYPE",
            "status": "PERMIT_STATUS", "proposed_use": "VALUE_DESC",
            "work_class": "B1_PER_SUB_TYPE", "value": "G3_VALUE_TTL",
            "address": "SITE_ADDRESS", "issued_date": "ISSUED_DT",
            "record_url": "ACA_URL", "applicant_business": "APPLICANT_BUS_NAME",
            "applicant_name": "APPLICANT_FULL_NAME",
        },
    )


def additional_city_configs():
    """Verified official permit layers that use the shared ArcGIS adapter."""
    return [
        ArcGISPermitConfig(
            source_id="cleveland-building-permits",
            layer_url="https://services3.arcgis.com/dty2kHktVXHrqO8i/arcgis/rest/services/Building_Permits/FeatureServer/0",
            source_url="https://www.arcgis.com/home/item.html?id=c08ddeaf2d1e41679a03103ff4e9fe17",
            source_name="City of Cleveland Building Permits", jurisdiction="Cleveland",
            county="Cuyahoga", state="OH", default_city="Cleveland", date_field="ISSUE_DATE",
            return_geometry=True, page_size=2000,
            fields={"permit_number":"PERMIT_ID","permit_type":"PERMIT_TYPE","status":"CURRENT_TASK_STATUS","contractor":"CONTRATOR_BUSINESS_NAME","proposed_use":"USE_GROUP_1","work_class":"WORK_DESCRIPTION","value":"JOB_VALUE","address":"PRIMARY_ADDRESS","issued_date":"ISSUE_DATE","record_url":"ACCELA_CITIZEN_ACCESS_URL"},
        ),
        ArcGISPermitConfig(
            source_id="detroit-building-permits",
            layer_url="https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/bseed_building_permits/FeatureServer/0",
            source_url="https://www.arcgis.com/home/item.html?id=86d47e86062e4beeb19344eb125b75d2",
            source_name="City of Detroit Building Permits", jurisdiction="Detroit",
            county="Wayne", state="MI", default_city="Detroit", date_field="issued_date",
            fields={"permit_number":"record_id","permit_type":"permit_type","status":"is_open_to_elements","proposed_use":"proposed_use_type","work_class":"work_description","value":"amt_estimated_contractor_cost","address":"address","issued_date":"issued_date","latitude":"latitude","longitude":"longitude"},
        ),
        ArcGISPermitConfig(
            source_id="austin-issued-building-permits",
            layer_url="https://services.arcgis.com/0L95CJ0VTaxqcmED/ArcGIS/rest/services/PLANNINGCADASTRE_issued_building_permits/FeatureServer/0",
            source_url="https://www.arcgis.com/home/item.html?id=3dfba2a413ee47ebae6c875890b79a59",
            source_name="City of Austin Issued Building Permits", jurisdiction="Austin",
            county="Travis", state="TX", default_city="Austin", date_field="ISSUE_DATE",
            return_geometry=True, page_size=2000,
            fields={"permit_number":"PERMIT_NUMBER","permit_type":"PERMIT_TYPE","status":"STATUS","proposed_use":"SUB_TYPE","work_class":"WORK_TYPE","value":"TOTAL_JOB_VALUATION","address":"PERMIT_LOCATION","city":"CITY","state":"STATE","issued_date":"ISSUE_DATE","record_url":"LINK","latitude":"LATITUDE","longitude":"LONGITUDE"},
        ),
        ArcGISPermitConfig(
            source_id="raleigh-building-permits",
            layer_url="https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services/Building_Permits/FeatureServer/0",
            source_url="https://www.arcgis.com/home/item.html?id=bdfad82b15344d37beb28d7f90b6c4be",
            source_name="City of Raleigh Building Permits", jurisdiction="Raleigh",
            county="Wake", state="NC", default_city="Raleigh", date_field="issueddate",
            fields={"permit_number":"permitnum","permit_type":"permittype","status":"statuscurrent","contractor":"contractorcompanyname","proposed_use":"proposeduse","work_class":"workclass","value":"estprojectcost","address":"originaladdress1","city":"originalcity","state":"originalstate","issued_date":"issueddate","latitude":"latitude_perm","longitude":"longitude_perm"},
        ),
        ArcGISPermitConfig(
            source_id="pasadena-active-building-permits",
            layer_url="https://services2.arcgis.com/zNjnZafDYCAJAbN0/arcgis/rest/services/Active_Building_Permits_view/FeatureServer/0",
            source_url="https://www.arcgis.com/home/item.html?id=fbcfc2f4307d4a4ba4e8c57e7db511ce",
            source_name="City of Pasadena Active Building Permits", jurisdiction="Pasadena",
            county="Los Angeles", state="CA", default_city="Pasadena", date_field="",
            return_geometry=True, where_clause="1=1", allow_unvalued_commercial=True,
            fields={"permit_number":"CASE_NUMBER","permit_type":"DESCRIPTION","status":"DESCRIPTION","work_class":"DESCRIPTION","address":"ADDRESS"},
        ),
        ArcGISPermitConfig(
            source_id="baltimore-building-permits",
            layer_url="https://egisdata.baltimorecity.gov/egis/rest/services/Housing/DHCD_Open_Baltimore_Datasets/FeatureServer/3",
            source_url="https://www.arcgis.com/home/item.html?id=189e6d1c65df4e13b38c0027cee574f6",
            source_name="City of Baltimore Housing and Building Permits", jurisdiction="Baltimore",
            county="Baltimore City", state="MD", default_city="Baltimore", date_field="IssuedDate",
            return_geometry=True,
            fields={"permit_number":"CaseNumber","permit_type":"PermitName","proposed_use":"ProposedUse","work_class":"Description","value":"Cost","address":"Address","issued_date":"IssuedDate"},
        ),
        ArcGISPermitConfig(
            source_id="beverly-hills-building-permits",
            layer_url="https://services5.arcgis.com/7CXE3aevo18HlHBC/arcgis/rest/services/Permit_Assessor_Export/FeatureServer/0",
            source_url="https://www.arcgis.com/home/item.html?id=d25f52e393d5436e844737d2e3447bf1",
            source_name="City of Beverly Hills Building Permit Report", jurisdiction="Beverly Hills",
            county="Los Angeles", state="CA", default_city="Beverly Hills", date_field="",
            where_clause="ISSUED_YEAR = {year}",
            fields={"permit_number":"PERMIT_NUMBER","permit_type":"PERMIT_TYPE","work_class":"PERMIT_DESCRIPTION","value":"VALUATION","address":"ADDRESS","applicant_name":"NAME"},
        ),
        ArcGISPermitConfig(
            source_id="las-vegas-building-permits",
            layer_url="https://services1.arcgis.com/F1v0ufATbBQScMtY/arcgis/rest/services/Bldg_Permits/FeatureServer/379",
            source_url="https://www.arcgis.com/home/item.html?id=a51e6fdbe4bb4562abf769842abad9d2",
            source_name="City of Las Vegas Building Permits", jurisdiction="Las Vegas",
            county="Clark", state="NV", default_city="Las Vegas", date_field="ISSUE_DT",
            return_geometry=True, page_size=2000,
            fields={"permit_number":"APNO","permit_type":"APTYPE","status":"Status","proposed_use":"APDESC","work_class":"WORKDESC","value":"VALUATION","address":"ADDR","issued_date":"ISSUE_DT","applicant_name":"APPLICANT"},
        ),
        ArcGISPermitConfig(
            source_id="washington-dc-building-permits",
            layer_url="https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/DCRA/FeatureServer/18",
            source_url="https://www.arcgis.com/home/item.html?id=7296e6392349498bb6ba6ba3db836644",
            source_name="District of Columbia Building Permits", jurisdiction="Washington",
            county="District of Columbia", state="DC", default_city="Washington", date_field="ISSUE_DATE",
            page_size=2000, allow_unvalued_commercial=True,
            fields={"permit_number":"PERMIT_ID","permit_type":"PERMIT_TYPE_NAME","status":"APPLICATION_STATUS_NAME","proposed_use":"PERMIT_CATEGORY_NAME","work_class":"DESC_OF_WORK","address":"FULL_ADDRESS","city":"CITY","state":"STATE","issued_date":"ISSUE_DATE","latitude":"LATITUDE","longitude":"LONGITUDE","applicant_name":"PERMIT_APPLICANT"},
        ),
        ArcGISPermitConfig(
            source_id="tempe-building-permits",
            layer_url="https://services.arcgis.com/lQySeXwbBg53XWDi/arcgis/rest/services/building_permits/FeatureServer/0",
            source_url="https://www.arcgis.com/home/item.html?id=55b38626464d48cb94e81cb8227d6fde",
            source_name="City of Tempe Building Safety Permits", jurisdiction="Tempe",
            county="Maricopa", state="AZ", default_city="Tempe", date_field="IssuedDateDtm",
            page_size=2000,
            fields={"permit_number":"PermitNum","permit_type":"PermitTypeDesc","status":"StatusCurrent","contractor":"ContractorCompanyName","proposed_use":"PermitClass","work_class":"Description","value":"EstProjectCost","address":"OriginalAddress1","city":"OriginalCity","state":"OriginalState","issued_date":"IssuedDateDtm","latitude":"Latitude","longitude":"Longitude"},
        ),
    ]


def licensed_county_configs():
    """CC BY 4.0 county slices from Shovels' Q1 2026 permit release."""
    layer_url = (
        "https://services5.arcgis.com/ygiShlCiglrHaijs/arcgis/rest/services/"
        "Nationwide_New_Construction_Permits/FeatureServer/0"
    )
    source_url = (
        "https://www.arcgis.com/home/item.html?id="
        "368d580663f641be8e9627fd3d444bbc"
    )
    source_name = (
        "Shovels Nationwide New Construction Permits (Q1 2026), CC BY 4.0"
    )
    fields = {
        "permit_number": "PERMIT_NUMBER",
        "permit_type": "CATEGORY",
        "status": "STATUS",
        "contractor": "CONTRACTOR_NAME",
        "proposed_use": "PROPERTY_TYPE",
        "work_class": "SUB_CATEGORY",
        "address_number": "STREET_NO",
        "address": "STREET",
        "city": "CITY",
        "state": "STATE",
        "issued_date": "START_DATE",
    }
    counties = [
        ("butler-county-oh-new-construction", "Butler County", "OH", "BUTLER COUNTY"),
        ("allen-county-in-new-construction", "Allen County", "IN", "ALLEN COUNTY-FORT WAYNE"),
        ("loudoun-county-va-new-construction", "Loudoun County", "VA", "LOUDOUN COUNTY"),
        ("pasco-county-fl-new-construction", "Pasco County", "FL", "PASCO COUNTY"),
        ("charlotte-county-fl-new-construction", "Charlotte County", "FL", "CHARLOTTE COUNTY"),
    ]
    return [
        ArcGISPermitConfig(
            source_id=source_id,
            layer_url=layer_url,
            source_url=source_url,
            source_name=source_name,
            jurisdiction=county,
            county=county.replace(" County", ""),
            state=state,
            default_city="Unknown",
            date_field="START_DATE",
            page_size=500,
            max_records=500,
            return_geometry=True,
            allow_unvalued_commercial=True,
            where_clause=(
                f"STATE = '{state}' AND JURISDICTION = '{publisher_jurisdiction}' "
                "AND PROPERTY_TYPE = 'commercial' "
                "AND CONTRACTOR_NAME IS NOT NULL "
                "AND STATUS IN ('active', 'in_review')"
            ),
            fields=dict(fields),
        )
        for source_id, county, state, publisher_jurisdiction in counties
    ]
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
    """Researched Northern Kentucky sources awaiting authorized data access."""
    return [
        UnverifiedCountyAdapter(
            "boone-county-ky-permits",
            "Boone County, Kentucky",
            "https://www.boonecountyky.org/departments/building_department/index.php",
            (
                "the official Oracle portal is authenticated and its monthly "
                "reports contain aggregates rather than project-level records; "
                "an authorized commercial-purpose export is required"
            ),
        ),
        UnverifiedCountyAdapter(
            "kenton-county-ky-permits",
            "Kenton County, Kentucky",
            "https://pdskc.govbuilt.com/ActivitySearchTool",
            (
                "the public GovBuilt activity search is licensed for personal "
                "use and its terms prohibit copying, republishing, and "
                "redistribution; written permission or an authorized county "
                "export is required"
            ),
        ),
        UnverifiedCountyAdapter(
            "campbell-county-ky-permits",
            "Campbell County, Kentucky",
            "https://co-campbell-ky.smartgovcommunity.com/ApplicationPublic/ApplicationSearchAdvanced",
            (
                "SmartGov provides human permit search but no authorized bulk "
                "feed was verified, and Campbell County requires commercial-use "
                "disclosure and may require a records contract"
            ),
        ),
    ]


def ohio_kentucky_expansion_scaffolds():
    """Researched regional sources that are not safe current-lead feeds yet."""
    return [
        UnverifiedCountyAdapter(
            "lexington-fayette-ky-permits",
            "Lexington-Fayette County, Kentucky",
            "https://www.lexingtonky.gov/working/development-records",
            (
                "the official AgencyCounter portal supports public record lookup, "
                "but no authoritative bulk/API feed or automated-access terms have "
                "been verified"
            ),
        ),
        UnverifiedCountyAdapter(
            "cuyahoga-county-high-value-construction",
            "Cuyahoga County, Ohio",
            "https://services8.arcgis.com/1cKSe8lh4duMZ8W0/ArcGIS/rest/services/DeltaTrack_All/FeatureServer/0",
            (
                "the official DeltaTrack layer is a historical high-value new-"
                "construction dataset covering 2012-2025, not a current permit feed; "
                "City of Cleveland permits are already enabled separately"
            ),
        ),
        UnverifiedCountyAdapter(
            "bowling-green-warren-ky-permits",
            "Bowling Green-Warren County, Kentucky",
            "https://www.bgky.org/ncs/building",
            (
                "the public GIS layer contains construction inspections rather than "
                "permit opportunities and does not publish the required project, "
                "valuation, address, and contractor fields"
            ),
        ),
        UnverifiedCountyAdapter(
            "toledo-oh-building-permits",
            "Toledo, Ohio",
            "https://toledo.oh.gov/business/how-to-build-in-the-city/permits",
            (
                "the available official ArcGIS permit dataset ends in March 2023 and "
                "would misrepresent historical records as current opportunities"
            ),
        ),
        UnverifiedCountyAdapter(
            "dayton-oh-building-permits",
            "Dayton, Ohio",
            "https://daytonohio.gov/201/Online-Permit-System",
            (
                "the official portal is a record-status search rather than a bulk "
                "feed, and the City states that commercial use requires prior written "
                "permission"
            ),
        ),
    ]
