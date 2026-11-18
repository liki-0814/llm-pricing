"""Source-qualified literal identity/channel/output observations, never full catalogs.

Shared by OpenAI and xAI. No pricing writes, family-name guesses, alias templates,
provider ID borrowing, input=>output inference, or account-entitlement inference.
"""
import json,re
from urllib.parse import urlsplit,unquote
import catalog_diff as c
MODALITIES={'text','image','audio','video'}
OA='https://developers.openai.com/api/docs/models/all.md'
XAI='https://docs.x.ai/developers/models.md'


def sections(text):
    """Line-preserving Markdown sections; legal EOF closes a section, not a fence."""
    result=[];current=dict(name=None,line=1,lines=[],termination=None);fence=None
    for number,line in enumerate(text.splitlines(),1):
        if fence:
            if re.fullmatch(r' {0,3}'+re.escape(fence[0])+r'{'+str(fence[1])+r',}[ \t]*',line):fence=None
            continue
        start=re.match(r' {0,3}(`{3,}|~{3,})(.*)$',line)
        if start:fence=(start[1][0],len(start[1]));continue
        heading=re.match(r'^## (.+?)\s*$',line)
        if heading:
            current['termination']='next_heading';result.append(current)
            current=dict(name=heading[1],line=number,lines=[],termination=None)
        else:current['lines'].append((number,line))
    current['termination']='unclosed_fence' if fence else 'EOF';result.append(current)
    return result


def openai_identity(text):
    parts=sections(text);ids=[]
    for section in parts:
        for number,line in section['lines']:
            primary=re.fullmatch(r'Model ID:\s*`([^`]+)`\s*',line)
            if primary and section['name'] is None and c.canonical_id(primary[1])==primary[1]:ids.append(dict(model_id=primary[1],role='primary',line=number,quote=line,termination=section['termination']))
            if section['name'] in ('Snapshots','Model IDs'):
                hit=re.fullmatch(r'- `([^`]+)`(?: — (.+))?',line)
                if hit and c.canonical_id(hit[1])==hit[1]:ids.append(dict(model_id=hit[1],role='snapshot_or_alias',line=number,quote=line,termination=section['termination'],status=hit[2]))
    return ids


def qualified(doc):
    if not isinstance(doc.get('source_sha256'),str) or not re.fullmatch('[0-9a-f]{64}',doc['source_sha256']):raise ValueError('raw source hash missing')
    parsed=urlsplit(doc.get('source_url',''))
    if parsed.scheme!='https' or parsed.username or parsed.password:raise ValueError('official HTTPS source missing')
    if not isinstance(doc.get('capture_path'),str) or not doc['capture_path']:raise ValueError('raw capture path missing')
    c.parse_time(doc.get('observed_at',''))
    return {k:doc.get(k) for k in ('source_url','source_sha256','capture_path','observed_at')}


def claim(doc,mid,kind,**fields):return dict(qualified(doc),model_id=mid,kind=kind,**fields)


def valid_claim(value):
    """JSON contract validation before claims enter the shared diff consumer."""
    if not isinstance(value,dict) or value.get('kind') not in ('identity','output','native_channel','lifecycle'):return False
    if not isinstance(value.get('model_id'),str) or c.canonical_id(value['model_id'])!=value['model_id']:return False
    try:qualified(value)
    except (ValueError,TypeError,AttributeError):return False
    if value['kind']=='output':
        modes=value.get('values')
        if modes is not None and (not isinstance(modes,list) or not modes or any(not isinstance(x,str) for x in modes) or len(modes)!=len(set(modes)) or not set(modes)<=MODALITIES):return False
    if value['kind']=='native_channel' and (value.get('status') not in ('verified','unknown') or not isinstance(value.get('reason'),str)):return False
    if value['kind']=='lifecycle' and value.get('status') not in ('retired','deprecated'):return False
    return True


def project(claims):
    """Sticky conflicts, exact per-ID provenance; unknown never disappears by order."""
    if len({x['model_id'] for x in claims})>1:raise ValueError('cannot project claims for different literal IDs')
    claims=sorted(claims,key=lambda x:json.dumps(x,sort_keys=True,ensure_ascii=False))
    outputs=[tuple(sorted(x['values'])) for x in claims if x['kind']=='output' and x.get('values') is not None]
    conflict=len(set(outputs))>1 or any(x.get('conflict') for x in claims if x['kind']=='output')
    union=set().union(*(set(x) for x in outputs)) if outputs else set()
    if any(x.get('conflict') and x.get('values') is None for x in claims if x['kind']=='output'):union|=MODALITIES
    channel=[x.get('status') for x in claims if x['kind']=='native_channel']
    statuses={x['status'] for x in claims if x['kind']=='lifecycle'}
    status_conflict=len(statuses)>1
    return dict(native_claims=claims,output_modalities=sorted(union) if outputs and not conflict else [],
        unknown_output_modalities=sorted(union or MODALITIES) if conflict or not outputs else [],output_conflict=conflict,
        channel_applicability='verified' if channel and set(channel)=={'verified'} else 'unknown',
        channel_unknown_reasons=sorted({x.get('reason','unspecified') for x in claims if x['kind']=='native_channel' and x.get('status')!='verified'}),
        lifecycle_status=next(iter(statuses)) if statuses and not status_conflict else 'unconfirmed',lifecycle_conflict=status_conflict,lifecycle_quote='\n'.join(dict.fromkeys(x['quote'] for x in claims if x['kind']=='lifecycle' and x.get('quote'))) or None,
        alias_of=None,alias_status='unknown_snapshot_or_alias_role_not_a_direct_mapping')


def openai_detail(doc,entity):
    url=doc['source_url'];parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname!='developers.openai.com' or not parsed.path.startswith('/api/docs/models/') or not parsed.path.endswith('.md') or parsed.query or parsed.fragment or parsed.username or parsed.password or '..' in unquote(parsed.path).split('/'):raise ValueError('unapproved OpenAI detail source')
    qualified(doc);parts=sections(doc['text']);identities=openai_identity(doc['text']);primary={x['model_id'] for x in identities if x['role']=='primary'}
    aliases=[s for s in parts if s['name'] in ('Snapshots','Model IDs')]
    alias_errors=[]
    if not aliases:alias_errors.append('literal ID enumeration absent')
    if len(aliases)>1:alias_errors.append('multiple ID enumeration sections')
    for section in aliases:
        if section['termination']=='unclosed_fence':alias_errors.append('unclosed fence is not legal EOF termination')
        bullets=[line for _,line in section['lines'] if line.startswith('- ')]
        if not bullets or any(not re.fullmatch(r'- `([^`]+)`(?: — .+)?',line) for line in bullets):alias_errors.append('unparsed/empty literal ID enumeration')
    details=[s for s in parts if s['name']=='Model details'];output_claims=[]
    for s in details:
        for number,line in s['lines']:
            match=re.fullmatch(r'- Output modalities: (.+)',line)
            if not match:continue
            values=[x.strip() for x in match[1].split(',')]
            output_claims.append(dict(values=values if values and len(values)==len(set(values)) and set(values)<=MODALITIES else None,line=number,quote=line))
    endpoints=[]
    for s in parts:
        if s['name']!='Endpoints':continue
        if '| Endpoint | Route | Support |' not in [line for _,line in s['lines']]:continue
        for number,line in s['lines']:
            m=re.fullmatch(r'\| ([^|]+) \| `(v1/[A-Za-z0-9_/-]+)` \| Supported \|',line)
            if m:endpoints.append(dict(line=number,quote=line,route=m[2]))
    open_weight=entity.get('catalog_section')=='Open-weight models' or 'open-weight' in '\n'.join(line for s in parts if s['name'] is None for _,line in s['lines']).lower()
    channel_ok=bool(len(primary)==1 and endpoints and not open_weight)
    channel_reason='native API directory + this model supported endpoint; documented usage, not account entitlement' if channel_ok else ('open-weight native PAYG attribution not proven' if open_weight else 'no bound native supported endpoint or unique primary ID')
    rows=[]
    for mid in dict.fromkeys(x['model_id'] for x in identities):
        bound_channel=channel_ok and (mid in primary or not alias_errors)
        roles=[x for x in identities if x['model_id']==mid];claims=[claim(doc,mid,'identity',**{k:v for k,v in x.items() if k!='model_id'}) for x in roles]
        claims.append(claim(doc,mid,'native_channel',status='verified' if bound_channel else 'unknown',reason=channel_reason if bound_channel or not channel_ok else 'ID enumeration is not closed',endpoints=endpoints))
        can_bind=bool(len(primary)==1 and output_claims and (mid in primary or not alias_errors))
        if can_bind:
            for output in output_claims:claims.append(claim(doc,mid,'output',**output,conflict=output['values'] is None or len(details)!=1,binding='same native detail entity and literal ID enumeration'))
        else:claims.append(claim(doc,mid,'output',values=None,conflict=bool(output_claims),unbound_output_declarations=output_claims,reason='unique primary/output or closed ID enumeration missing'))
        for ident in roles:
            status=ident.get('status')
            if status=='Shut down':claims.append(claim(doc,mid,'lifecycle',status='retired',line=ident['line'],quote=ident['quote']))
        if mid in primary:
            for section in parts:
                if section['name'] is not None:continue
                for number,line in section['lines']:
                    if line in ('Status: Shut down','Status: Deprecated'):claims.append(claim(doc,mid,'lifecycle',status='retired' if line.endswith('Shut down') else 'deprecated',line=number,quote=line))
        row=dict(model_id=mid,api_id_explicit=True,catalog_observation=False,identity_evidence={'claims':claims},**project(claims))
        row.update(id_enumeration_complete=not alias_errors,scope_status='native_channel_observed' if bound_channel else 'pending_native_channel_applicability',retired_at=None)
        rows.append(row)
    return rows,dict(identity_count=len({x['model_id'] for x in identities}),id_enumeration_complete=not alias_errors,id_enumeration_errors=alias_errors,output_declarations=len(output_claims),native_channel_verified=channel_ok,termination=[x['termination'] for x in aliases])


def xai_records(doc):
    if doc['source_url']!=XAI:raise ValueError('xAI PAYG claims require exact native API model source; never subscription price page')
    qualified(doc);rows=[]
    for section in sections(doc['text']):
        # xAI uses H3 pricing sections inside a H1 page. Parse typed table
        # headings below with line-local state; no model-name prefix inference.
        current=None;header=False
        for number,line in section['lines']:
            if line.startswith('### '):current=line[4:];header=False;continue
            if current not in ('Text API Pricing','Image & Video Pricing'):continue
            if line.startswith('| Model |'):
                expected='| Model | Context | Input / 1M tokens | Cached input / 1M tokens | Output / 1M tokens |' if current=='Text API Pricing' else '| Model | Cost |'
                header=line==expected;continue
            if not header or not line.startswith('| '):continue
            cells=[x.strip() for x in line.strip('|').split('|')]
            if all(re.fullmatch(r'[: -]+',x) for x in cells):continue
            mid=re.sub(r' \((?:<|≥) [^)]*prompt tokens\)$','',cells[0])
            if c.canonical_id(mid)!=mid:continue
            modality=None
            if current=='Text API Pricing' and len(cells)==5:modality='text'
            elif current=='Image & Video Pricing' and len(cells)==2:
                if re.fullmatch(r'\$[0-9.]+ / image',cells[1]):modality='image'
                elif re.fullmatch(r'\$[0-9.]+ / sec',cells[1]):modality='video'
            if modality is None:continue
            claims=[claim(doc,mid,'identity',role='literal_native_API_pricing_Model_cell',line=number,quote=line),claim(doc,mid,'output',values=[modality],line=number,quote=line,binding=current),claim(doc,mid,'native_channel',status='verified',reason='native API per-request/token/output-unit usage pricing; not subscription or account entitlement',line=number,quote=line)]
            rows.append(dict(model_id=mid,api_id_explicit=True,catalog_observation=False,price_public=True,identity_evidence={'claims':claims},**project(claims)))
    grouped={}
    for row in rows:grouped.setdefault(row['model_id'],[]).extend(row['native_claims'])
    return [dict(model_id=mid,api_id_explicit=True,catalog_observation=False,price_public=True,identity_evidence={'claims':claims},**project(claims)) for mid,claims in grouped.items()]
