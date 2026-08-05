import unittest
from datetime import datetime, timezone

from bids import classify_bid, parse_open_bids


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
        self.assertEqual(bids[0]["record_id"], "cincinnati-open-bids:27E")
        self.assertEqual(bids[0]["match_type"], "Electrical match")
        self.assertEqual(bids[0]["document_code"], "ITB")

    def test_trade_classification_does_not_claim_hidden_scope(self):
        self.assertEqual(classify_bid("Office supplies", "Procurement"), "Other city bid")
        self.assertEqual(classify_bid("Roof Replacement", "Public Services"), "Construction match")


if __name__ == "__main__":
    unittest.main()
