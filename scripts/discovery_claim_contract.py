"""Neutral literal identity, provenance, channel and claim projection contract. No adapters/consumers imported."""
import re,json,datetime as dt
from urllib.parse import urlsplit
MODALITIES={"text","image","audio","video"}
ID = re.compile(r"^[a-z0-9][a-z0-9._/-]*$", re.I)


def canonical_id(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if ID.fullmatch(value) else None


def parse_time(value):
    value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None: raise ValueError("Timezone required")
    return value.astimezone(dt.timezone.utc)


def qualified(doc):
    if not isinstance(doc.get('source_sha256'),str) or not re.fullmatch('[0-9a-f]{64}',doc['source_sha256']):raise ValueError('raw source hash missing')
    parsed=urlsplit(doc.get('source_url',''))
    if parsed.scheme!='https' or parsed.username or parsed.password:raise ValueError('official HTTPS source missing')
    if not isinstance(doc.get('capture_path'),str) or not doc['capture_path']:raise ValueError('raw capture path missing')
    parse_time(doc.get('observed_at',''))
    if any(not isinstance(doc.get(k),str) or not doc[k] for k in ('vendor','channel','catalog_source_url')):raise ValueError('claim vendor/channel context missing')
    return {k:doc.get(k) for k in ('source_url','source_sha256','capture_path','observed_at','vendor','channel','catalog_source_url')}


def claim(doc,mid,kind,**fields):return dict(qualified(doc),model_id=mid,kind=kind,**fields)


def valid_claim(value, *, vendor=None, channel=None, source_url=None):
    """JSON contract validation before claims enter the shared diff consumer."""
    if not isinstance(value,dict) or value.get('kind') not in ('identity','output','native_channel','lifecycle','alias'):return False
    if not isinstance(value.get('model_id'),str) or canonical_id(value['model_id'])!=value['model_id']:return False
    try:qualified(value)
    except (ValueError,TypeError,AttributeError):return False
    if vendor is not None and value['vendor']!=vendor:return False
    if channel is not None and value['channel']!=channel:return False
    if source_url is not None and value['catalog_source_url']!=source_url:return False
    if value['kind']=='output':
        modes=value.get('values')
        if modes is not None and (not isinstance(modes,list) or not modes or any(not isinstance(x,str) for x in modes) or len(modes)!=len(set(modes)) or not set(modes)<=MODALITIES):return False
    if value['kind']=='native_channel' and (value.get('status') not in ('verified','unknown') or not isinstance(value.get('reason'),str)):return False
    if value['kind']=='lifecycle' and value.get('status') not in ('retired','deprecated','active','listed'):return False
    if value['kind']=='alias' and (value.get('status') not in ('direct','none') or (value['status']=='direct' and (not isinstance(value.get('alias_of'),str) or canonical_id(value['alias_of'])!=value['alias_of']))):return False
    if value['kind']=='alias' and (not isinstance(value.get('quote'),str) or not value['quote'] or type(value.get('line')) is not int or value['line']<1 or (value['status']=='none' and value.get('alias_of') is not None)):return False
    return True


def project(claims):
    """Sticky conflicts, exact per-ID provenance; unknown never disappears by order."""
    if len({x['model_id'] for x in claims})>1:raise ValueError('cannot project claims for different literal IDs')
    if any(not valid_claim(x) for x in claims):raise ValueError('unqualified native projection')
    if len({(x['vendor'],x['channel'],x['catalog_source_url']) for x in claims})>1:raise ValueError('cross-context native projection')
    claims=sorted(claims,key=lambda x:json.dumps(x,sort_keys=True,ensure_ascii=False))
    outputs=[tuple(sorted(x['values'])) for x in claims if x['kind']=='output' and x.get('values') is not None]
    conflict=len(set(outputs))>1 or any(x.get('conflict') for x in claims if x['kind']=='output')
    union=set().union(*(set(x) for x in outputs)) if outputs else set()
    if any(x.get('conflict') and x.get('values') is None for x in claims if x['kind']=='output'):union|=MODALITIES
    channel=[x.get('status') for x in claims if x['kind']=='native_channel']
    statuses={x['status'] for x in claims if x['kind']=='lifecycle'}
    status_conflict=len(statuses)>1
    alias_targets={x.get('alias_of') for x in claims if x['kind']=='alias' and x.get('status')=='direct'}
    no_alias=any(x['kind']=='alias' and x.get('status')=='none' for x in claims)
    alias_conflict=len(alias_targets)>1 or bool(alias_targets and no_alias)
    return dict(native_claims=claims,output_modalities=sorted(union) if outputs and not conflict else [],
        unknown_output_modalities=sorted(union or MODALITIES) if conflict or not outputs else [],output_conflict=conflict,
        channel_applicability='verified' if channel and set(channel)=={'verified'} else 'unknown',
        channel_unknown_reasons=sorted({x.get('reason','unspecified') for x in claims if x['kind']=='native_channel' and x.get('status')!='verified'}),
        lifecycle_status=next(iter(statuses)) if statuses and not status_conflict else 'unconfirmed',lifecycle_conflict=status_conflict,lifecycle_quote='\n'.join(dict.fromkeys(x['quote'] for x in claims if x['kind']=='lifecycle' and x.get('quote'))) or None,
        alias_of=next(iter(alias_targets)) if len(alias_targets)==1 and not alias_conflict else None,alias_status='conflicting_explicit_alias_declarations' if alias_conflict else 'explicit_official_mapping' if alias_targets else 'explicit_no_aliases' if no_alias else 'unknown_snapshot_or_alias_role_not_a_direct_mapping')


