"""Read-only projection of already bounded vendor observations into one contract.

No parser/coverage override: accepted Google/Anthropic/MiniMax observations remain
unchanged. Missing proof is explicit; a certificate does not certify itself.
"""
import hashlib,json,re
from pathlib import Path
from urllib.parse import urlsplit
from discovery_claim_contract import claim,canonical_id,valid_claim,MODALITIES
from discovery_universe_contracts import scope_certificate,unknown
from discovery_request_contracts import request_models


def source(snapshot,evidence,quote,manifest):
    if not isinstance(evidence,dict) or not isinstance(quote,str) or not quote:return None
    hosts={h for s in manifest['scopes'] if (s['vendor'],s['channel'])==(snapshot['vendor'],snapshot['channel']) for h in s['official_hosts']}
    url=urlsplit(evidence.get('source_url',''))
    if url.scheme!='https' or url.netloc not in hosts or url.username or url.password:return None
    path=Path(evidence.get('capture_path','/nonexistent'))
    if not path.is_file():return None
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=evidence.get('source_sha256'):return None
    text=raw.decode('utf-8')
    if quote not in text:return None
    return dict(source_url=evidence['source_url'],source_sha256=evidence['source_sha256'],capture_path=str(path),observed_at=evidence['observed_at'],vendor=snapshot['vendor'],channel=snapshot['channel'],catalog_source_url=snapshot['source_url'])


def minimax_native_channel_eligible(snapshot,entry,spec,mid):
    """Pure bounded channel predicate; caller must first verify raw capture provenance.

    Re-use the producer's finite source/route map and strict satisfiable request
    validator. This proves documented API channel only, never authorship, current
    account entitlement, output, or a closed global population.
    """
    import discovery_minimax_contracts as native
    if (snapshot.get('vendor'),snapshot.get('channel'),snapshot.get('source_url'))!=('MiniMax','pay_as_you_go',native.ROOT):return False
    url=entry.get('source_url','')
    if not url.startswith(native.BASE) or url[len(native.BASE):] not in native.SPECS:return False
    modality,route=native.SPECS[url[len(native.BASE):]]
    routes={route}
    if url==native.BASE+'video/generation/api/v2-video-generation.json':routes.add('/v2/video_regeneration')
    if snapshot.get('coverage_evidence',{}).get('modalities')!=[modality] or entry.get('server')!='https://api.minimax.io' or entry.get('route') not in routes:return False
    try:return any(r.get('model_id')==mid for r in request_models(spec,entry['route'],entry['server']))
    except (ValueError,KeyError,TypeError):return False


def minimax_output_statement(snapshot,entry,spec,mid):
    """Explicit operation output wording, after the same native request binding."""
    if not minimax_native_channel_eligible(snapshot,entry,spec,mid):return None
    summary=spec['paths'][entry['route']]['post'].get('summary')
    declared={'Text Generation V2':'text','Image Generation':'image','Image Edit':'image','Text-to-Image':'image','Video Generation':'video','Create video generation task':'video','Create Video Regeneration Task':'video'}.get(summary)
    if snapshot['coverage_evidence']['modalities']!=[declared]:return None
    return summary


def qualified_producer_claims(snapshot,row,manifest):
    mid=row.get('model_id');claims=[]
    if row.get('api_id_explicit') is not True or canonical_id(mid)!=mid:return claims
    existing=row.get('native_claims',[])
    if existing:return [x for x in existing if valid_claim(x,vendor=snapshot['vendor'],channel=snapshot['channel'],source_url=snapshot['source_url']) and x.get('model_id')==mid]
    evidence=row.get('identity_evidence',{});vendor=snapshot['vendor']
    if vendor=='Anthropic' and isinstance(evidence,dict):
        for entry in evidence.get('claims',[]):
            quote=entry.get('quote');scoped=source(snapshot,entry,quote,manifest)
            if not scoped or entry.get('model_id')!=mid or mid not in quote:continue
            claims.append(claim(scoped,mid,'identity',role='existing_bounded_Anthropic_'+entry.get('kind','literal'),line=entry.get('line'),quote=quote))
            output=entry.get('output_evidence',{});oq=output.get('quote');os=source(snapshot,output,oq,manifest)
            if os and entry.get('output_modalities') and output.get('declared_output')=='text':claims.append(claim(os,mid,'output',values=['text'],line=output.get('line'),quote=oq))
            status=entry.get('lifecycle_status')
            if status in ('active','listed','deprecated','retired'):claims.append(claim(scoped,mid,'lifecycle',status=status,line=entry.get('line'),quote=quote))
            if entry.get('kind')=='alias' and entry.get('alias_of'):claims.append(claim(scoped,mid,'alias',status='direct',alias_of=entry['alias_of'],line=entry.get('line'),quote=quote))
    elif vendor=='Google Gemini' and isinstance(evidence,dict):
        for entry in evidence.get('declarations',[]):
            quote=entry.get('identity_quote') if mid in entry.get('identity_quote','') else entry.get('versions_quote','')
            scoped=source(snapshot,entry,quote,manifest)
            if not scoped or mid not in quote:continue
            claims.append(claim(scoped,mid,'identity',role='existing_bounded_Google_invocation_or_Versions_literal',quote=quote))
            oq=entry.get('output_quote');os=source(snapshot,entry,oq,manifest)
            # The original producer leaves historical/ambiguous versions unknown.
            if os and entry.get('output'):
                values=entry['output']
                if set(values)<=MODALITIES:claims.append(claim(os,mid,'output',values=values,quote=oq))
                else:claims.append(claim(os,mid,'output',values=None,quote=oq,unclassified_output_values=values,reason='output artifacts outside the closed modality contract retained; not silently coerced or dropped'))
    elif vendor=='MiniMax' and isinstance(evidence,list):
        for entry in evidence:
            if entry.get('identity_role')!='request_model_enum' or entry.get('model_id')!=mid:continue
            p=Path(entry.get('capture_path','/nonexistent'))
            if not p.is_file():continue
            raw=p.read_bytes();text=raw.decode('utf-8');quote=json.dumps(mid,ensure_ascii=False);scoped=source(snapshot,entry,quote,manifest)
            if not scoped:continue
            # Re-use the same strict request-eligibility validator, not string search.
            try:eligible=request_models(json.loads(text),entry['route'],entry['server'])
            except (ValueError,KeyError,TypeError):continue
            if not any(r.get('model_id')==mid for r in eligible):continue
            claims.append(claim(scoped,mid,'identity',role='validated_request_model_enum',quote=quote,route=entry['route'],server=entry['server']))
            if minimax_native_channel_eligible(snapshot,entry,json.loads(text),mid):
                claims.append(claim(scoped,mid,'native_channel',status='verified',reason='literal ID accepted by the bound native generation request schema; not account entitlement or global population closure',quote=quote,route=entry['route'],server=entry['server'],evidence_role='validated_native_request_server_route_model_enum'))
                statement=minimax_output_statement(snapshot,entry,json.loads(text),mid)
                output_quote=json.dumps(statement,ensure_ascii=False) if statement else None
                if output_quote and output_quote in text:
                    claims.append(claim(scoped,mid,'output',values=list(snapshot['coverage_evidence']['modalities']),quote=output_quote,model_quote=quote,route=entry['route'],server=entry['server'],evidence_role='explicit_bound_generation_operation_summary'))
        for entry in row.get('directory_evidence',[]):
            quote=entry.get('quote');scoped=source(snapshot,entry,quote,manifest)
            status=entry.get('lifecycle_status')
            if row.get('lifecycle_status')=='retired' and status!='retired':continue
            if scoped and entry.get('display_name')==mid and status in ('listed','retired','deprecated'):
                claims.append(claim(scoped,mid,'lifecycle',status=entry['lifecycle_status'],line=entry.get('line'),quote=quote))
    return claims


def attach_scope_certificates(inventories,manifest):
    """Wire all applicable legacy/subscription paths without upgrading coverage flags."""
    for snapshot in inventories:
        if snapshot.get('vendor') not in ('Anthropic','Google Gemini','MiniMax','xAI','阿里云 Qwen'):continue
        if snapshot.get('scope_certificates'):continue
        modes=list(snapshot.get('coverage_evidence',{}).get('modalities',[]))
        if snapshot['vendor']=='Google Gemini':modes=['text','image','video']
        projected=[]
        for row in snapshot.get('records',[]):
            claims=qualified_producer_claims(snapshot,row,manifest)
            row['certification_claims']=claims
            projected.append(dict(row,native_claims=claims))
        snapshot['scope_certificates']=[scope_certificate(snapshot['vendor'],snapshot['channel'],mode,projected,population=unknown('full current+historical native population not established by this source',original_producer_proof=snapshot.get('coverage_evidence',{}).get('proof',{}),source_role=snapshot.get('role')),pagination=unknown('no independent global/historical termination declaration; account/directory observations retained'),alias_enumeration=unknown('direct observed mappings are not proof of exhaustive alias population'),lifecycle=unknown('per-ID statuses retained; full lifecycle population remains unproved')) for mode in modes]
        snapshot['certificate_projection']='qualified_existing_producer_observations; no coverage override'
