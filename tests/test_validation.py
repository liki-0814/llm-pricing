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

    def test_openai_12h_cache_write_rules(self):
        m = self.model('gpt-5.6-sol')
        self.assertEqual((m['cache_pricing']['explicit_write_12h'], m['pricing_tiers'][0]['cache_pricing']['explicit_write_12h']), (10.0, 20.0))
        self.assertIsNone(m['cache_pricing']['explicit_write_1h'])
        for mutate in (lambda m: m['pricing_tiers'][0].update(cache_pricing=None),
                       lambda m: m['cache_pricing'].update(explicit_write_12h=1.0),
                       lambda m: m['service_tiers'][0]['multipliers'].update(explicit_write_12h=None),
                       lambda m: m['pricing_tiers'][0]['cache_pricing'].update(explicit_write=9.0)):
            d = copy.deepcopy(self.data)
            mutate(next(x for x in d['models'] if x['model_id'] == 'gpt-5.6-sol'))
            self.assertTrue(validate.validate_data(d))

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


    # ---- image / video models ----
    def invalid(self, mid, mutate):
        d = copy.deepcopy(self.data)
        mutate(next(x for x in d['models'] if x['model_id'] == mid))
        return validate.validate_data(d)

    def test_modality_counts_and_required_field(self):
        counts = {}
        for m in self.data['models']:
            counts[m['modality']] = counts.get(m['modality'], 0) + 1
        self.assertEqual(counts, {'text': 49, 'image': 12, 'video': 9})
        self.assertTrue(all(m.get('media_pricing') is None for m in self.data['models'] if m['modality'] == 'text'))
        self.assertTrue(self.invalid('grok-4.7', lambda m: m.pop('modality')))
        self.assertTrue(self.invalid('grok-4.7', lambda m: m.update(modality='audio')))
        # a text model may not carry media pricing, and a media model must
        self.assertTrue(self.invalid('grok-4.7', lambda m: m.update(media_pricing=copy.deepcopy(self.model('grok-imagine-image-2.0')['media_pricing']))))
        self.assertTrue(self.invalid('grok-imagine-image-2.0', lambda m: m.update(media_pricing=None)))

    def test_media_models_use_neutral_text_fields(self):
        files = build_api.build(self.data)
        for mid in ('grok-imagine-image-2.0', 'gpt-image-2.5-flare', 'wan3.0-video'):
            m = files['models/%s.json' % mid]['data']
            self.assertEqual(m['unit'], 'see_media_pricing')
            self.assertTrue(all(v is None for v in m['pricing'].values()))
            self.assertTrue(all(v == 'not_applicable' for v in m['pricing_status'].values()))
            self.assertIsNotNone(m['media_pricing'])
        self.assertIsNone(files['models/grok-4.7.json']['data']['media_pricing'])
        self.assertEqual(files['models.json']['meta']['modality_counts'], {'text': 49, 'image': 12, 'video': 9})
        for k in ('text', 'image', 'video'):
            self.assertTrue(all(o['modality'] == k for o in files['modalities/%s.json' % k]['data']))

    def test_unverified_media_fields_are_listed(self):
        gpt = self.model('gpt-image-2.5-flare')
        self.assertEqual(gpt['media_pricing']['image_prices'], [])
        self.assertIn('media_pricing.image_prices', gpt['unverified_fields'])
        omni = self.model('gemini-omni-1.1-flash')
        self.assertIn('media_pricing.video_prices.1080p.any.standard', omni['unverified_fields'])
        self.assertTrue(self.invalid('gemini-omni-1.1-flash', lambda m: m['unverified_fields'].remove('media_pricing.video_prices.1080p.any.standard')))
        # a null price that is not listed as unverified must be rejected
        self.assertTrue(self.invalid('grok-imagine-image-2.0', lambda m: m['media_pricing']['image_prices'][0].update(price=None)))

    def test_invalid_media_prices_rejected(self):
        self.assertTrue(self.invalid('grok-imagine-image-2.0', lambda m: m['media_pricing']['image_prices'][0].update(price=-1)))
        self.assertTrue(self.invalid('grok-imagine-image-2.0', lambda m: m['media_pricing']['image_prices'][0].update(price='0.04')))
        self.assertTrue(self.invalid('grok-imagine-video-1.5', lambda m: m['media_pricing']['video_prices'][0].update(price_per_second=True)))
        self.assertTrue(self.invalid('grok-imagine-video-1.5', lambda m: m['media_pricing'].update(input_image_price=-0.01)))
        self.assertTrue(self.invalid('gpt-image-2.5-flare', lambda m: m['media_pricing']['token_pricing']['standard'].update(image_output=-1)))
        self.assertTrue(self.invalid('grok-imagine-video-1.5', lambda m: m['media_pricing'].update(output_kind='image')))
        self.assertTrue(self.invalid('grok-imagine-video-1.5', lambda m: m['price_basis'].update(type='reference')))

    def test_duplicate_and_conflicting_media_rows_rejected(self):
        self.assertTrue(self.invalid('grok-imagine-image-2.0', lambda m: m['media_pricing']['image_prices'].append(copy.deepcopy(m['media_pricing']['image_prices'][0]))))
        self.assertTrue(self.invalid('grok-imagine-video-1.5', lambda m: m['media_pricing']['video_prices'].append(copy.deepcopy(m['media_pricing']['video_prices'][0]))))
        def mix_audio(m):
            e = copy.deepcopy(m['media_pricing']['video_prices'][0]); e['audio'] = 'with_audio'
            m['media_pricing']['video_prices'].append(e)
        self.assertTrue(self.invalid('grok-imagine-video-1.5', mix_audio))
        self.assertTrue(self.invalid('grok-imagine-image-2.0', lambda m: m['media_pricing']['video_prices'].append(copy.deepcopy(self.model('grok-imagine-video-1.5')['media_pricing']['video_prices'][0]))))
        self.assertTrue(self.invalid('wan3.0-video', lambda m: m['media_pricing']['video_prices'].append(dict(copy.deepcopy(m['media_pricing']['video_prices'][0]), tier='batch'))))

    def test_token_equivalent_price_must_match_token_rate(self):
        banana = self.model('gemini-nano-banana-2.1')
        row = next(e for e in banana['media_pricing']['image_prices'] if e['tier'] == 'standard' and e['size'] == '1k')
        self.assertAlmostEqual(row['price'], row['tokens'] * banana['media_pricing']['token_pricing']['standard']['image_output'] / 1e6, places=4)
        def bad(m):
            next(e for e in m['media_pricing']['image_prices'] if e['tier'] == 'standard' and e['size'] == '1k')['price'] = 0.05
        self.assertTrue(self.invalid('gemini-nano-banana-2.1', bad))
        self.assertTrue(self.invalid('gemini-nano-banana-2.1', lambda m: m['media_pricing'].update(token_pricing=None)))

    def test_media_sources_and_promotion(self):
        self.assertTrue(self.invalid('grok-imagine-image-2.0', lambda m: m['media_pricing'].update(sources=[])))
        wan = self.model('wan3.0-video')
        self.assertEqual(wan['media_pricing']['promotion']['discount_percent'], 30)
        self.assertEqual(wan['media_pricing']['video_prices'][1]['price_per_second'], 0.1)  # list price; discount not applied
        self.assertTrue(self.invalid('wan3.0-video', lambda m: m['media_pricing']['promotion'].update(effective_until='2026-01-01')))

    def test_stale_or_missing_modality_files_detected(self):
        files = build_api.build(self.data)
        files['modalities/image.json']['data'].pop()
        self.assertTrue(validate.validate_api(self.data, files))
        files = build_api.build(self.data)
        files['modalities/video.json']['data'][0]['modality'] = 'image'
        self.assertTrue(validate.validate_api(self.data, files))
        files = build_api.build(self.data)
        files['models.json']['data'][0]['modality'] = 'video'
        self.assertTrue(validate.validate_api(self.data, files))


if __name__ == '__main__':
    unittest.main()
