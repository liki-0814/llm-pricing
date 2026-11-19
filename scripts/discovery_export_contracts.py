"""Documented account-catalog export ingestion. Pure validation; never networking/auth.

Exports are partial account/region observations, never global/subscription proof.
"""
import hashlib,json,re
from urllib.parse import urlsplit,parse_qs
from discovery_claim_contract import claim,project,parse_time
from discovery_universe_contracts import qwen_catalog_pages,xai_catalog_exports

XAI_PATHS={'/v1/models','/v1/language-models','/v1/image-generation-models','/v1/video-generation-models'}
QWEN_FILTERS={'page_no','page_size','providers','capabilities','inference_providers','language','name','model'}

def documented_export_url(url,vendor,channel):
    try:
        p=urlsplit(url or '')
        if p.scheme!='https' or p.username or p.password or p.port is not None or p.fragment or channel!='pay_as_you_go':return False
        if vendor=='xAI':return p.netloc=='api.x.ai' and p.path in XAI_PATHS and not p.query
        host=bool(re.fullmatch(r'[A-Za-z0-9-]+\.(?:cn-beijing|ap-southeast-1|cn-hongkong|eu-central-1|ap-northeast-1)\.maas\.aliyuncs\.com',p.netloc) or p.netloc=='dashscope-us.aliyuncs.com')
        return vendor=='阿里云 Qwen' and host and p.path=='/api/v1/models' and set(parse_qs(p.query,keep_blank_values=True))<=QWEN_FILTERS
    except (ValueError,TypeError):return False

def no_duplicate_keys(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate JSON object key')
        result[key]=value
    return result

def json_spans(text):
    """Actual JSON token spans by pointer; quotes are original bytes, not reserialization."""
    json.loads(text,object_pairs_hook=no_duplicate_keys);decoder=json.JSONDecoder();spans={}
    def whitespace(i):
        while i<len(text) and text[i].isspace():i+=1
        return i
    def value(i,path):
        i=whitespace(i);start=i
        if text[i]=='{':
            i=whitespace(i+1)
            while text[i]!='}':
                key,end=decoder.raw_decode(text,i);i=whitespace(end)
                if text[i]!=':':raise ValueError('JSON colon missing')
                i=whitespace(value(i+1,path+'/'+key.replace('~','~0').replace('/','~1')))
                if text[i]=='}':break
                if text[i]!=',':raise ValueError('JSON comma missing')
                i=whitespace(i+1)
            end=i+1
        elif text[i]=='[':
            i=whitespace(i+1);number=0
            while text[i]!=']':
                i=whitespace(value(i,path+'/'+str(number)));number+=1
                if text[i]==']':break
                if text[i]!=',':raise ValueError('JSON array comma missing')
                i=whitespace(i+1)
            end=i+1
        else:_,end=decoder.raw_decode(text,i)
        spans[path]=(start,end);return end
    value(0,'');return spans

def catalog_snapshots(documents,capture_dir):
    """Validate complete original exports, then produce source-bound partial rows.

    Model ownership/output/alias observations can be known while PAYG remains
    unknown. Available-to-key does not invent channel entitlement or history.
    """
    qwen=[d for d in documents if urlsplit(d.get('url','')).netloc!='api.x.ai'];xai=[d for d in documents if urlsplit(d.get('url','')).netloc=='api.x.ai']
    if qwen:qwen_catalog_pages(qwen)
    if xai:xai_catalog_exports(xai)
    snapshots=[]
    for doc in documents:
        vendor='xAI' if urlsplit(doc['url']).netloc=='api.x.ai' else '阿里云 Qwen';channel='pay_as_you_go'
        if not documented_export_url(doc['url'],vendor,channel) or doc.get('channel',channel)!=channel or doc.get('vendor',vendor)!=vendor:raise ValueError('export vendor/channel/origin mismatch')
        parse_time(doc.get('observed_at',''));raw=doc['body'];raw=raw.encode() if isinstance(raw,str) else raw
        if hashlib.sha256(raw).hexdigest()!=doc['sha256']:raise ValueError('export raw hash changed')
        text=raw.decode('utf-8');body=json.loads(text,object_pairs_hook=no_duplicate_keys);spans=json_spans(text)
        stem='catalog-export-'+hashlib.sha256(doc['url'].encode()).hexdigest()[:16];path=capture_dir/(stem+'.body');path.write_bytes(raw)
        metadata={k:v for k,v in doc.items() if k!='body'};metadata.update(capture_path=str(path),mode='offline_export_import');(capture_dir/(stem+'.json')).write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
        scoped=dict(source_url=doc['url'],source_sha256=doc['sha256'],capture_path=str(path),observed_at=doc['observed_at'],vendor=vendor,channel=channel,catalog_source_url=doc['url'])
        items=body.get('data',body.get('models')) if vendor=='xAI' else body['output']['models'];base='/data' if 'data' in body else '/models' if vendor=='xAI' else '/output/models';records=[]
        for number,item in enumerate(items):
            pointer=base+'/'+str(number);start,end=spans[pointer];quote=text[start:end];line=text.count('\n',0,start)+1;mid=item['id'] if vendor=='xAI' else item['model']
            native=item.get('owned_by')=='xai' if vendor=='xAI' else item.get('provider') in {'qwen','wan','happyhorse','qwen-domain-model'}
            source=dict(line=line,quote=quote,json_pointer=pointer)
            if not native:
                records.append(dict(model_id=None,observed_model_id=mid,api_id_explicit=False,catalog_observation=True,display_name=mid,scope_status='non_native_or_unknown_provider',identity_evidence=dict(scoped,**source),observed_provider=item.get('provider')));continue
            claims=[claim(scoped,mid,'identity',role='native_owner_literal_HTTP_catalog_field',**source),claim(scoped,mid,'lifecycle',status='listed',**source)]
            output=item.get('output_modalities') if vendor=='xAI' else item.get('inference_metadata',{}).get('response_modality');known={'Text':'text','Image':'image','Video':'video','Audio':'audio'}
            modes=output if vendor=='xAI' else [known[v] for v in output] if isinstance(output,list) and output and all(v in known for v in output) else None
            if modes:claims.append(claim(scoped,mid,'output',values=modes,**source))
            # Deliberately no native_channel claim: key-visible != proven PAYG.
            records.append(dict(model_id=mid,api_id_explicit=True,catalog_observation=False,identity_evidence=dict(scoped,**source),account_population='authenticating_key_region_filter',**project(claims)))
            if vendor=='xAI':
                for alias in item['aliases']:
                    aliases=[claim(scoped,alias,'identity',role='literal_alias_request_ID_in_native_model_HTTP_catalog',**source),claim(scoped,alias,'alias',status='direct',alias_of=mid,**source)]
                    if modes:aliases.append(claim(scoped,alias,'output',values=modes,**source))
                    records.append(dict(model_id=alias,api_id_explicit=True,catalog_observation=False,identity_evidence=dict(scoped,**source),account_population='authenticating_key_region_filter',**project(aliases)))
        snapshots.append(dict(vendor=vendor,channel=channel,source_url=doc['url'],source_sha256=doc['sha256'],capture_path=str(path),observed_at=doc['observed_at'],role='catalog',records=records,fetch_status='ok',extraction_status='partial',complete=False,errors=['offline_account_visible_export_NOT_global_native_alias_lifecycle_universe'],coverage_evidence=dict(modalities=['text','image','video'],source_url=doc['url'],enumeration_verified=False,pagination_complete=False,native_identity_verified=False,account_pagination_validated=True,expected_record_count=len(records))))
    return snapshots
