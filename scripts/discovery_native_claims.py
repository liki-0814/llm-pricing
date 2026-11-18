"""Source-qualified literal identity/channel/output observations, never full catalogs.

Shared by OpenAI and xAI. No pricing writes, family-name guesses, alias templates,
provider ID borrowing, input=>output inference, or account-entitlement inference.
"""
import json,re
from urllib.parse import urlsplit,unquote
import discovery_claim_contract as c
from discovery_claim_contract import qualified,claim,valid_claim,project,MODALITIES
OA='https://developers.openai.com/api/docs/models/all.md'
XAI='https://docs.x.ai/developers/models.md'


from discovery_markdown import sections

def openai_candidates(text):
    """Observe every formal candidate BEFORE deciding whether it is a literal ID."""
    out=[]
    for section in sections(text):
        for number,line in section['lines']:
            primary=re.fullmatch(r'Model ID:\s*`([^`]+)`\s*',line)
            hit=re.fullmatch(r'- `([^`]+)`(?: — (.+))?',line) if section['name'] in ('Snapshots','Model IDs') else None
            if primary and section['name'] is None:token=primary[1];role='primary';status=None
            elif hit:token=hit[1];role='snapshot_or_alias';status=hit[2]
            elif section['name'] in ('Snapshots','Model IDs') and line.startswith('- '):token=line[2:];role='unclassified_snapshot_candidate';status=None
            else:continue
            literal=role!='unclassified_snapshot_candidate' and c.canonical_id(token)==token
            out.append(dict(model_id=token if literal else None,raw_token=token,role=role,line=number,quote=line,termination=section['termination'],status=status))
    return out


def openai_identity(text):
    return [x for x in openai_candidates(text) if x['model_id'] is not None]


def openai_detail(doc,entity):
    url=doc['source_url'];parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname!='developers.openai.com' or not parsed.path.startswith('/api/docs/models/') or not parsed.path.endswith('.md') or parsed.query or parsed.fragment or parsed.username or parsed.password or '..' in unquote(parsed.path).split('/'):raise ValueError('unapproved OpenAI detail source')
    if doc.get('vendor') not in (None,'OpenAI') or doc.get('channel') not in (None,'pay_as_you_go'):raise ValueError('OpenAI native claim context mismatch')
    doc=dict(doc,vendor='OpenAI',channel='pay_as_you_go',catalog_source_url=OA)
    qualified(doc);parts=sections(doc['text']);candidates=openai_candidates(doc['text']);identities=[x for x in candidates if x['model_id'] is not None];primary={x['model_id'] for x in identities if x['role']=='primary'}
    aliases=[s for s in parts if s['name'] in ('Snapshots','Model IDs')]
    invalid=[x for x in candidates if x['model_id'] is None]
    alias_errors=['unclassified/nonliteral identity candidates retained'] if invalid else []
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
            direct=re.fullmatch(r'Alias for `([^`]+)`',status or '')
            if direct and c.canonical_id(direct[1])==direct[1]:claims.append(claim(doc,mid,'alias',status='direct',alias_of=direct[1],line=ident['line'],quote=ident['quote']))
            if status=='Shut down':claims.append(claim(doc,mid,'lifecycle',status='retired',line=ident['line'],quote=ident['quote']))
        if mid in primary:
            for section in parts:
                if section['name'] is not None:continue
                for number,line in section['lines']:
                    if line=='Aliases: None':claims.append(claim(doc,mid,'alias',status='none',line=number,quote=line))
                    if line in ('Status: Available','Status: Active'):claims.append(claim(doc,mid,'lifecycle',status='active',line=number,quote=line))
                    if line in ('Status: Shut down','Status: Deprecated'):claims.append(claim(doc,mid,'lifecycle',status='retired' if line.endswith('Shut down') else 'deprecated',line=number,quote=line))
        row=dict(model_id=mid,api_id_explicit=True,catalog_observation=False,identity_evidence={'claims':claims},**project(claims))
        row.update(id_enumeration_complete=not alias_errors,scope_status='native_channel_observed' if bound_channel else 'pending_native_channel_applicability',retired_at=None)
        rows.append(row)
    for observed in invalid:
        rows.append(dict(observed,api_id_explicit=False,catalog_observation=True,display_name=observed['raw_token'],id_enumeration_complete=False,scope_status='unclassified_identity_candidate',identity_evidence=dict(qualified(doc),**observed),output_modalities=[],channel_applicability='unknown'))
    return rows,dict(unclassified_identity_observations=[dict(qualified(doc),**x) for x in invalid],identity_count=len({x['model_id'] for x in identities}),id_enumeration_complete=not alias_errors,id_enumeration_errors=alias_errors,output_declarations=len(output_claims),native_channel_verified=channel_ok,termination=[x['termination'] for x in aliases])


def xai_records(doc):
    if doc['source_url']!=XAI:raise ValueError('xAI PAYG claims require exact native API model source; never subscription price page')
    if doc.get('vendor') not in (None,'xAI') or doc.get('channel') not in (None,'pay_as_you_go'):raise ValueError('xAI native claim context mismatch')
    doc=dict(doc,vendor='xAI',channel='pay_as_you_go',catalog_source_url=XAI)
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
