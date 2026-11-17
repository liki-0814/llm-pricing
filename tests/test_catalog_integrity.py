import copy
import json
import pathlib
import sys
import tempfile
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import catalog_diff as c


class CatalogIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.scopes = {"version":1,"scopes":[{"vendor":"Vendor","channel":"native","modalities":["text"],"official_hosts":["official.invalid"]}]}
        self.db = {"models": [{"vendor": "Vendor", "billing": {"channel": "native"}, "model_id": "known-v1"}]}
        self.snap = {"vendor": "Vendor", "channel": "native", "complete": True, "errors": [],
            "source_url": "https://official.invalid/catalog", "observed_at": "2026-11-17T12:00:00Z",
            "fetch_status": "ok", "extraction_status": "ok", "coverage_evidence": {
                "enumeration_verified": True, "pagination_complete": True, "native_identity_verified": True,
                "source_url": "https://official.invalid/catalog", "expected_record_count": 1, "modalities":["text"]},
            "records": [{"model_id": "known-v1", "api_id_explicit": True}]}

    def compare(self, snap=None):
        return c.compare_catalogs(self.db, [self.snap if snap is None else snap], scopes=self.scopes)

    def test_complete_current_catalog_without_history_is_valid_first_baseline(self):
        result = self.compare()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["historical_comparison"], "no_previous_successful_snapshot")
        self.assertEqual(result["discovery_verdict"], "no_untracked_ids_in_verified_scope")

    def test_failed_partial_empty_invalid_and_unproven_never_claim_no_additions(self):
        variants = []
        for key, value in [("fetch_status", "failed"), ("extraction_status", "failed"),
                           ("complete", False), ("records", []),
                           ("records", [{"model_id": "Display Name", "api_id_explicit": False}]),
                           ("records", [None]), ("errors", ["HTTP failed"])]:
            s = copy.deepcopy(self.snap); s[key] = value; variants.append(s)
        for key, value in [("pagination_complete", False), ("enumeration_verified", False),
                           ("expected_record_count", 2), ("expected_record_count", True), ("source_url", None)]:
            s=copy.deepcopy(self.snap);s["coverage_evidence"][key]=value;variants.append(s)
        s=copy.deepcopy(self.snap);s.pop("coverage_evidence");variants.append(s)
        for s in variants:
            with self.subTest(snapshot=s):
                result=self.compare(s)
                self.assertEqual(result["status"], "incomplete")
                self.assertEqual(result["discovery_verdict"], "inconclusive_incomplete_coverage")
                self.assertFalse(result["vendor_coverage"][0]["complete"])

    def test_successful_subset_does_not_hide_missing_vendor_or_partial_source(self):
        db=copy.deepcopy(self.db);db["models"].append({"vendor":"Other", "billing":{"channel":"native"},"model_id":"other-v1"})
        scopes=copy.deepcopy(self.scopes);scopes["scopes"].append({"vendor":"Other","channel":"native","modalities":["text"],"official_hosts":["official.invalid"]})
        result=c.compare_catalogs(db,[self.snap],scopes=scopes);self.assertEqual(result["status"],"incomplete")
        self.assertEqual(result["missing_scopes"],[("Other","native","text")])
        partial=copy.deepcopy(self.snap);partial["complete"]=False
        result=c.compare_catalogs(self.db,[self.snap,partial],scopes=self.scopes)
        self.assertFalse(result["vendor_coverage"][0]["complete"])

    def test_first_baseline_advances_on_success_only_latest_failure_stays_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(c.previous_success(directory))
            good=self.compare();first=c.save_attempt(directory,good)
            self.assertEqual(c.previous_success(directory)["status"],"complete")
            failed=copy.deepcopy(self.snap);failed["extraction_status"]="failed"
            second=c.save_attempt(directory,self.compare(failed))
            self.assertNotEqual(first,second)
            self.assertEqual(c.previous_success(directory)["status"],"complete")
            latest=json.loads((pathlib.Path(directory)/"latest-attempt.json").read_text())
            self.assertEqual(latest["status"],"incomplete")
            self.assertTrue(first.exists() and second.exists())

    def test_generic_ids_not_whitelist_and_no_retirement_by_absence(self):
        self.snap["records"][0]["model_id"]="unannounced-future-family-12"
        result=self.compare()
        self.assertEqual(result["not_in_database"][0]["model_id"],"unannounced-future-family-12")
        self.assertEqual(c.extract_explicit_ids("Model invocation ID: `hy4`\nModel invocation ID: `future9`")[1]["model_id"],"future9")
        self.assertNotIn("retirements",result)

    def test_horizontal_first_party_ids_do_not_leak_partner_rows_or_guess_punctuation(self):
        text="| Feature | Model 1.5 | Future 9 |\n| Claude API ID | `model-1-5` | `future9` |\n| Amazon Bedrock ID | `partner.model-1-5` | `partner.future9` |"
        rows=c.extract_horizontal_identities(text,"Claude API ID")
        self.assertEqual([r["model_id"] for r in rows],["model-1-5","future9"])
        self.assertEqual(rows[0]["display_name"],"Model 1.5")

    def test_alias_conflicts_and_cycles_fail_instead_of_collapsing_entities(self):
        base={"vendor":"Vendor","channel":"native","source_url":"https://official.invalid/map","evidence_quote":"official a maps to b"}
        for aliases in [[dict(base,alias="a",canonical="b"),dict(base,alias="a",canonical="c")],
                        [dict(base,alias="a",canonical="b"),dict(base,alias="b",canonical="a")]]:
            with self.assertRaises(ValueError):c.compare_catalogs(self.db,[self.snap],aliases=aliases,scopes=self.scopes)
