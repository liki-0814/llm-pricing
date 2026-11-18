"""Finite, context-bound universe/alias/lifecycle obligations. No network or consumer imports.

This evaluates evidence, never turns an unread directory or account-visible API into
an empty/global population. Positive scope certificates require every obligation.
"""
import copy,hashlib,json,re
from urllib.parse import urlsplit,parse_qs
from discovery_markdown import formal_text
from discovery_claim_contract import canonical_id,valid_claim,project,direct_alias_map

DIMENSIONS=('population','pagination','identity','native_channel','output','alias_enumeration','lifecycle')

def scope_certificate(vendor,channel,modality,records,*,population,pagination,alias_enumeration,lifecycle,source_evidence=()):
    facts={k:copy.deepcopy(v) for k,v in (('population',population),('pagination',pagination),('alias_enumeration',alias_enumeration),('lifecycle',lifecycle))}
    rows=list(records);pending=[r for r in rows if r.get('api_id_explicit') is not True or canonical_id(r.get('model_id'))!=r.get('model_id')]
    ids={r['model_id'] for r in rows if r.get('api_id_explicit') is True and canonical_id(r.get('model_id'))==r.get('model_id')}
    unqualified_ids=[]
    for mid in ids:
        claims=[c for r in rows if r.get('model_id')==mid for c in r.get('native_claims',[]) if valid_claim(c,vendor=vendor,channel=channel) and c.get('model_id')==mid]
        if not any(c['kind']=='identity' for c in claims):unqualified_ids.append(mid)
    unrecognized_alias=[dict(model_id=r.get('model_id'),declarations=r.get('unrecognized_alias_declarations')) for r in rows if r.get('unrecognized_alias_declarations')]
    unrecognized_lifecycle=[dict(model_id=r.get('model_id'),declarations=r.get('unrecognized_lifecycle_declarations')) for r in rows if r.get('unrecognized_lifecycle_declarations')]
    facts['identity']=dict(state='verified' if ids and not pending and not unqualified_ids else 'unknown',pending_count=len(pending),literal_ids=sorted(ids),unqualified_ids=sorted(unqualified_ids),unclassified_candidates=[r for r in pending])
    channel_unknown=[];output_unknown=[];output_proven=[];output_conflicted=[];alias_unknown=[];lifecycle_unknown=[]
    for mid in sorted(ids):
        local=[r for r in rows if r.get('model_id')==mid]
        claims=[c for r in local for c in r.get('native_claims',[]) if valid_claim(c,vendor=vendor,channel=channel) and c.get('model_id')==mid]
        try:proven=project(claims)
        except ValueError:proven={}
        if proven.get('channel_applicability')!='verified':channel_unknown.append(mid)
        if proven.get('alias_status') not in ('explicit_official_mapping','explicit_no_aliases'):alias_unknown.append(mid)
        if proven.get('lifecycle_status') not in ('active','listed','retired','deprecated'):lifecycle_unknown.append(mid)
        if modality not in (proven.get('output_modalities') or []):output_unknown.append(mid)
        if modality in (proven.get('output_modalities') or []):output_proven.append(mid)
        if modality in (proven.get('unknown_output_modalities') or []):output_conflicted.append(mid)
    facts['native_channel']=dict(state='unknown' if channel_unknown else 'verified',unknown_ids=channel_unknown)
    # Only the requested modality's per-ID proof can verify it; another modality's output cannot.
    facts['output']=dict(state='verified' if output_proven and not output_conflicted else 'unknown',unknown_ids=output_unknown,proven_ids=output_proven,conflicted_ids=output_conflicted,modality=modality)
    for dimension,missing in (('alias_enumeration',alias_unknown),('lifecycle',lifecycle_unknown)):
        if missing:facts[dimension].update(state='unknown',per_ID_unproven=missing)
    if unrecognized_alias:facts['alias_enumeration'].update(state='unknown',unrecognized_declarations=unrecognized_alias,reason='unrecognized alias declarations retained; not inferred and not ignored')
    if unrecognized_lifecycle:facts['lifecycle'].update(state='unknown',unrecognized_declarations=unrecognized_lifecycle,reason='unrecognized lifecycle declarations retained; not inferred and not ignored')
    # A verified atom is source-backed and scoped; arbitrary complete=True is not an atom.
    for name in ('population','pagination','alias_enumeration','lifecycle'):
        atom=facts[name]
        evidence=atom.get('evidence',[])
        if atom.get('state')=='verified' and (not evidence or any(not isinstance(e,dict) or not e.get('quote') or not re.fullmatch('[0-9a-f]{64}',str(e.get('source_sha256',''))) or not e.get('capture_path') or e.get('vendor')!=vendor or e.get('channel')!=channel for e in evidence)):
            atom.update(state='unknown',reason='missing/mismatched source-qualified obligation evidence')
    closed=bool(ids and not pending and all(facts[d].get('state')=='verified' for d in DIMENSIONS))
    return dict(contract='source_qualified_universe/1',vendor=vendor,channel=channel,modality=modality,complete=closed,population_state='enumerated' if closed else 'not_certified',empty_state='not_an_empty_population_proof' if not ids else 'nonempty_observed',obligations=facts,source_evidence=list(source_evidence),unmet=[d for d in DIMENSIONS if facts[d].get('state')!='verified'])


def openai_directory_candidates(text):
    """Every official-directory entity candidate is retained; only the hyphen grammar is formal."""
    formal=[];unparsed=[]
    for number,line in enumerate(formal_text(text).splitlines(),1):
        if not line.strip() or line.startswith('#'):continue
        m=re.fullmatch(r'- \[([^]]+)\]\(([^)]+)\):?(.*)',line)
        if m:
            path=m[2]
            if re.fullmatch(r'/api/docs/models/[A-Za-z0-9._-]+(?:\.md)?',path) or re.search(r'Model ID:\s*`[^`]+`',m[3]):
                formal.append(dict(line=number,quote=line,display_name=m[1],path=path,inline_id=bool(re.search(r'Model ID:\s*`[^`]+`',m[3]))))
            else:unparsed.append(dict(line=number,quote=line,display_name=m[1],path=path,reason='unreviewed directory link grammar'))
            continue
        if re.search(r'\]\((?:https://developers\.openai\.com)?/api/docs/models/[^)]+\)',line):
            name=re.search(r'\[([^]]+)\]',line);path=re.search(r'\(([^)]+)\)',line)
            unparsed.append(dict(line=number,quote=line,display_name=name[1] if name else line,path=path[1] if path else None,reason='unparsed directory entity retained, not inferred as a native ID'))
    return formal,unparsed


def unknown(reason,**extra):return dict(state='unknown',reason=reason,**extra)

def native_observation_certificates(snapshot,root_document=None,supplementary=()):
    """Production certifier consumes each parsed ID/section proof; no unconditional false flag."""
    vendor,channel=snapshot['vendor'],snapshot['channel'];e=snapshot.get('coverage_evidence',{});consumed=e.get('native_claim_consumption',{});proofs=consumed.get('source_proofs',[])
    if vendor=='OpenAI':
        alias_bad=[p.get('source_url') for p in proofs if p.get('id_enumeration_complete') is not True]
        inline=[r['model_id'] for r in snapshot['records'] if r.get('model_id') and any(c.get('role')=='inline_directory_literal' for c in r.get('native_claims',[]))]
        alias=unknown('closed literal Snapshot/Model-ID lists do not prove direct alias relationships; inline IDs have no alias enumeration',unclosed_detail_urls=alias_bad,inline_unenumerated_ids=sorted(set(inline)),closed_detail_count=sum(p.get('id_enumeration_complete') is True for p in proofs),unmapped_role_ids=sorted({r['model_id'] for r in snapshot['records'] if r.get('model_id') and any(c.get('role')=='snapshot_or_alias' for c in r.get('native_claims',[]))}))
        population=unknown('root advertised population not validated');pagination=unknown('root traversal not validated')
        if root_document:
            text=formal_text(root_document['text']);headings=re.findall(r'^## (.+)$',text,re.M)
            known={'Flagship models','Image','Realtime & audio','OpenAI Daybreak','Life sciences','Open-weight models','Embedding models','More models','ChatGPT models','Deprecated models'}
            formal,unparsed=openai_directory_candidates(root_document['text'])
            expected={}
            for item in formal:
                path=item['path']
                if re.fullmatch(r'/api/docs/models/[A-Za-z0-9._-]+\.md',path):expected['https://developers.openai.com'+path]=item['quote']
            acquired={p.get('source_url') for p in proofs};missing=sorted(set(expected)-acquired)
            extra=[dict(source_url=s.get('source_url'),model_id=r.get('model_id'),detail_url=r.get('detail_url'),display_name=r.get('display_name')) for s in supplementary for r in s.get('records',[]) if r.get('detail_url') or r.get('model_id')]
            grammar=bool(text.startswith('# All models\n') and 'Deprecated models' in headings and len(headings)==len(set(headings)) and set(headings)<=known and formal and not unparsed and not re.search(r'(?i)\b(next page|load more|next_cursor|has_more)\b',text))
            evidence=[dict({k:v for k,v in root_document.items() if k!='text'},quote='# All models',line=1,vendor=vendor,channel=channel)]
            for item in unparsed:
                snapshot.setdefault('records',[]).append(dict(model_id=None,api_id_explicit=False,catalog_observation=True,display_name=item.get('display_name'),raw_token=item.get('display_name'),detail_url=('https://developers.openai.com'+item['path']) if item.get('path','').startswith('/') else item.get('path'),line=item['line'],quote=item['quote'],scope_status='unclassified_directory_candidate',identity_evidence=dict({k:v for k,v in root_document.items() if k!='text'},vendor=vendor,channel=channel,catalog_source_url=root_document.get('source_url'),**item)))
            population=dict(state='verified' if grammar and not missing and not extra else 'unknown',reason='all advertised current/deprecated model entities accounted for' if grammar and not missing and not extra else 'directory grammar, unparsed retained candidate, missing entity or supplementary source disagreement',evidence=evidence,advertised_entity_count=len(formal)+len(unparsed),required_child_urls=sorted(expected),missing_child_urls=missing,unparsed_candidate_lines=unparsed,retained_unclassified_candidates=unparsed,supplementary_unreconciled_entities=extra,population_basis='advertised_all_models_current_and_deprecated_NOT_account_entitlement')
            pagination=dict(state='verified' if grammar and not missing and not consumed.get('errors') else 'unknown',evidence=evidence,reason='formal finite root + every linked detail acquired; EOF, no cursor',required_details=len(expected),acquired_details=len(set(expected)&acquired),capture_failures=consumed.get('errors',[]),unparsed_candidate_count=len(unparsed))
    else:
        population=unknown('public usage-price table is not an exhaustive unpriced/retired native universe')
        pagination=unknown('priced table has EOF; no exhaustive catalog/retired termination claim')
        alias=unknown('generic alias templates are not a literal alias population; account model API must not be called a global universe')
    lifecycle_unknown=sorted({r['model_id'] for r in snapshot['records'] if r.get('model_id') and r.get('lifecycle_status') not in ('retired','deprecated','active','listed')})
    lifecycle_evidence=[c for r in snapshot['records'] for c in r.get('native_claims',[]) if c.get('kind')=='lifecycle']
    lifecycle=dict(state='unknown' if lifecycle_unknown or not lifecycle_evidence else 'verified',reason='explicit per-ID lifecycle declarations; unconfirmed is not an active/retired assertion',unknown_ids=lifecycle_unknown,evidence=lifecycle_evidence)
    mapping_unknown=sorted({r['model_id'] for r in snapshot['records'] if r.get('model_id') and r.get('alias_status') not in ('explicit_official_mapping','explicit_no_aliases')})
    alias_evidence=[c for r in snapshot['records'] for c in r.get('native_claims',[]) if c.get('kind')=='alias']
    all_ids={r['model_id'] for r in snapshot['records'] if r.get('model_id')}
    try:
        direct_alias_map(((r['model_id'],r['alias_of']) for r in snapshot['records'] if r.get('model_id') and r.get('alias_of')),known_ids=all_ids)
    except ValueError as error:
        mapping_unknown=sorted(set(mapping_unknown)|all_ids);alias=unknown(str(error),mapping_unknown_ids=mapping_unknown) if not isinstance(alias,dict) else alias
    if not mapping_unknown and alias_evidence and not consumed.get('errors') and not any(p.get('id_enumeration_complete') is False for p in proofs):alias=dict(state='verified',evidence=alias_evidence,reason='complete literal lists plus per-ID explicit mapping/no-alias declarations')
    else:alias['mapping_unknown_ids']=mapping_unknown
    return [scope_certificate(vendor,channel,m,snapshot['records'],population=population,pagination=pagination,alias_enumeration=alias,lifecycle=lifecycle) for m in e.get('modalities',[])]

def qwen_catalog_pages(documents):
    """Validate documented ListModels page exports, never documentation examples.

    Caller supplies original HTTP capture bodies and metadata, not API credentials.
    A complete response proves ONLY that account/region/filter population; never global.
    """
    if not documents:raise ValueError('no actual catalog response pages')
    context=None;pages={};total=None;models=[];seen=set()
    for doc in documents:
        url=urlsplit(doc['url'])
        allowed=bool(url.scheme=='https' and not url.username and not url.password and (re.fullmatch(r'[A-Za-z0-9-]+\.(?:cn-beijing|ap-southeast-1|cn-hongkong|eu-central-1|ap-northeast-1)\.maas\.aliyuncs\.com',url.hostname or '') or url.hostname=='dashscope-us.aliyuncs.com') and url.path=='/api/v1/models')
        if not allowed or doc.get('capture_kind')!='http_body' or doc.get('http_status')!=200:raise ValueError('not a documented successful catalog HTTP export')
        raw=doc['body'];raw=raw.encode() if isinstance(raw,str) else raw
        if hashlib.sha256(raw).hexdigest()!=doc.get('sha256'):raise ValueError('catalog page raw hash mismatch')
        body=json.loads(raw);output=body.get('output');request=doc.get('request',{})
        if not isinstance(output,dict) or not isinstance(output.get('models'),list) or type(output.get('total')) is not int or output['total']<0:raise ValueError('actual output.models/total missing (examples and total_count guesses rejected)')
        page,size=request.get('page_no'),request.get('page_size')
        query=parse_qs(url.query,keep_blank_values=True)
        if query.get('page_no')!=[str(page)] or query.get('page_size')!=[str(size)]:raise ValueError('URL and recorded pagination request disagree')
        filters={k:v for k,v in query.items() if k not in ('page_no','page_size')}
        declared={k:(v if isinstance(v,list) else [str(v)]) for k,v in request.get('filters',{}).items()}
        if any(k not in {'providers','capabilities','inference_providers','language','name','model'} for k in filters):raise ValueError('unsupported/SDK-client-side filter is not a server catalog filter')
        if filters!=declared or any(k.lower() in ('api_key','token','access_token','authorization') for k in query):raise ValueError('filter/request disagreement or credential-bearing URL')
        if type(page) is not int or page<1 or type(size) is not int or not 1<=size<=1000:raise ValueError('explicit page request metadata required')
        current=(url.scheme,url.netloc,url.path,json.dumps(request.get('filters',{}),sort_keys=True),size)
        if context is None:context=current;total=output['total']
        if current!=context or total!=output['total'] or page in pages:raise ValueError('mixed region/filter/size/total or duplicate page')
        pages[page]=len(output['models'])
        for item in output['models']:
            mid=item.get('model')
            if not isinstance(mid,str) or canonical_id(mid)!=mid or mid in seen:raise ValueError('missing/invalid/duplicate literal model identity')
            if query.get('providers') and item.get('provider') not in query['providers']:raise ValueError('server provider filter/result disagreement')
            seen.add(mid)
            response=item.get('inference_metadata',{}).get('response_modality')
            known={'Text':'text','Image':'image','Video':'video','Audio':'audio'}
            output_modes=[known[x] for x in response] if isinstance(response,list) and response and all(x in known for x in response) else []
            models.append(dict(model_id=mid,provider=item.get('provider'),output_modalities=sorted(set(output_modes)),output_status='verified' if output_modes else 'unknown',raw_model=item,source_url=doc['url'],source_sha256=doc['sha256'],capture_path=doc.get('capture_path'),page_no=page))
    expected=max(1,(total+context[-1]-1)//context[-1])
    if sorted(pages)!=list(range(1,expected+1)) or len(models)!=total:raise ValueError('catalog pagination incomplete or total mismatch')
    if any(pages[n]!=context[-1] for n in range(1,expected)):raise ValueError('short intermediate catalog page')
    return dict(models=models,pagination_complete=True,total=total,population='authenticated_account_region_filter',global_universe_verified=False,lifecycle_history_verified=False,aliases_verified=False,empty_state='verified_empty_account_region_filter' if total==0 else 'nonempty_account_region_filter',context=list(context))


def xai_catalog_exports(documents):
    """Consume documented native PAYG model/alias/output responses, never subscription.

    All endpoints are account-key scoped by the official reference. Their union
    is usable per-ID evidence, not a global/current+retired completeness claim.
    """
    allowed={'/v1/models':('data',None),'/v1/language-models':('models','text'),'/v1/image-generation-models':('models','image'),'/v1/video-generation-models':('models','video')}
    endpoints={};models={};alias_targets={};base_ids=None;detail_ids=set()
    for doc in documents:
        url=urlsplit(doc['url'])
        if url.scheme!='https' or url.netloc!='api.x.ai' or url.path not in allowed or url.query or url.fragment or doc.get('http_status')!=200 or doc.get('capture_kind')!='http_body' or doc.get('channel','pay_as_you_go')!='pay_as_you_go':raise ValueError('not a documented native PAYG catalog HTTP export')
        if url.path in endpoints:raise ValueError('duplicate model catalog endpoint')
        raw=doc['body'];raw=raw.encode() if isinstance(raw,str) else raw
        if hashlib.sha256(raw).hexdigest()!=doc.get('sha256'):raise ValueError('model export body/hash mismatch')
        data=json.loads(raw);field,modality=allowed[url.path];items=data.get(field)
        if not isinstance(items,list) or any(k in data for k in ('next_cursor','has_more','next_page')):raise ValueError('unreviewed/continuing catalog response')
        endpoints[url.path]=len(items);endpoint_ids=set()
        for item in items:
            mid=item.get('id');aliases=item.get('aliases');output=item.get('output_modalities')
            if not isinstance(mid,str) or canonical_id(mid)!=mid or item.get('object')!='model' or item.get('owned_by')!='xai' or not isinstance(aliases,list) or any(not isinstance(a,str) or canonical_id(a)!=a for a in aliases) or len(aliases)!=len(set(aliases)):raise ValueError('unqualified native model/owner/aliases')
            if output is not None and (not isinstance(output,list) or not output or not set(output)<={'text','image','video','audio'}):raise ValueError('unreviewed model output modalities')
            if modality and (output is None or modality not in output):raise ValueError('typed endpoint and explicit output conflict')
            if mid in endpoint_ids:raise ValueError('duplicate literal model in one endpoint')
            endpoint_ids.add(mid)
            prior=models.get(mid)
            if prior is not None and sorted(aliases)!=prior['aliases']:raise ValueError('inconsistent alias declarations across catalog endpoints')
            row=models.setdefault(mid,dict(model_id=mid,owned_by='xai',aliases=[],output_declarations=[],sources=[]))
            row['aliases']=sorted(set(row['aliases'])|set(aliases))
            if output is not None:row['output_declarations'].append(sorted(output))
            row['sources'].append(dict(source_url=doc['url'],source_sha256=doc['sha256'],capture_path=doc.get('capture_path')))
            for alias in aliases:
                if alias in alias_targets and alias_targets[alias]!=mid:raise ValueError('conflicting literal alias targets')
                if alias in alias_targets and alias_targets[alias]!=mid:raise ValueError('conflicting literal alias targets')
                alias_targets[alias]=mid
        if url.path=='/v1/models':base_ids=endpoint_ids
        else:detail_ids.update(endpoint_ids)
    if base_ids is not None and detail_ids-base_ids:raise ValueError('typed models absent from account all-model list')
    if '/v1/models' not in endpoints:raise ValueError('all-models account list required')
    for mid,row in models.items():
        declarations={tuple(x) for x in row['output_declarations']}
        row['output_modalities']=list(next(iter(declarations))) if len(declarations)==1 else []
        row['output_status']='verified' if len(declarations)==1 else 'unknown_or_conflicting'
        row['lifecycle_status']='account_listed_not_history_or_retirement_proof'
    alias_targets=direct_alias_map(alias_targets.items(),known_ids=models,aliases_distinct_from_canonicals=True)
    return dict(models=list(models.values()),direct_alias_map=alias_targets,endpoints=endpoints,missing_typed_endpoints=sorted(set(allowed)-set(endpoints)),population='authenticating_API_key_available_models',global_universe_verified=False,subscription_verified=False,historical_lifecycle_verified=False)
