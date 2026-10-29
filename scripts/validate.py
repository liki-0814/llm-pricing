#!/usr/bin/env python3
"""Validate source semantics, generated OpenAPI contracts and committed API files."""
import copy
import datetime as dt
import math
import pathlib
import sys

sys.dont_write_bytecode = True
import build_api
try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:
    raise SystemExit('Install validation dependencies: python3 -m pip install -r requirements-dev.txt')

PRICE_FIELDS = build_api.PRICE_FIELDS
REMOVED = {'modalities', 'features', 'knowledge_cutoff', 'thinking_budget', 'availability', 'snapshot', 'aliases'}


def source_schema(d):
    """Reuse the generated response contract without letting conversion hide missing keys."""
    spec = build_api.openapi(d, list(build_api.VENDOR_SLUGS.values()), [])
    schema = copy.deepcopy(spec['components']['schemas']['Model'])
    props = schema['properties']
    for field in ('api_version', 'unit', 'vendor_name', 'pricing', 'pricing_status', 'has_off_peak',
                  'off_peak_pricing', 'links', 'context_length_label', 'media_pricing'):
        props.pop(field, None)
    props['modality'] = {'const': 'text'}
    props['model_id'] = props.pop('id')
    props['model_id']['pattern'] = build_api.SLUG_RE.pattern
    props['id'] = {'type': 'string', 'minLength': 1}
    props['model'] = props.pop('name')
    props['vendor'] = {'enum': d.get('vendors', [])}
    props['context_length'] = {'type': ['string', 'null']}
    props['context_tokens'] = {'type': ['integer', 'null'], 'minimum': 1}
    for k in PRICE_FIELDS:
        props[k] = {'anyOf': [{'type': 'number', 'minimum': 0}, {'type': 'null'}, {'const': 'n/a'}]}
    props['offpeak'] = {'type': ['object', 'null'], 'required': list(build_api.OFFPEAK_FIELDS),
                        'properties': {k: {'type': 'number', 'minimum': 0} for k in build_api.OFFPEAK_FIELDS},
                        'additionalProperties': False}
    for name in ('limits', 'reasoning_effort'):
        for field in ('status', 'field_status'):
            props[name]['properties'].pop(field, None)
            if field in props[name]['required']:
                props[name]['required'].remove(field)
    props['limits']['properties']['max_output_tokens']['type'] = ['integer', 'null', 'string']
    props['limits']['properties']['max_output_tokens']['anyOf'] = [
        {'type': ['integer', 'null']}, {'const': 'n/a'}]
    props['unverified_fields']['uniqueItems'] = True
    schema['required'] = [k for k in props if k != 'offpeak']
    schema['components'] = spec['components']
    return schema


def media_source_schema(d):
    """Source contract for image / video models: no token-price, context, reasoning, limits or tier fields."""
    spec = build_api.openapi(d, list(build_api.VENDOR_SLUGS.values()), [])
    props = spec['components']['schemas']['Model']['properties']
    keep = ('currency', 'source_url', 'extra_sources', 'last_updated', 'notes', 'unverified_fields', 'price_basis', 'billing')
    out = {k: copy.deepcopy(props[k]) for k in keep}
    out['model_id'] = dict(copy.deepcopy(props['id']), pattern=build_api.SLUG_RE.pattern)
    out['id'] = {'type': 'string', 'minLength': 1}
    out['model'] = copy.deepcopy(props['name'])
    out['vendor'] = {'enum': d.get('vendors', [])}
    out['modality'] = {'enum': ['image', 'video']}
    out['media_pricing'] = {'$ref': '#/components/schemas/MediaPricing'}
    out['unverified_fields']['uniqueItems'] = True
    return {'type': 'object', 'required': list(out), 'properties': out, 'additionalProperties': False,
            'components': spec['components']}


def numeric(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0


def expected_unverified(m):
    missing = {k for k in PRICE_FIELDS if m.get(k) is None}
    missing |= {'limits.' + k for k in build_api.LIMIT_FIELDS if m['limits'][k] is None}
    r = m['reasoning_effort']
    missing |= {'reasoning_effort.' + k for k in ('supported', 'levels', 'default', 'can_disable')
                if r[k] is None and not (r['supported'] is False and k in ('levels', 'default'))}
    return missing


def expected_unverified_media(m):
    """Paths of media prices that are null, plus an empty price table for the model's own output kind."""
    mp = m['media_pricing']
    missing = set()
    if mp['output_kind'] == 'image' and not mp['image_prices']:
        missing.add('media_pricing.image_prices')
    if mp['output_kind'] == 'video' and not mp['video_prices']:
        missing.add('media_pricing.video_prices')
    for e in mp['image_prices']:
        if e['price'] is None:
            missing.add('media_pricing.image_prices.%s.%s.%s' % (e['size'], e['quality'] or 'default', e['tier']))
    for e in mp['video_prices']:
        if e['price_per_second'] is None:
            missing.add('media_pricing.video_prices.%s.%s.%s' % (e['resolution'], e['audio'], e['tier']))
    return missing


def validate_media(m, snapshot, fail):
    where = m['model_id']
    mp, kind = m['media_pricing'], m['modality']
    if mp['output_kind'] != kind:
        fail(where, 'media_pricing.output_kind must equal modality')
    if m['price_basis']['type'] != 'official' or m['price_basis']['reference_model_id'] is not None:
        fail(where, 'image / video prices must be official')
    if m['billing']['price_type'] == 'reference' or m['billing']['channel'] != 'pay_as_you_go':
        fail(where, 'image / video prices must be pay-as-you-go list prices')
    if m['source_url'] not in mp['sources']:
        fail(where, 'media_pricing.sources must include source_url')
    methods = set(mp['billing_methods'])
    if ('token' in methods) != (mp['token_pricing'] is not None):
        fail(where, 'billing_methods token must match token_pricing presence')
    if ('per_image' in methods) != bool(mp['image_prices']):
        fail(where, 'billing_methods per_image must match image_prices presence')
    if ('per_second' in methods) != bool(mp['video_prices']):
        fail(where, 'billing_methods per_second must match video_prices presence')
    if kind == 'image' and mp['video_prices'] or kind == 'video' and mp['image_prices']:
        fail(where, 'price table does not match output_kind')
    if kind == 'image' and (methods - {'token', 'per_image'}) or kind == 'video' and (methods - {'token', 'per_second'}):
        fail(where, 'billing_methods do not match output_kind')
    if set(m['unverified_fields']) != expected_unverified_media(m):
        fail(where, 'unverified_fields must equal ' + repr(sorted(expected_unverified_media(m))))
    tp = mp['token_pricing']
    for tier in ('standard', 'batch', 'priority'):
        prices = (tp or {}).get(tier)
        for k, v in (prices or {}).items():
            if v is not None and not numeric(v):
                fail(where, 'invalid token price %s.%s' % (tier, k))
    if tp is not None and tp['standard'] is None:
        fail(where, 'token_pricing requires standard prices')
    seen = set()
    for e in mp['image_prices']:
        key = (e['tier'], e['size'], e['quality'])
        if key in seen:
            fail(where, 'duplicate image price ' + repr(key))
        seen.add(key)
        if e['size'] != e['size'].lower():
            fail(where, 'image size labels must be lowercase')
    seen, audio = set(), {}
    for e in mp['video_prices']:
        key = (e['tier'], e['resolution'], e['audio'])
        if key in seen:
            fail(where, 'duplicate video price ' + repr(key))
        seen.add(key)
        audio.setdefault((e['tier'], e['resolution']), set()).add(e['audio'])
        if e['resolution'] != e['resolution'].lower():
            fail(where, 'video resolution labels must be lowercase')
    for k, a in audio.items():
        if 'any' in a and len(a) > 1:
            fail(where, 'audio "any" cannot coexist with with_audio/without_audio for %s' % (k,))
    # A documented token equivalence must match the token price within vendor rounding.
    for e, rate_key, price_key, count_key, tol in (
            [(e, 'image_output', 'price', 'tokens', 0.01) for e in mp['image_prices']] +
            [(e, 'video_output', 'price_per_second', 'tokens_per_second', 0.02) for e in mp['video_prices']]):
        count, price = e.get(count_key), e.get(price_key)
        rate = ((tp or {}).get(e['tier']) or {}).get(rate_key)
        if count is not None and tp is None:
            fail(where, count_key + ' requires token_pricing')
        elif count is not None and numeric(rate) and numeric(price) and not math.isclose(price, count * rate / 1e6, rel_tol=tol):
            fail(where, '%s %s x %s disagrees with listed price' % (count_key, count, rate_key))
    for e in mp['image_prices'] + mp['video_prices']:
        if e['basis'] in ('token_equivalent',) and tp is None:
            fail(where, 'token_equivalent prices require token_pricing')
    for k in ('input_image_price', 'input_image_price_batch'):
        if mp[k] is not None and not numeric(mp[k]):
            fail(where, 'invalid ' + k)
    for e in mp['video_prices']:
        if e['input_video_price_per_second'] is not None and not numeric(e['input_video_price_per_second']):
            fail(where, 'invalid input_video_price_per_second')
    if mp['batch_supported'] is False and any(e['tier'] == 'batch' for e in mp['image_prices'] + mp['video_prices']):
        fail(where, 'batch prices on a model without batch support')
    promo = mp['promotion']
    if promo and promo['effective_until'] and promo['effective_until'] < m['last_updated']:
        fail(where, 'expired promotion needs re-verification')


def validate_data(d):
    errors = []
    def fail(where, message):
        errors.append(where + ': ' + message)
    if not isinstance(d, dict) or not isinstance(d.get('models'), list) or not isinstance(d.get('vendors'), list):
        return ['dataset: models and vendors must be arrays']
    if not all(isinstance(v, str) for v in d['vendors']):
        return ['vendors: names must be strings']
    if not d['models'] or not d['vendors']:
        return ['dataset: models and vendors cannot be empty']
    def finite(value, where):
        if isinstance(value, float) and not math.isfinite(value):
            fail(where, 'numbers must be finite')
        elif isinstance(value, dict):
            for k, v in value.items():
                finite(v, where + '.' + k)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                finite(v, where + '[%d]' % i)
    finite(d, 'dataset')
    try:
        snapshot = dt.date.fromisoformat(d['meta']['last_updated'])
    except (KeyError, ValueError, TypeError):
        return ['meta.last_updated: invalid calendar date']
    if snapshot > dt.datetime.now(dt.timezone.utc).date():
        fail('meta.last_updated', 'verification date is in the future')
    if len(d['vendors']) != len(set(d['vendors'])):
        fail('vendors', 'duplicate vendor')
    for v in d['vendors']:
        if v not in build_api.VENDOR_SLUGS:
            fail('vendors', 'unknown vendor ' + str(v))
    validators = {'text': Draft202012Validator(source_schema(d), format_checker=FormatChecker()),
                  'media': Draft202012Validator(media_source_schema(d), format_checker=FormatChecker())}
    by_id, ids = {}, set()
    for i, m in enumerate(d['models']):
        where = 'models[%d]' % i
        if not isinstance(m, dict) or m.get('modality') not in build_api.MODALITIES:
            fail(where, 'modality must be one of ' + ', '.join(build_api.MODALITIES))
            continue
        validator = validators['text' if m['modality'] == 'text' else 'media']
        schema_errors = list(validator.iter_errors(m))
        for e in schema_errors:
            fail(where + '.' + '.'.join(map(str, e.path)), e.message)
        if schema_errors:
            continue
        where = m['model_id']
        for k in REMOVED:
            if k in m:
                fail(where, 'removed field ' + k)
        if m['id'] in ids or where in by_id:
            fail(where, 'duplicate identifier')
        ids.add(m['id']); by_id[where] = m
        if dt.date.fromisoformat(m['last_updated']) > snapshot:
            fail(where, 'model verification date is after dataset date')
        if m['modality'] != 'text':
            validate_media(m, snapshot, fail)
            continue
        if set(m['unverified_fields']) != expected_unverified(m):
            fail(where, 'unverified_fields must equal ' + repr(sorted(expected_unverified(m))))
        if m['limits']['context_length'] != m['context_tokens']:
            fail(where, 'limits.context_length != context_tokens')
        if (m['context_tokens'] is None) != (m['context_length'] is None):
            fail(where, 'context label and numeric value must both be null or present')
        L = m['limits']
        if L['max_output_tokens'] == 'n/a' and (not L['note'] or not L['sources']):
            fail(where, 'documented absent output cap requires note and sources')
        if numeric(L['max_output_tokens']) and L['context_length'] is not None and L['max_output_tokens'] > L['context_length']:
            fail(where, 'max output exceeds context')
        r = m['reasoning_effort']
        if r['supported'] is None and (r['levels'] is not None or r['default'] is not None):
            fail(where, 'unknown reasoning support with populated levels/default')
        if r['supported'] is False and (r['levels'] is not None or r['default'] is not None):
            fail(where, 'non-adjustable reasoning cannot have levels/default')
        if r['levels'] is not None and (not r['levels'] or len(set(r['levels'])) != len(r['levels'])):
            fail(where, 'empty or duplicate reasoning levels')
        if r['default'] is not None and r['levels'] is not None and r['default'] not in r['levels']:
            fail(where, 'reasoning default is not an accepted level')
        basis, bill = m['price_basis'], m['billing']
        if basis['type'] == 'reference':
            if not basis['reference_model_id'] or bill['price_type'] != 'reference':
                fail(where, 'reference price requires reference model and billing.price_type=reference')
        elif basis['reference_model_id'] is not None or bill['price_type'] == 'reference' or 'reference_multiplier' in basis:
            fail(where, 'official price cannot have a reference model/type')
        C = m['cache_pricing']
        for k in PRICE_FIELDS:
            if isinstance(m[k], (int, float)) and not numeric(m[k]):
                fail(where, 'nonfinite price ' + k)
        for label, cache in [('cache_pricing', C)] + [('tier.cache_pricing', t['cache_pricing']) for t in m['pricing_tiers'] if t['cache_pricing']]:
            for k, v in cache.items():
                if k != 'note' and v is not None and not numeric(v):
                    fail(where, 'invalid ' + label + '.' + k)
        for k, base in [('explicit_write', 'cache_write')]:
            if numeric(C[k]) and numeric(m[base]) and C[k] != m[base]:
                fail(where, 'cache write breakdown disagrees with base')
        for t in m['pricing_tiers']:
            tc = t['cache_pricing'] or {}
            if numeric(tc.get('explicit_write')) and numeric(t['cache_write']) and tc['explicit_write'] != t['cache_write']:
                fail(where, 'tier cache write breakdown disagrees with tier cache_write')
        # 12-hour TTL writes are a separate, longer-lived write rate; never a substitute for 1h or default writes.
        if numeric(C['explicit_write_12h']):
            if not numeric(C['explicit_write']) or C['explicit_write_12h'] < C['explicit_write']:
                fail(where, 'explicit_write_12h requires a default explicit_write no greater than it')
            for t in m['pricing_tiers']:
                tc = t['cache_pricing'] or {}
                # Without a tier value the estimator would silently reuse the short-context 12h rate.
                if numeric(t['cache_write']) and not numeric(tc.get('explicit_write_12h')):
                    fail(where, 'tiered model with explicit_write_12h needs tier cache_pricing.explicit_write_12h')
        for s in m['service_tiers']:
            if numeric(C['explicit_write_12h']) and s['multipliers']['explicit_write_12h'] is None and 'explicit_write_12h' not in s['pricing']:
                fail(where, 'service tier ' + s['name'] + ' lacks explicit_write_12h multiplier')
        ctype = bill['cached_input_type']
        if ctype != 'unspecified' and C[ctype + '_read'] != m['cached_input']:
            fail(where, 'cached_input_type disagrees with cache price')
        tiers = sorted(m['pricing_tiers'], key=lambda t: t['input_tokens_gt'])
        previous_end = None
        for j, t in enumerate(tiers):
            lo, hi = t['input_tokens_gt'], t['input_tokens_lte']
            condition = 'input_tokens>%d' % lo + (' and input_tokens<=%d' % hi if hi is not None else '')
            if t['condition'] != condition or (hi is not None and hi <= lo):
                fail(where, 'tier condition/bounds disagree')
            if j and (previous_end is None or lo != previous_end):
                fail(where, 'tier ranges overlap or have a gap')
            previous_end = hi
            if t['input'] is None or t['output'] is None:
                fail(where, 'tier needs input/output prices')
        if m.get('offpeak') is not None:
            if m['off_peak_schedule'] is None:
                fail(where, 'offpeak requires complete schedule')
            else:
                windows = sorted(m['off_peak_schedule']['peak_windows'], key=lambda w: w['start'])
                for j, w in enumerate(windows):
                    if w['start'] >= w['end'] or (j and windows[j-1]['end'] > w['start']):
                        fail(where, 'invalid or overlapping peak windows')
        elif m['off_peak_schedule'] is not None:
            fail(where, 'schedule without offpeak prices')
        names = [s['name'] for s in m['service_tiers']]
        if len(names) != len(set(names)):
            fail(where, 'duplicate service tier')
        for s in m['service_tiers']:
            if s['multipliers']['input'] != s['multiplier'] or s['multipliers']['output'] != s['multiplier']:
                fail(where, 'display multiplier must match input/output multipliers')
        schedules = m['price_schedule']
        starts = [e['effective_from'] for e in schedules if e['kind'] != 'promotion' and e['effective_from']]
        if starts != sorted(starts) or len(starts) != len(set(starts)):
            fail(where, 'scheduled changes must have unique chronological start dates')
        for e in m['price_schedule']:
            start, end = e['effective_from'], e['effective_until']
            if start and end and start > end:
                fail(where, 'price schedule ends before it starts')
            if e['kind'] != 'promotion' and not start:
                fail(where, 'scheduled price change requires effective_from')
            if e['kind'] == 'promotion' and end and end < m['last_updated']:
                fail(where, 'expired promotion needs re-verification')
            if tiers and e['multiplier'] is None and any(e[k] is not None and e[k] != m[k] for k in PRICE_FIELDS):
                fail(where, 'flat scheduled changes on tiered models need a documented tier multiplier')
    for mid, m in by_id.items():
        ref = m['price_basis']['reference_model_id']
        if ref is not None:
            target = by_id.get(ref)
            if not target or ref == mid or target['price_basis']['type'] != 'official':
                fail(mid, 'reference model must exist and have official prices')
            else:
                multiplier = m['price_basis'].get('reference_multiplier', 1)
                if any(not math.isclose(m[k], target[k] * multiplier, rel_tol=1e-12)
                       if numeric(m[k]) and numeric(target[k]) else m[k] != target[k]
                       for k in PRICE_FIELDS):
                    fail(mid, 'reference base prices disagree with reference model and documented multiplier')
    return errors


def validate_api(d, files=None):
    files = files or build_api.build(d)
    spec = files['openapi.json']
    errors = []
    for name, schema in spec['components']['schemas'].items():
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as e:
            errors.append('schema ' + name + ': ' + str(e))
    for rel, response in files.items():
        if rel == 'openapi.json':
            continue
        path = ('/models/{model_id}.json' if rel.startswith('models/') else '/vendors/{vendor}.json' if rel.startswith('vendors/')
                else '/modalities/{modality}.json' if rel.startswith('modalities/') else '/' + rel)
        schema = copy.deepcopy(spec['paths'][path]['get']['responses']['200']['content']['application/json']['schema'])
        schema['components'] = spec['components']
        for e in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(response):
            errors.append(rel + '.' + '.'.join(map(str, e.path)) + ': ' + e.message)
    for o in files['models.json']['data']:
        applicable = o['modality'] == 'text'
        if (o['media_pricing'] is None) != applicable:
            errors.append(o['id'] + ': media_pricing must be null for text models and present for image / video models')
        if not applicable and (any(v is not None for v in o['pricing'].values()) or
                               set(o['pricing_status'].values()) != {'not_applicable'}):
            errors.append(o['id'] + ': token price fields must be null / not_applicable on image / video models')
    for k in build_api.MODALITIES:
        f = files['modalities/%s.json' % k]
        if any(o['modality'] != k for o in f['data']) or [o['id'] for o in f['data']] != f['modality']['model_ids']:
            errors.append('modalities/%s.json: data does not match modality' % k)
    if sum(len(files['modalities/%s.json' % k]['data']) for k in build_api.MODALITIES) != len(files['models.json']['data']):
        errors.append('modalities: every model must belong to exactly one modality')
    return errors


def main():
    d = build_api.load()
    problems = validate_data(d)
    if not problems:
        problems += validate_api(d)
        problems += build_api.check(d)
    for problem in problems:
        print('BAD', problem)
    counts = {k: sum(1 for m in d['models'] if m.get('modality') == k) for k in build_api.MODALITIES}
    print('%d models (%s), %d problem(s)' % (len(d['models']), ', '.join('%s %d' % kv for kv in counts.items()), len(problems)))
    for m in d['models']:
        for k in m['unverified_fields']:
            print('unverified:', m['model_id'], k)
    print('api/v1: in sync and schema-valid' if not problems else 'validation FAILED')
    return bool(problems)


if __name__ == '__main__':
    sys.exit(main())
