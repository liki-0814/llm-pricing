import copy
import pathlib
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import build_api
import validate


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.data = build_api.load()

    def model(self, mid):
        return next(m for m in self.data['models'] if m['model_id'] == mid)

    def test_current_data_and_all_response_schemas(self):
        self.assertEqual(validate.validate_data(self.data), [])
        self.assertEqual(validate.validate_api(self.data), [])
        self.assertEqual(build_api.check(self.data), [])

    def test_invalid_calendar_date(self):
        self.data['models'][0]['last_updated'] = '2026-02-31'
        self.assertTrue(validate.validate_data(self.data))

    def test_absent_output_cap_is_documented_not_unknown(self):
        m = self.model('grok-4.7')
        self.assertEqual(m['limits']['max_output_tokens'], 'n/a')
        m['limits']['note'] = None
        self.assertTrue(validate.validate_data(self.data))
        m['limits']['max_output_tokens'] = 'unlimited'
        self.assertTrue(validate.validate_data(self.data))

    def test_missing_price_marker(self):
        self.model('qwen3.8-omni-flash')['unverified_fields'] = []
        self.assertTrue(validate.validate_data(self.data))

    def test_overlapping_tiers(self):
        m = self.model('qwen3.7-flash')
        t = copy.deepcopy(m['pricing_tiers'][0]); t['input_tokens_gt'] = 33000
        t['condition'] = 'input_tokens>33000 and input_tokens<=256000'
        m['pricing_tiers'].append(t)
        self.assertTrue(validate.validate_data(self.data))

    def test_gap_and_condition_mismatch(self):
        m = self.model('qwen3.7-flash'); m['pricing_tiers'][1]['input_tokens_gt'] += 1
        self.assertTrue(validate.validate_data(self.data))

    def test_malformed_missing_and_removed_fields(self):
        for field, value in [('input', float('nan')), ('context_tokens', True), ('features', {})]:
            with self.subTest(field=field):
                d = copy.deepcopy(self.data); d['models'][0][field] = value
                self.assertTrue(validate.validate_data(d))
        del self.data['models'][0]['input']
        self.assertTrue(validate.validate_data(self.data))

    def test_unknown_reference_and_mismatched_reference_price(self):
        m = self.model('kimi-for-coding'); m['price_basis']['reference_model_id'] = 'unknown'
        self.assertTrue(validate.validate_data(self.data))
        m['price_basis']['reference_model_id'] = 'kimi-k2.7-code'; m['input'] = 100
        self.assertTrue(validate.validate_data(self.data))

    def test_documented_reference_multiplier_is_required_and_valid(self):
        m = self.model('grok-4.7-build-fast')
        self.assertEqual(m['price_basis']['reference_multiplier'], 2)
        self.assertEqual(validate.validate_data(self.data), [])
        del m['price_basis']['reference_multiplier']
        self.assertTrue(validate.validate_data(self.data))
        for bad in (0, -1, True, '2', float('inf'), 1.5):
            m['price_basis']['reference_multiplier'] = bad
            self.assertTrue(validate.validate_data(self.data), repr(bad))
        m['price_basis']['reference_multiplier'] = 2
        self.model('grok-4.7')['price_basis']['reference_multiplier'] = 1
        self.assertTrue(validate.validate_data(self.data))

    def test_wrong_response_status_and_type_rejected(self):
        files = build_api.build(self.data)
        files['models.json']['data'][0]['pricing_status']['input'] = 'fake'
        self.assertTrue(validate.validate_api(self.data, files))
        files = build_api.build(self.data); files['models.json']['data'][0]['pricing']['input'] = True
        self.assertTrue(validate.validate_api(self.data, files))

    def test_expired_or_reversed_schedule(self):
        e = self.model('gpt-5.6-sol')['price_schedule'][0]; e['effective_until'] = '2026-10-10'
        self.assertTrue(validate.validate_data(self.data))
        e['effective_until'] = '2026-12-01'; e['effective_from'] = '2026-12-02'
        self.assertTrue(validate.validate_data(self.data))

    def test_missing_schedule_start_and_ambiguous_tier_change(self):
        m = self.model('gemini-3.8-flash')
        e = copy.deepcopy(m['price_schedule'][0]); e['effective_from'] = None
        m['price_schedule'].append(e)
        self.assertTrue(validate.validate_data(self.data))
        m['price_schedule'].pop()
        e = self.model('gpt-5.6-sol')['price_schedule'][0]; e['input'] += 1
        self.assertTrue(validate.validate_data(self.data))

    def test_version_and_reference_status(self):
        files = build_api.build(self.data)
        versions = {v['meta']['data_version'] for k,v in files.items() if k != 'openapi.json'}
        self.assertEqual(len(versions), 1)
        self.assertEqual(files['models/kimi-for-coding.json']['data']['pricing_status']['input'], 'reference')
        self.assertEqual(files['models/gpt-6-astra.json']['data']['reasoning_effort']['status'], 'partial')
        self.assertEqual(files['models/kimi-k2.7-code.json']['data']['reasoning_effort']['field_status']['default'], 'not_applicable')


if __name__ == '__main__':
    unittest.main()
