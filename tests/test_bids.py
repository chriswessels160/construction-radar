import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from bids import (
    BID_SOURCES,
    classify_bid,
    parse_bids,
    parse_bonfire_bids,
    parse_civicplus_bids,
    parse_florence_bids,
    fetch_bids,
    parse_open_bids,
    parse_opengov_bids,
)


HTML = """
<table id="projects"><tbody>
<tr data-docid="27E" data-doccd="ITB" data-deptid="1">
<td>27E</td><td>Accepting Bids</td><td>Fire Station Electrical Upgrade</td>
<td>Public Services</td><td>Buyer Name</td><td>Invitation to Bid</td>
<td>MBE 5%</td><td>08/20/2026 12:00 PM</td><td></td><td>View Attachments</td>
</tr>
<tr><td>OLD</td><td>Awarded</td><td>Closed Work</td><td>Water</td><td>A</td>
<td>ITB</td><td></td><td>08/20/2026 12:00 PM</td><td>Winner</td><td></td></tr>
<tr><td>EXPIRED</td><td>Accepting Bids</td><td>Old Work</td><td>Water</td><td>A</td>
<td>ITB</td><td></td><td>07/20/2026 12:00 PM</td><td></td><td></td></tr>
</tbody></table>
"""


class BidTests(unittest.TestCase):
    def test_only_future_accepting_bids_are_emitted(self):
        bids = parse_open_bids(
            HTML, now=datetime(2026, 8, 5, tzinfo=timezone.utc)
        )
        self.assertEqual(len(bids), 1)
        self.assertEqual(
            bids[0]["record_id"], "cincinnati-business-opportunities:27E"
        )
        self.assertEqual(bids[0]["match_type"], "Electrical match")
        self.assertEqual(bids[0]["document_code"], "ITB")

    def test_full_history_preserves_status_and_award(self):
        bids = parse_bids(
            HTML, now=datetime(2026, 8, 5, tzinfo=timezone.utc)
        )
        self.assertEqual(len(bids), 3)
        awarded = next(bid for bid in bids if bid["bid_number"] == "OLD")
        self.assertEqual(awarded["status"], "Awarded")
        self.assertEqual(awarded["awarded_contractor"], "Winner")
        self.assertFalse(awarded["is_open"])

    def test_trade_classification_does_not_claim_hidden_scope(self):
        self.assertEqual(classify_bid("Office supplies", "Procurement"), "Other public bid")
        self.assertEqual(classify_bid("Roof Replacement", "Public Services"), "Construction match")

    def test_civicplus_records_keep_official_detail_link(self):
        source = next(item for item in BID_SOURCES if item["source_id"] == "nky-sd1-bids")
        source_html = """
        <div class="listItemsRow bid"><div class="bidTitle">
        <span><a href="bids.aspx?bidID=241">Tunnel Inspection</a></span><br>
        <span><strong>Bid No.</strong> 26-026</span></div>
        <div class="bidStatus"><div><span>Status:</span><span>Closes:</span></div>
        <div><span>Open</span><span>8/30/2026 2:00 PM</span></div></div></div>
        <script></script>
        """
        bids = parse_civicplus_bids(source_html, source, datetime(2026, 8, 5, tzinfo=timezone.utc))
        self.assertEqual(len(bids), 1)
        self.assertTrue(bids[0]["is_open"])
        self.assertEqual(bids[0]["bid_number"], "26-026")
        self.assertTrue(bids[0]["source_url"].endswith("bids.aspx?bidID=241"))

    def test_florence_parser_separates_current_and_history(self):
        source = next(item for item in BID_SOURCES if item["source_id"] == "florence-ky-bids")
        source_html = """
        <h3>Current Bid Solicitations</h3><table><tr><td>Lighting Renovation</td><td>8-30-26</td><td><a href="notice.pdf">AD</a></td></tr></table>
        <h3>Inactive/Prior Bid Solicitations</h3><table><tr><td>Old Roof Work</td><td>7-1-26</td><td>6-1-26</td></tr></table>
        Property Tax Info
        """
        bids = parse_florence_bids(source_html, source, datetime(2026, 8, 5, tzinfo=timezone.utc))
        self.assertEqual(len(bids), 2)
        self.assertTrue(bids[0]["is_open"])
        self.assertEqual(bids[1]["status"], "Closed")

    def test_bonfire_public_payload_maps_covington(self):
        source = next(item for item in BID_SOURCES if item["source_id"] == "covington-ky-bids")
        payload = '{"payload":{"projects":{"1":{"ProjectID":"1","PrivateProjectID":"abc","ReferenceID":"RFP1","ProjectName":"Band Shell Rehabilitation","DateClose":"2026-08-13 14:30:00"}}}}'
        bids = parse_bonfire_bids(payload, source, datetime(2026, 8, 5, tzinfo=timezone.utc))
        self.assertEqual(bids[0]["record_id"], "covington-ky-bids:1")
        self.assertTrue(bids[0]["is_open"])

    def test_opengov_embedded_state_maps_source_qualified_id(self):
        source = next(item for item in BID_SOURCES if item["source_id"] == "cvg-airport-bids")
        state = {"portal": {"projects": [{"id": 7, "title": "Airfield Lighting", "status": "open", "proposalDeadline": "2026-09-01T18:00:00Z", "financialId": "CVG-7", "government": {"code": "cvgairport"}, "department": {"name": "Planning"}, "template": {"title": "Invitation to Bid"}}]}}
        source_html = "<script>window.__data=" + __import__("json").dumps(state) + ";</script>"
        bids = parse_opengov_bids(source_html, source, datetime(2026, 8, 5, tzinfo=timezone.utc))
        self.assertEqual(bids[0]["record_id"], "cvg-airport-bids:7")
        self.assertEqual(bids[0]["match_type"], "Electrical match")
        self.assertTrue(bids[0]["is_open"])

    def test_source_failure_preserves_that_sources_prior_records(self):
        prior = {
            "record_id": "cincinnati-business-opportunities:prior",
            "source_id": "cincinnati-business-opportunities",
            "is_open": True,
        }
        with patch("bids.fetch_source", side_effect=OSError("offline")):
            bids, results = fetch_bids(previous_records=[prior])
        self.assertEqual(bids, [prior])
        self.assertEqual(results[0]["status"], "stale")
        self.assertEqual(results[0]["count"], 1)
        self.assertTrue(all(result["source_id"] != results[0]["source_id"] or result["status"] == "stale" for result in results))

    def test_opengov_sources_request_complete_public_page(self):
        sources = [source for source in BID_SOURCES if source["kind"] == "opengov"]
        self.assertEqual(len(sources), 2)
        self.assertTrue(all("limit=100" in source["fetch_url"] for source in sources))


if __name__ == "__main__":
    unittest.main()
