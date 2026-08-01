import unittest
from unittest.mock import patch

from permit_schema import PermitValidationError, SCHEMA_VERSION, validate_project
from source_adapters import (
    AdapterResult,
    ColumbusBuildingPermitsAdapter,
    ConfigurableArcGISPermitAdapter,
    LouisvilleJeffersonAdapter,
    UnverifiedCountyAdapter,
    additional_city_configs,
    run_adapters,
)
import scraper


def valid_project():
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": "source:permit-1",
        "source_id": "source",
        "permit_number": "permit-1",
        "project": "Example",
        "county": "Hamilton",
        "state": "OH",
        "source": "Example source",
        "source_url": "https://example.test",
        "contractors": [
            {
                "name": "Builder LLC",
                "role": "contractor",
                "source": "Example source",
                "source_field": "company",
            }
        ],
    }


class SchemaTests(unittest.TestCase):
    def test_valid_project(self):
        project = valid_project()
        self.assertIs(validate_project(project), project)

    def test_requires_source_qualified_id(self):
        project = valid_project()
        project["record_id"] = "permit-1"
        with self.assertRaises(PermitValidationError):
            validate_project(project)

    def test_requires_contractor_provenance(self):
        project = valid_project()
        del project["contractors"][0]["source_field"]
        with self.assertRaises(PermitValidationError):
            validate_project(project)


class AdapterTests(unittest.TestCase):
    def test_ten_additional_city_configs_are_unique_and_mapped(self):
        configs = additional_city_configs()
        self.assertEqual(len(configs), 10)
        self.assertEqual(len({config.source_id for config in configs}), 10)
        for config in configs:
            self.assertTrue(config.layer_url.startswith("https://"))
            self.assertTrue(config.source_url.startswith("https://"))
            self.assertIn("permit_number", config.fields)

    def test_configured_city_keeps_contact_roles_truthful(self):
        config = next(c for c in additional_city_configs() if c.jurisdiction == "Tempe")
        adapter = ConfigurableArcGISPermitAdapter(
            scraper.is_relevant, scraper.classify_market, scraper.electrical_score,
            scraper.parse_money, scraper.format_money, config=config,
        )
        project = adapter.normalize_record({
            "PermitNum": "BP-1", "PermitTypeDesc": "Commercial Building",
            "StatusCurrent": "Issued", "ContractorCompanyName": "Builder LLC",
            "PermitClass": "Office", "Description": "New construction",
            "EstProjectCost": 900000, "OriginalAddress1": "1 Mill Ave",
            "IssuedDateDtm": 1782864000000,
        })
        self.assertEqual(project["contractor"], "Builder LLC")
        self.assertEqual(project["contractors"][0]["source_field"], "ContractorCompanyName")
        self.assertEqual(project["record_id"], "tempe-building-permits:BP-1")

    def louisville_adapter(self):
        return LouisvilleJeffersonAdapter(
            scraper.is_relevant,
            scraper.classify_market,
            scraper.electrical_score,
            scraper.parse_money,
            scraper.format_money,
        )

    def columbus_adapter(self):
        return ColumbusBuildingPermitsAdapter(
            scraper.is_relevant,
            scraper.classify_market,
            scraper.electrical_score,
            scraper.parse_money,
            scraper.format_money,
        )

    def test_louisville_matches_dashboard_schema_and_contractor_provenance(self):
        project = self.louisville_adapter().normalize_record({
            "PERMIT_NUMBER": "BLD-2026-001",
            "PERMIT_TYPE": "Commercial Building",
            "PERMIT_STATUS": "Issued",
            "CONTRACTOR": "Louisville Builder LLC",
            "CATEGORY_NAME": "Office",
            "WORK_TYPE": "New Construction",
            "PROJECT_COSTS": 2500000,
            "ADDRESS": "100 Main St",
            "CITY": "Louisville",
            "STATE": "KY",
            "LATITUDE": 38.25,
            "LONGITUDE": -85.76,
            "ISSUE_DATE": 1782864000000,
        })
        self.assertEqual(project["county"], "Jefferson")
        self.assertEqual(project["contractor"], "Louisville Builder LLC")
        self.assertEqual(project["value"], "$2,500,000")
        self.assertEqual(
            project["record_id"],
            "louisville-metro-active-construction-permits:BLD-2026-001",
        )
        self.assertEqual(project["contractors"][0]["source_field"], "CONTRACTOR")

    def test_louisville_does_not_guess_missing_contractor(self):
        project = self.louisville_adapter().normalize_record({
            "PERMIT_NUMBER": "BLD-2026-002",
            "PERMIT_TYPE": "Commercial Building",
            "WORK_TYPE": "Renovation",
            "PROJECT_COSTS": 500000,
            "ADDRESS": "200 Main St",
        })
        self.assertEqual(project["contractor"], "Unknown")
        self.assertEqual(project["contractors"], [])

    def test_columbus_uses_geometry_and_does_not_promote_applicant_to_contractor(self):
        project = self.columbus_adapter().normalize_record({
            "B1_ALT_ID": "ALTC2523456",
            "GENERAL_TYPE": "Commercial New Building",
            "PERMIT_STATUS": "Permit Issued",
            "B1_PER_SUB_TYPE": "New Construction",
            "VALUE_DESC": "Office Building",
            "G3_VALUE_TTL": 4000000,
            "SITE_ADDRESS": "100 HIGH ST",
            "ISSUED_DT": 1782864000000,
            "ACA_URL": "https://ca.columbus.gov/example",
            "APPLICANT_BUS_NAME": "Applicant Design LLC",
            "_geometry_x": -82.99,
            "_geometry_y": 39.96,
        })
        self.assertEqual(project["jurisdiction"], "Columbus")
        self.assertEqual(project["county"], "Unknown")
        self.assertEqual(project["latitude"], 39.96)
        self.assertEqual(project["longitude"], -82.99)
        self.assertEqual(project["contractor"], "Unknown")
        self.assertEqual(project["contractors"], [])
        self.assertEqual(project["applicant"], "Applicant Design LLC")
        self.assertEqual(project["applicant_source"], "City of Columbus Building Permits")

    def test_arcgis_adapter_rejects_missing_source_id_field(self):
        with self.assertRaisesRegex(ValueError, "missing its permit number"):
            self.columbus_adapter().normalize_record({"SITE_ADDRESS": "100 HIGH ST"})

    @patch("scraper.geocode_address", return_value=(39.1, -84.5))
    def test_cincinnati_normalization_preserves_dashboard_and_provenance(self, _):
        record = {
            "permitnum": "2026P0001",
            "description": "Commercial renovation",
            "originaladdress1": "1 Main St",
            "originalcity": "Cincinnati",
            "originalstate": "OH",
            "companyname": "General Builder LLC",
            "issueddate": "2026-07-01T00:00:00",
            "estprojectcostdec": "500000",
        }
        project = scraper.normalize(
            record, {"2026P0001": ["Electrical Trade LLC"]}, {}
        )
        self.assertEqual(project["contractor"], "General Builder LLC")
        self.assertEqual(project["county"], "Hamilton")
        self.assertEqual(project["record_id"], "cincinnati-building-permits:2026P0001")
        self.assertEqual(
            {contractor["name"] for contractor in project["contractors"]},
            {"General Builder LLC", "Electrical Trade LLC"},
        )

    def test_one_source_failure_does_not_block_another(self):
        class Broken:
            source_id = "broken"

            def run(self, cache):
                raise RuntimeError("offline")

        class Working:
            source_id = "working"

            def run(self, cache):
                return AdapterResult(self.source_id, "success", [valid_project()])

        results = run_adapters([Broken(), Working()], {})
        self.assertEqual([result.status for result in results], ["failed", "success"])
        self.assertEqual(len(results[1].projects), 1)

    def test_unverified_adapter_never_fetches(self):
        adapter = UnverifiedCountyAdapter(
            "county", "County", "https://example.test", "access not verified"
        )
        result = adapter.run({})
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.projects, [])


if __name__ == "__main__":
    unittest.main()
