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
                  'off_peak_pricing', 'links', 'context_length_label'):
        props.pop(field, None)
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
    props['unverified_fields']['uniqueItems'] = True
    schema['required'] = [k for k in props if k != 'offpeak']
    schema['components'] = spec['components']
    return schema


def numeric(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0


def expected_unverified(m):
    missing = {k for k in PRICE_FIELDS if m.get(k) is None}
    missing |= {'limits.' + k for k in build_api.LIMIT_FIELDS if m['limits'][k] is None}
    r = m['reasoning_effort']
    missing |= {'reasoning_effort.' + k for k in ('supported', 'levels', 'default', 'can_disable')
                if r[k] is None and not (r['supported'] is False and k in ('levels', 'default'))}
    return missing


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
    validator = Draft202012Validator(source_schema(d), format_checker=FormatChecker())
    by_id, ids = {}, set()
    for i, m in enumerate(d['models']):
        where = 'models[%d]' % i
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
        if set(m['unverified_fields']) != expected_unverified(m):
            fail(where, 'unverified_fields must equal ' + repr(sorted(expected_unverified(m))))
        if m['limits']['context_length'] != m['context_tokens']:
            fail(where, 'limits.context_length != context_tokens')
        if (m['context_tokens'] is None) != (m['context_length'] is None):
            fail(where, 'context label and numeric value must both be null or present')
        L = m['limits']
        if L['max_output_tokens'] is not None and L['context_length'] is not None and L['max_output_tokens'] > L['context_length']:
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
        elif basis['reference_model_id'] is not None or bill['price_type'] == 'reference':
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
            elif any(m[k] != target[k] for k in PRICE_FIELDS):
                fail(mid, 'reference base prices disagree with reference model')
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
        path = '/models/{model_id}.json' if rel.startswith('models/') else '/vendors/{vendor}.json' if rel.startswith('vendors/') else '/' + rel
        schema = copy.deepcopy(spec['paths'][path]['get']['responses']['200']['content']['application/json']['schema'])
        schema['components'] = spec['components']
        for e in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(response):
            errors.append(rel + '.' + '.'.join(map(str, e.path)) + ': ' + e.message)
    return errors


def main():
    d = build_api.load()
    problems = validate_data(d)
    if not problems:
        problems += validate_api(d)
        problems += build_api.check(d)
    for problem in problems:
        print('BAD', problem)
    print('%d models, %d problem(s)' % (len(d['models']), len(problems)))
    for m in d['models']:
        for k in m['unverified_fields']:
            print('unverified:', m['model_id'], k)
    print('api/v1: in sync and schema-valid' if not problems else 'validation FAILED')
    return bool(problems)


if __name__ == '__main__':
    sys.exit(main())
