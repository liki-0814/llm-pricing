import copy
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import build_api
import build_site
import catalog_diff
import validate


class LifecycleCurrencyTests(unittest.TestCase):
    def setUp(self):
        self.data = build_api.load()

    def test_shared_cases_page_all_lists_detail_and_fingerprint(self):
        cases = json.loads((build_api.ROOT / "tests/fixtures/lifecycle-cases.json").read_text())
        for c in cases:
            if c["name"] == "timezone-unknown":
                # Invalid exact source metadata must be rejected, not published.
                continue
            with self.subTest(case=c["name"]):
                d = copy.deepcopy(self.data)
                m = next(m for m in d["models"] if m["model_id"] == "qwen4-max")
                m["lifecycle"] = c["lifecycle"]
                d["meta"]["availability_as_of"] = c["at"]
                self.assertEqual(validate.validate_data(d), [])
                files = build_api.build(d, mixed=True)
                detail = files["models/qwen4-max.json"]["data"]
                self.assertEqual(detail["availability"]["status"], c["status"])
                if not c["estimable"]:
                    self.assertTrue(all(x is None for x in detail["pricing"].values()))
                    self.assertEqual(detail["price_schedule"], [])
                    self.assertIsNone(detail["media_pricing"])
                for rel in ["models.json", "vendors/qwen.json", "modalities/text.json"]:
                    present = any(x["id"] == "qwen4-max" for x in files[rel]["data"])
                    self.assertEqual(present, c["estimable"])
                self.assertEqual(any(x["model_id"] == "qwen4-max" for x in build_api.page_data(d)["models"]), c["estimable"])
                self.assertEqual(validate.validate_api(d, files), [])
        before = copy.deepcopy(self.data)
        after = copy.deepcopy(self.data)
        before["meta"]["availability_as_of"] = "2026-11-17T12:00:00Z"
        after["meta"]["availability_as_of"] = "2026-11-17T12:00:01Z"
        self.assertNotEqual(build_api.base_meta(before)["data_version"], build_api.base_meta(after)["data_version"])

    def test_v2_schema_and_snapshot_sync(self):
        files = build_api.build(self.data, mixed=True)
        self.assertEqual(validate.validate_api(self.data, files), [])
        self.assertEqual(len(files["models.json"]["data"]), 75)
        self.assertEqual(len(files["vendors/tencent.json"]["data"]), 3)
        for rel, value in files.items():
            if rel != "openapi.json":
                self.assertEqual(value["meta"]["as_of"], self.data["meta"]["availability_as_of"])
                self.assertEqual(value["meta"]["data_version"], build_api.base_meta(self.data)["data_version"])
                self.assertEqual(value["api_version"], "v2")
                self.assertEqual(json.loads((build_api.ROOT / "api/v2" / rel).read_text()), value)
        page = json.loads((build_api.ROOT / "data/page-models.json").read_text())
        self.assertEqual(page, build_api.page_data(self.data))

    def test_unknown_currency_and_cross_currency_reference_fail_validation(self):
        for bad in ("JPY", None, "usd"):
            d = copy.deepcopy(self.data); d["models"][0]["currency"] = bad
            self.assertTrue(validate.validate_data(d))
        d = copy.deepcopy(self.data)
        next(m for m in d["models"] if m["model_id"] == "kimi-for-coding")["currency"] = "CNY"
        self.assertTrue(validate.validate_data(d))

    def test_exact_retirement_requires_official_precision_timezone(self):
        d = copy.deepcopy(self.data)
        m = next(m for m in d["models"] if m["model_id"] == "hy4-preview")
        m["lifecycle"]["retired_at"] = "2026-12-07T00:00:00"
        self.assertTrue(validate.validate_data(d))

    def test_complete_artifact_failure_never_publishes_partial_tree(self):
        with tempfile.TemporaryDirectory() as t:
            output = pathlib.Path(t) / "release"
            with self.assertRaises(RuntimeError):
                build_site.build_site(output, "2026-11-17T20:26:37+08:00", "fixture-sha", True)
            self.assertFalse(output.exists())
            meta = build_site.build_site(output, "2026-11-17T20:26:37+08:00", "fixture-sha")
            self.assertEqual(meta["source_commit"], "fixture-sha")
            self.assertTrue((output / "api/v2/models/hy4.json").exists())
            self.assertFalse((output / "data/prices.json").exists())
            old = (output / "deployment.json").read_bytes()
            with self.assertRaises(ValueError):
                build_site.build_site(output, "2026-12-02T00:00:00Z", "later-sha")
            self.assertEqual((output / "deployment.json").read_bytes(), old)

    def test_generator_only_cleans_managed_orphans(self):
        with tempfile.TemporaryDirectory() as t:
            output = pathlib.Path(t)
            (output / "old.json").write_text("generated old")
            (output / "unmanaged.json").write_text("must retain")
            (output / ".generated-files").write_text("old.json\n../outside.json\n")
            with mock.patch.object(build_api, "API_DIR", output), mock.patch.object(build_api, "build", return_value={"models.json": {}}), mock.patch.object(sys, "argv", ["build_api.py"]):
                # main prints a root-relative output; keep temp path under ROOT for this exercise.
                with mock.patch.object(build_api, "ROOT", output.parent):
                    build_api.main()
            self.assertFalse((output / "old.json").exists())
            self.assertEqual((output / "unmanaged.json").read_text(), "must retain")
            self.assertTrue((output / "models.json").exists())

    def test_invocation_ids_are_extracted_without_a_model_whitelist(self):
        text = "Model invocation ID (`model` parameter): `qwen4-max`\nModel invocation ID (`model` parameter): `future-vendor-model`"
        self.assertEqual([r["model_id"] for r in catalog_diff.extract_explicit_ids(text)], ["qwen4-max", "future-vendor-model"])
        self.assertEqual(catalog_diff.extract_explicit_ids("# Brand New Model Name"), [])

    def test_catalog_diff_is_not_a_whitelist_or_retirement_detector(self):
        snap = {"vendor": "阿里云 Qwen", "channel": "pay_as_you_go", "complete": False,
                "errors": ["incomplete"], "source_url": "https://example.org/catalog", "observed_at": "2026-11-17T20:00:00+08:00",
                "records": [{"model_id": x, "api_id_explicit": True, "price_public": False} for x in ("qwen4-next-unpriced", "QWEN4-NEXT-UNPRICED", "qwen3.8-max", "qwen3-8-max")]}
        prev = {"observations": [{"vendor": "阿里云 Qwen", "channel": "pay_as_you_go", "model_id": "qwen-old"}]}
        result = catalog_diff.compare_catalogs(self.data, [snap], prev)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(len(result["observations"]), 3)
        self.assertEqual({x["model_id"] for x in result["not_in_database"]}, {"qwen4-next-unpriced", "qwen3-8-max"})
        self.assertTrue(result["not_observed_this_run_not_retired"])
        mapped = catalog_diff.compare_catalogs(self.data, [snap], aliases=[{"vendor": "阿里云 Qwen", "channel": "pay_as_you_go", "alias": "qwen3-8-max", "canonical": "qwen3.8-max", "source_url": "https://example.org/official-map"}])
        self.assertEqual(len(mapped["not_in_database"]), 1)

    def test_confirmed_retired_unknown_time_complete_artifact_and_observation_contract(self):
        cases=json.loads((build_api.ROOT / "tests/fixtures/lifecycle-cases.json").read_text())
        case=next(c for c in cases if c["name"]=="confirmed-retired-unknown-T-current")
        d=copy.deepcopy(self.data)
        model=next(m for m in d["models"] if m["model_id"]=="qwen4-max")
        model["lifecycle"]=case["lifecycle"]
        self.assertEqual(validate.validate_data(d),[])
        with tempfile.TemporaryDirectory() as t, mock.patch.object(build_api,"load",return_value=d):
            output=pathlib.Path(t)/"release"
            build_site.build_site(output,case["at"],"confirmed-retired-fixture")
            detail=json.loads((output/"api/v2/models/qwen4-max.json").read_text())["data"]
            self.assertEqual(detail["availability"]["status"],"retired")
            self.assertEqual(detail["lifecycle"]["routes_to"],"new-entity")
            self.assertTrue(all(v is None for v in detail["pricing"].values()))
            page=json.loads((output/"data/page-models.json").read_text())
            self.assertFalse(any(m["model_id"]=="qwen4-max" for m in page["models"]))
        model["lifecycle"]=dict(case["lifecycle"])
        model["lifecycle"].pop("observed_at")
        self.assertTrue(any("observed_at" in e for e in validate.validate_data(d)))

    def test_stale_generated_sdk_cannot_publish(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(build_site.build_sdk,"check",return_value=False):
            output=pathlib.Path(t)/"release"
            with self.assertRaisesRegex(ValueError,"SDK bundle stale"):
                build_site.build_site(output,"2026-11-17T12:26:37Z","fixture")
            self.assertFalse(output.exists())
