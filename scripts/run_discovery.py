#!/usr/bin/env python3
"""Fixed fetch -> raw capture -> literal-ID extraction -> diff -> durable ledger.

The full monitored directory remains PARTIAL. This is executable plumbing, NOT proof
of full directory coverage or a connected routine. No automatic data/PR writes.
"""
import argparse,base64,datetime as dt,hashlib,json,pathlib,re,subprocess,sys
import urllib.request,urllib.error
from urllib.parse import urljoin,urlparse
import catalog_diff as c
import discovery_adapters as adapters
import discovery_bridges as bridges
from concurrent.futures import ThreadPoolExecutor
ROOT=pathlib.Path(__file__).resolve().parents[1]
ADAPTER_VERSION='discovery-adapters/10-published-catalog-certification'
OpenAICards=adapters.OpenAICards
class LimitedPublicRedirect(urllib.request.HTTPRedirectHandler):
    """Follow a short chain of public official documentation redirects only."""
    def __init__(self, allow_hosts, max_hops=3):
        super().__init__(); self.allow_hosts=set(allow_hosts); self.max_hops=max_hops; self.chain=[]
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target=urljoin(req.full_url, newurl); parsed=urlparse(target)
        self.chain.append({'from':req.full_url,'status':code,'location':headers.get('Location'),'resolved':target})
        if len(self.chain)>self.max_hops: raise ValueError('Official redirect budget exceeded')
        if parsed.scheme!='https' or parsed.username or parsed.password or parsed.hostname not in self.allow_hosts:
            raise ValueError('Refusing non-public or off-allowlist redirect to '+target)
        return urllib.request.Request(target, headers=dict(req.header_items()), method='GET')

def digest(body):return hashlib.sha256(body).hexdigest()
def command(args):
    result=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=30)
    if result.returncode:raise RuntimeError('Command failed ('+str(result.returncode)+'): '+result.stderr.strip()[-2000:])
    return result.stdout.strip()
def code_identity(expected):
    sha=command(['git','rev-parse','HEAD'])
    if sha!=expected:raise ValueError('Code SHA differs from expected version')
    if command(['git','status','--porcelain','--','scripts','data/discovery-scopes.json','data/discovery-sources.json','data/public-price-evidence.json','data/evidence/public-prices']):
        raise ValueError('Discovery implementation/config has uncommitted changes')
    return sha

def remote_main():
    prefix='repos/liki-0814/llm-pricing/'
    sha=command(['gh','api',prefix+'commits/main','--jq','.sha'])
    if not re.fullmatch('[0-9a-f]{40}',sha):raise ValueError('Invalid remote main SHA')
    encoded=command(['gh','api',prefix+'contents/data/prices.json?ref='+sha,'--jq','.content'])
    body=base64.b64decode(encoded,validate=False)
    return json.loads(body),sha,digest(body)

def validate_sources(config,manifest):
    if config.get('version')!=1 or config.get('adapter_version')!=ADAPTER_VERSION:raise ValueError('Unsupported sources/adapter version')
    expected=digest(json.dumps(manifest,sort_keys=True).encode())
    if config.get('scope_manifest_sha256')!=expected:raise ValueError('Sources/scope manifest version mismatch')
    seen=set()
    for source in config['sources']:
        sid=source['id']
        if not re.fullmatch('[a-z0-9][a-z0-9-]*',sid) or sid in seen:raise ValueError('Invalid/duplicate source id')
        seen.add(sid)
        if not c.official_url(source['url'],source['vendor'],source['channel'],manifest):raise ValueError('Source URL is not approved for original vendor/channel')
        if source.get('adapter') not in adapters.ADAPTERS:raise ValueError('Unsupported/unreviewed adapter')
        if source.get('role') not in ('catalog','price','detail','lifecycle'):raise ValueError('Explicit source role required')
        if not source.get('modalities'):raise ValueError('Source modalities required')

def fetch_source(source, allow_hosts):
    request=urllib.request.Request(source['url'],headers={'User-Agent':'llm-pricing-public-discovery/1','Accept':'*/*'})
    handler=LimitedPublicRedirect(allow_hosts)
    with urllib.request.build_opener(handler).open(request,timeout=25) as response:
        if response.status!=200:raise ValueError('Non-200 source response')
        body=response.read(8*1024*1024+1)
        if len(body)>8*1024*1024:raise ValueError('Source exceeds 8MiB capture limit')
        return body,dt.datetime.now(dt.timezone.utc).isoformat(), {'final_url':response.geturl(),'redirects':handler.chain,
            'content_encoding':response.headers.get('Content-Encoding')}

def parse_source(body,source,observed_at):
    raw,text=adapters.decode_body(body)
    records,reseller,notes=adapters.parse(source['adapter'], raw, source)
    for row in records+reseller:row['line_basis']='adapter:'+source['adapter']
    proof=adapters.kimi_code_proof(raw,source,records) if source['adapter']=='kimi_code_catalog' else {'verified':False}
    if source['adapter']=='kimi_model_tables':proof=bridges.kimi_payg_proof(text,source,records)
    if source['adapter']=='zai_openapi_models':
        _,proof=bridges.zai_request_models(text)
        if (source.get('vendor'),source.get('channel'),source.get('url'),source.get('role'),source.get('modalities'))!=('智谱 Z.ai','pay_as_you_go','https://docs.z.ai/openapi.json','catalog',['text','image']):proof['verified']=False
    if source['adapter']=='deepseek_model_row':
        _,proof=adapters.text_contracts.deepseek_contract(text,source)
    if source['adapter']=='hunyuan_invocation_tables':
        scoped,resold,proof=adapters.text_contracts.hunyuan_text_contract(text,source)
        text_ids={row['model_id'] for row in scoped}
        if proof['verified'] and not text_ids.issubset({row.get('model_id') for row in records}):
            proof.update(verified=False,error='native text ID missing from full retained invocation extraction')
        if proof['verified'] and any(not adapters.text_contracts.native_hunyuan_identity(row) for row in records):
            proof.update(verified=False,error='retained native observation lacks paired native brand/invocation evidence')
        for row in records:row['text_scope_member']=row.get('model_id') in text_ids
        proof['text_record_count']=len(scoped)
        # Preserve all pre-existing non-text raw observations; this proof covers
        # only the two explicit text-output sections, not extra monitored scopes.
        if proof['verified']:proof['expected_record_count']=len(records)
    complete=proof['verified']
    errors=[] if complete else ['adapter_partial_not_full_enumeration']+list(notes)

    return dict(_extraction_text=text,vendor=source['vendor'],channel=source['channel'],role=source['role'],
        source_url=source['url'],observed_at=observed_at,complete=complete,
        fetch_status='ok',extraction_status='ok' if complete else 'partial',
        errors=errors,records=records,reseller_records=reseller,
        coverage_evidence=dict(source_url=source['url'],modalities=source['modalities'],
            enumeration_verified=complete,pagination_complete=complete,expected_record_count=proof.get('expected_record_count'),
            native_identity_verified=complete,proof=proof))

def bridge_google(snapshot,source,capture_dir,replay_dir=None):
    """At most64 native detail bodies, root links plus one direct Versions wave.
    Replay never falls back to HTTP; absent/invalid bodies leave scoped proof closed.
    """
    g=adapters.google_contracts;docs={}
    try:
        _,directory=g.directory(snapshot['_extraction_text'])
        urls=directory['required_detail_urls']
        def child(url):
            sid=source['id']+'-detail-'+digest(url.encode())[:16]
            try:
                if not g.allowed_detail(url):raise ValueError('unapproved native detail URL')
                if replay_dir is None:
                    body,at,extra=fetch_source({'url':url},{'aistudio.google.com'})
                    meta=dict(url=url,observed_at=at,sha256=digest(body),http_status=200,capture_kind='http_body',mode='fresh',**extra)
                else:
                    meta=json.loads((replay_dir/(sid+'.json')).read_text());body=(replay_dir/(sid+'.body')).read_bytes()
                    if meta['url']!=url or meta['sha256']!=digest(body) or meta.get('http_status')!=200:raise ValueError('Google detail replay provenance invalid')
                    meta=dict(meta,mode='replay')
                (capture_dir/(sid+'.body')).write_bytes(body);c.atomic_json(capture_dir/(sid+'.json'),meta)
                _,text=adapters.decode_body(body)
                return url,dict(text=text,source_url=url,source_sha256=meta['sha256'],observed_at=meta['observed_at'],capture_path=str(capture_dir/(sid+'.body')))
            except Exception as error:
                failure=dict(url=url,error=type(error).__name__+': '+str(error));c.atomic_json(capture_dir/(sid+'.json'),failure)
                return url,dict(source_url=url,**failure)
        if len(urls)>64:raise ValueError('Google native detail budget exceeded64')
        docs.update(ThreadPoolExecutor(max_workers=6).map(child,urls))
        refs=set().union(*(g.version_links(doc['text']) for doc in docs.values()))
        additional=sorted(refs-set(docs))
        if len(docs)+len(additional)>64:raise ValueError('Google total detail budget exceeded64')
        docs.update(ThreadPoolExecutor(max_workers=6).map(child,additional))
        records,proof=g.prove(snapshot['_extraction_text'],source,docs)
        if proof['verified']:
            snapshot.update(records=records,complete=True,extraction_status='ok',errors=[])
            snapshot['coverage_evidence'].update(modalities=proof['modalities'],enumeration_verified=True,pagination_complete=True,native_identity_verified=True,expected_record_count=proof['expected_record_count'],proof=proof)
        else:snapshot['coverage_evidence']['proof']=proof;snapshot['errors'].append('Google scoped proof: '+proof.get('error','unverified'))
    except (ValueError,KeyError,TypeError,AttributeError,StopIteration) as error:
        snapshot['coverage_evidence']['proof']={'verified':False,'error':str(error)}
        snapshot['errors'].append('Google scoped proof: '+str(error))
    snapshot['detail_captures']=[{k:v for k,v in doc.items() if k!='text'} for doc in docs.values()]
    return snapshot


def bridge_catalog(snapshot,source,capture_dir,replay_dir=None):
    """One bounded fetch per official linked Markdown page. Every child is captured.
    Missing child/ID leaves its entity pending; no saved-body fallback in live mode.
    """
    if source['adapter']=='google_endpoint_tables':return bridge_google(snapshot,source,capture_dir,replay_dir)
    if source['adapter'] not in ('openai_markdown_bridged','anthropic_markdown_bridged','minimax_model_list'):return snapshot
    urls=sorted({row.get('detail_url') for row in snapshot['records'] if row.get('detail_url')
                 and bridges.allowed_detail(row['detail_url'],source['vendor'])
                 and not (source['vendor']=='MiniMax' and '/speech-' in row['detail_url'])})
    if len(urls)>150:
        snapshot['errors'].append('detail_budget_exceeded_150');return snapshot
    def child(url):
        sid=source['id']+'-detail-'+digest(url.encode())[:16]
        try:
            if replay_dir is None:
                body,at,extra=fetch_source({'url':url},{urlparse(url).hostname})
                meta=dict(url=url,observed_at=at,sha256=digest(body),http_status=200,capture_kind='http_body',mode='fresh',**extra)
            else:
                meta=json.loads((replay_dir/(sid+'.json')).read_text());body=(replay_dir/(sid+'.body')).read_bytes()
                if meta['url']!=url or meta['sha256']!=digest(body) or meta.get('http_status')!=200:raise ValueError('detail replay provenance invalid')
                meta=dict(meta,mode='replay')
            (capture_dir/(sid+'.body')).write_bytes(body);c.atomic_json(capture_dir/(sid+'.json'),meta)
            raw,text=adapters.decode_body(body);(capture_dir/(sid+'.txt')).write_text(text)
            fn={'OpenAI':bridges.openai_ids,'Anthropic':bridges.anthropic_ids,'MiniMax':bridges.minimax_ids}[source['vendor']]
            return url,dict(ids=fn(text),source_url=url,observed_at=meta['observed_at'],source_sha256=meta['sha256'],capture_path=str(capture_dir/(sid+'.body')))
        except Exception as error:
            failed=dict(url=url,error=type(error).__name__+': '+str(error));c.atomic_json(capture_dir/(sid+'.json'),failed);return url,dict(ids=[],**failed)
    docs=dict(ThreadPoolExecutor(max_workers=6).map(child,urls))
    snapshot['detail_captures']=list(docs.values());expanded=[]
    for row in snapshot['records']:
        detail=docs.get(row.get('detail_url'));ids=detail.get('ids',[]) if detail else []
        if source['vendor']=='MiniMax':ids=[mid for mid in ids if mid==row.get('display_name')]
        if row.get('api_id_explicit') or not ids:expanded.append(row);continue
        for mid in ids:
            expanded.append(dict(row,model_id=mid,literal_id=mid,api_id_explicit=True,catalog_observation=False,
                identity_error=None,scope_status='explicit_official_detail_id; directory_channel_review_pending',
                identity_evidence={k:v for k,v in detail.items() if k!='ids'}))
    snapshot['records']=expanded
    snapshot['errors'].append('bridged_literal_IDs:%d; remaining_pending:%d' % (sum(x.get('api_id_explicit') is True for x in expanded),sum(x.get('api_id_explicit') is not True for x in expanded)))
    # Bridging alone is not a proof of channel attribution or exhaustive scoped enumeration.
    return snapshot

def apply_anthropic_observations(inventories,capture_dir):
    """Consume only this attempt's hash-checked native captures, never an old sidecar.
    Partial observations are useful; they do not certify exhaustive scope coverage.
    """
    import discovery_anthropic_contracts as native
    root=next((s for s in inventories if s.get('source_url')==native.ROOT),None)
    if not root:return
    def captured(snap):
        if not snap or snap.get('fetch_status')!='ok':raise ValueError('same-attempt source absent/failed')
        path=pathlib.Path(snap['capture_path'])
        if path.resolve().parent!=capture_dir.resolve():raise ValueError('capture is outside current attempt')
        body=path.read_bytes()
        if digest(body)!=snap['source_sha256']:raise ValueError('capture hash changed')
        _,text=adapters.decode_body(body)
        return dict(text=text,source_url=snap['source_url'],source_sha256=snap['source_sha256'],observed_at=snap['observed_at'],capture_path=str(path))
    def source(url):
        snap=next((s for s in inventories if s.get('source_url')==url),None)
        try:return captured(snap)
        except (ValueError,KeyError,OSError):return None
    docs=[];capture_errors=[]
    for child in root.get('detail_captures',[]):
        try:
            if child.get('error'):raise ValueError(child['error'])
            docs.append(captured(dict(child,fetch_status='ok')))
        except (ValueError,KeyError,OSError) as e:capture_errors.append(str(e))
    root_doc=source(native.ROOT);status=source(native.STATUS);release=source(native.NOTES)
    rows,proof=native.observe(root_doc,docs,status,release)
    if status:
        try:
            status_rows,_=native.aggregate(native.status_claims(status))
            next(s for s in inventories if s.get('source_url')==native.STATUS)['records']=status_rows
        except (ValueError,KeyError,TypeError):pass  # The partial source failure is recorded in proof.
    proof['errors']+=capture_errors
    if capture_errors:proof['structures_verified']=False
    # Missing/failed pieces are never interpreted as evidence of absence.
    root.update(records=rows,complete=False,extraction_status='partial')
    root['coverage_evidence'].update(proof=proof,enumeration_verified=False,pagination_complete=False,native_identity_verified=False,expected_record_count=None)
    root['errors'].append('native observation union retained; scope completeness remains unproven')

def apply_minimax_observations(inventories,capture_dir,replay_dir=None):
    """Same-attempt native directory + finite indexed request schemas; replay is offline."""
    import discovery_minimax_contracts as native
    root=next((x for x in inventories if (x.get('vendor'),x.get('channel'),x.get('source_url'),x.get('role'))==('MiniMax','pay_as_you_go',native.ROOT,'catalog')),None)
    if not root:return
    docs={}
    def child(url):
        sid='minimax-contract-'+digest(url.encode())[:16]
        try:
            if replay_dir is None:
                body,at,extra=fetch_source({'url':url},{'platform.minimax.io'})
                meta=dict(url=url,observed_at=at,sha256=digest(body),http_status=200,capture_kind='http_body',mode='fresh',**extra)
            else:
                meta=json.loads((replay_dir/(sid+'.json')).read_text());body=(replay_dir/(sid+'.body')).read_bytes()
                if meta['url']!=url or meta['sha256']!=digest(body) or meta.get('http_status')!=200:raise ValueError('request schema replay provenance invalid')
                c.parse_time(meta['observed_at']);meta=dict(meta,mode='replay')
            (capture_dir/(sid+'.body')).write_bytes(body);c.atomic_json(capture_dir/(sid+'.json'),meta)
            _,text=adapters.decode_body(body);(capture_dir/(sid+'.txt')).write_text(text)
            return url,dict(text=text,source_url=url,observed_at=meta['observed_at'],source_sha256=meta['sha256'],capture_path=str(capture_dir/(sid+'.body')))
        except Exception as error:
            failed=dict(source_url=url,error=type(error).__name__+': '+str(error));c.atomic_json(capture_dir/(sid+'.json'),failed)
            return url,failed
    try:
        path=pathlib.Path(root['capture_path']);body=path.read_bytes()
        if path.resolve().parent!=capture_dir.resolve() or digest(body)!=root['source_sha256'] or root['fetch_status']!='ok':raise ValueError('directory same-attempt hash invalid')
        _,text=adapters.decode_body(body)
        docs[native.ROOT]=dict(text=text,source_url=native.ROOT,source_sha256=root['source_sha256'],capture_path=str(path),observed_at=root['observed_at'])
        key,index=child(native.INDEX);docs[key]=index
        urls=native.indexed_specs(index['text'])
        if len(urls)>16:raise ValueError('native request schema budget exceeded16')
        docs.update(ThreadPoolExecutor(max_workers=6).map(child,urls))
        scoped=native.prove(root,docs)
        for snap in scoped:snap['contract_captures']=[{k:v for k,v in doc.items() if k!='text'} for doc in docs.values()]
        position=inventories.index(root);inventories[position:position+1]=scoped
    except (ValueError,KeyError,TypeError,OSError) as error:
        root.setdefault('errors',[]).append('MiniMax scoped request contract: '+str(error))
        root['contract_captures']=[{k:v for k,v in doc.items() if k!='text'} for doc in docs.values()]


def apply_native_claims(inventories,capture_dir):
    """Consume only current hash-checked captures; no fetch, research sidecar or ID guesses."""
    import discovery_native_claims as native
    def captured(meta):
        path=pathlib.Path(meta['capture_path']);body=path.read_bytes()
        if path.resolve().parent!=capture_dir.resolve() or digest(body)!=meta['source_sha256']:raise ValueError('native claim capture hash/path invalid')
        c.parse_time(meta['observed_at']);_,text=adapters.decode_body(body)
        return dict(text=text,source_url=meta['source_url'],source_sha256=meta['source_sha256'],capture_path=str(path),observed_at=meta['observed_at'],vendor=meta.get('vendor'),channel=meta.get('channel'),catalog_source_url=meta['source_url'])
    for snap in inventories:
        key=(snap['vendor'],snap['channel'],snap['source_url'],snap['role'])
        if key not in (('OpenAI','pay_as_you_go',native.OA,'catalog'),('xAI','pay_as_you_go',native.XAI,'catalog')):continue
        if snap.get('fetch_status')!='ok':continue
        try:root=captured(snap)
        except (OSError,ValueError,KeyError) as error:
            snap.setdefault('errors',[]).append('native claims root: '+str(error));continue
        legacy=snap['records'];records=[];proofs=[];errors=[]
        if snap['vendor']=='OpenAI':
            details={x.get('source_url'):x for x in snap.get('detail_captures',[]) if x.get('source_url')}
            entities={}
            for row in legacy:
                url=row.get('detail_url')
                if bridges.allowed_detail(url or '', 'OpenAI'):entities.setdefault(url,row)
                elif row.get('api_id_explicit') and row.get('model_id'):
                    mid=row['model_id'];line=row.get('line');quote=root['text'].splitlines()[line-1] if isinstance(line,int) and 0<line<=len(root['text'].splitlines()) else row.get('id_evidence','directory literal ID')
                    claims=[native.claim(root,mid,'identity',role='inline_directory_literal',line=line,quote=quote),native.claim(root,mid,'native_channel',status='unknown',reason='inline ID has no bound native endpoint/channel evidence'),native.claim(root,mid,'output',values=None,reason='inline ID has no output declaration')]
                    records.append(dict(row,**native.project(claims)))
                else:records.append(row)
            for url,entity in entities.items():
                try:
                    doc=captured(details[url]);rows,proof=native.openai_detail(doc,entity)
                    if not rows:raise ValueError('no literal native identity declarations')
                    records.extend(dict(entity,**row) for row in rows);proofs.append(dict(source_url=url,**proof))
                except (ValueError,KeyError,OSError,TypeError) as error:
                    errors.append(dict(source_url=url,error=str(error)))
                    records.extend(row for row in legacy if row.get('detail_url')==url)
        else:
            typed=native.xai_records(root);mapped={r['model_id'] for r in typed};records.extend(typed)
            for row in legacy:
                if row.get('model_id') not in mapped:records.append(row)
            proofs.append(dict(source_url=native.XAI,typed_record_count=len(typed),catalog_universe='public priced subset only',alias_enumeration='generic templates are not literal aliases'))
        snap['records']=records
        snap['coverage_evidence']['native_claim_consumption']=dict(method='source_qualified_per_ID_channel_output_claims',source_proofs=proofs,errors=errors,
            typed_record_count=sum(bool(row.get('native_claims')) for row in records),
            unknown_channel_ids=sorted({row['model_id'] for row in records if row.get('model_id') and row.get('channel_applicability')!='verified'}),
            unknown_output_ids=sorted({row['model_id'] for row in records if row.get('model_id') and not row.get('output_modalities')}),
            completeness='NOT CERTIFIED: observation consumption is not official full catalog/alias/lifecycle enumeration')
        # Typed observations do not repair missing external universes/entitlements.
        snap['complete']=False


def apply_public_catalog_observations(inventories,capture_dir,replay_dir=None):
    """Published documents only; bounded indexes, no cookies, credentials or internal APIs."""
    import discovery_document_catalogs as public
    import discovery_universe_contracts as universe
    docs={};blocked_hosts=set()
    for snapshot in inventories:
        path=pathlib.Path(snapshot.get('capture_path','/nonexistent'))
        if path.is_file():
            _,root_text=adapters.decode_body(path.read_bytes())
            if public.access_gate(root_text):
                blocked_hosts.add(urlparse(snapshot['source_url']).hostname)
                snapshot['access_state']='HTTP_200_access_gate_NOT_catalog'
                snapshot.setdefault('errors',[]).append('captured_access_gate_not_an_empty_directory')
    def child(url):
        sid='published-catalog-'+digest(url.encode())[:16];doc={};meta={}
        try:
            if replay_dir is None and urlparse(url).hostname in blocked_hosts:raise ValueError('host access gate already observed; further network requests stopped')
            if replay_dir is None:
                body,at,extra=fetch_source({'url':url},{urlparse(url).hostname});meta=dict(url=url,observed_at=at,sha256=digest(body),http_status=200,capture_kind='http_body',mode='fresh',**extra)
            else:
                meta=json.loads((replay_dir/(sid+'.json')).read_text());body=(replay_dir/(sid+'.body')).read_bytes()
                if meta.get('url')!=url or meta.get('sha256')!=digest(body) or meta.get('http_status')!=200:raise ValueError('published catalog replay provenance invalid')
                meta=dict(meta,mode='replay')
            c.parse_time(meta['observed_at']);_,text=adapters.decode_body(body)
            (capture_dir/(sid+'.body')).write_bytes(body);c.atomic_json(capture_dir/(sid+'.json'),meta)
            doc=dict(text=text,source_url=url,source_sha256=meta['sha256'],capture_path=str(capture_dir/(sid+'.body')),observed_at=meta['observed_at'])
            if public.access_gate(text):
                blocked_hosts.add(urlparse(url).hostname)
                raise ValueError('public document access gate; no retry/header substitution')
            return url,doc
        except Exception as error:
            if getattr(error,'code',None) in (401,403,429):blocked_hosts.add(urlparse(url).hostname)
            failed=dict({k:v for k,v in doc.items() if k!='text'},source_url=url,error=type(error).__name__+': '+str(error),fetch_status='ok' if meta.get('http_status')==200 else 'failed')
            if not meta:c.atomic_json(capture_dir/(sid+'.json'),failed)
            return url,failed
    qwen=next((x for x in inventories if (x.get('vendor'),x.get('channel'),x.get('source_url'))==('阿里云 Qwen','pay_as_you_go',public.QWEN+'models') and x.get('fetch_status')=='ok'),None)
    if qwen is not None:
        docs.update(ThreadPoolExecutor(max_workers=3).map(child,public.QWEN_INDEXES))
        entities=[];index_proofs=[];failures=[]
        for url in public.QWEN_INDEXES:
            try:
                doc=docs[url];rows,proof=public.qwen_index(doc['text'],url);entities.extend(dict(row,index_url=url) for row in rows);index_proofs.append(dict(proof,source_sha256=doc['source_sha256'],capture_path=doc['capture_path']))
            except (ValueError,KeyError,TypeError) as error:failures.append(dict(source_url=url,error=str(error)))
        urls=sorted({e['detail_url'] for e in entities})
        if len(urls)>180:failures.append(dict(error='published Qwen detail budget exceeded180'));urls=[]
        docs.update(ThreadPoolExecutor(max_workers=6).map(child,urls));observed=[]
        for entity in entities:
            doc=docs[entity['detail_url']]
            try:observed.extend(public.qwen_details(doc,entity))
            except (ValueError,KeyError,TypeError) as error:
                failures.append(dict(source_url=entity['detail_url'],error=str(error)));observed.append(dict(model_id=None,api_id_explicit=False,catalog_observation=True,display_name=entity['display_name'],detail_url=entity['detail_url'],catalog_quote=entity['quote'],scope_status='pending_qualified_detail',observation_status='access_blocked' if 'access_blocked' in str(error) else 'unsupported_document',source_error=str(error)))
        qwen['records'].extend(observed)
        qwen['published_catalog_proof']=dict(method='official_published_category_indexes_and_literal_request_output_details',index_proofs=index_proofs,category_rows=len(entities),unique_detail_documents=len(urls),observations=len(observed),known_output_observations=sum(bool(r.get('output_modalities')) for r in observed),failures=failures,population='published_categories_not_a_claimed_global_native_universe',native_provider_unknown=sum(r.get('native_vendor_status')!='verified_explicit_provider' for r in observed),aliases='unknown: no direct map inferred from snapshots/model-name patterns',lifecycle='unknown where not declared',api_alternative='https://www.alibabacloud.com/help/en/model-studio/list-models; authenticated account/region/filter only, never automatically global')
        qwen['public_catalog_captures']=[{k:v for k,v in d.items() if k!='text'} for d in docs.values()]
        qwen['complete']=False
    subscription=next((x for x in inventories if (x.get('vendor'),x.get('channel'))==('xAI','subscription')),None)
    if subscription is not None:
        index_url,index=child(public.XAI_INDEX);subdocs={index_url:index};models=[];failures=[];urls=[]
        try:urls=public.xai_subscription_urls(index['text'])
        except (KeyError,ValueError) as error:failures.append(dict(source_url=index_url,error=str(error)))
        subdocs.update(ThreadPoolExecutor(max_workers=6).map(child,urls))
        for url in urls:
            try:
                rows=public.xai_subscription_catalog(subdocs[url]);models.extend(rows)
                if rows:
                    doc=subdocs[url]
                    inventories.append(dict(vendor='xAI',channel='subscription',role='catalog',source_url=url,observed_at=doc['observed_at'],source_sha256=doc['source_sha256'],capture_path=doc['capture_path'],records=rows,complete=False,fetch_status='ok',extraction_status='partial',errors=['native_catalog_rows_observed_without_global_alias_lifecycle_closure'],coverage_evidence={'modalities':['text'],'enumeration_verified':False,'pagination_complete':False}))
            except (ValueError,KeyError,TypeError) as error:failures.append(dict(source_url=url,error=str(error)))
        subscription['native_subscription_enumeration']=dict(method='published_Build_and_subscription_index_sections_only',required_document_count=len(urls),read_document_count=sum('text' in subdocs[u] for u in urls),literal_native_catalog_rows=len(models),failures=failures,empty_state='catalog_not_published_or_unread_NOT_verified_empty' if not models else 'partial_native_catalog_observed',excluded_evidence='config examples, BYOK/API-key/custom endpoints, generic placeholders and PAYG price IDs are not subscription membership',runtime_catalog_evidence=[dict(source_url=u,quote=line) for u,d in subdocs.items() for line in d.get('text','').splitlines() if 'GROK_MODELS_LIST_URL' in line or 'GROK_DEFAULT_MODEL' in line])
        subscription['public_catalog_captures']=[{k:v for k,v in d.items() if k!='text'} for d in subdocs.values()]
    for snap in inventories:
        if snap.get('coverage_evidence',{}).get('native_claim_consumption'):
            path=pathlib.Path(snap['capture_path']);raw=path.read_bytes()
            if path.resolve().parent!=capture_dir.resolve() or digest(raw)!=snap['source_sha256']:raise ValueError('universe root capture provenance mismatch')
            _,text=adapters.decode_body(raw);root_document=dict(text=text,**{k:snap[k] for k in ('source_url','source_sha256','capture_path','observed_at')})
            extra=[s for s in inventories if s is not snap and s['vendor']==snap['vendor'] and s['channel']==snap['channel'] and s.get('role')=='catalog']
            snap['scope_certificates']=universe.native_observation_certificates(snap,root_document,extra)
            required=list(snap.get('coverage_evidence',{}).get('modalities') or [])
            certified=[r['modality'] for r in snap['scope_certificates'] if r['complete']]
            if required and set(certified)==set(required):
                snap.update(complete=True,extraction_status='ok',errors=[])
                snap['coverage_evidence'].update(modalities=required,enumeration_verified=True,pagination_complete=True,native_identity_verified=True,expected_record_count=len(snap['records']))
        elif snap is qwen:
            proof=qwen['published_catalog_proof'];snap['scope_certificates']=[universe.scope_certificate(snap['vendor'],snap['channel'],m,snap['records'],population=universe.unknown('published categories do not assert complete native/legacy provider universe'),pagination=universe.unknown('published linked pages read, but Model Plaza/API regional terminal remains unproved',read=proof['unique_detail_documents'],failures=proof['failures']),alias_enumeration=universe.unknown('no complete direct alias declaration'),lifecycle=universe.unknown('historical lifecycle set not declared')) for m in ('text','image','video')]

def execute(config,manifest,database,capture_dir,replay_dir=None,public_price_ledger=None,public_price_root=None):
    validate_sources(config,manifest)
    capture_dir.mkdir(parents=True,exist_ok=False);inventories=[]
    for source in config['sources']:
        sid=source['id'];now=dt.datetime.now(dt.timezone.utc).isoformat();stage='fetch';http_status=None
        try:
            if replay_dir is None:
                hosts={urlparse(source['url']).hostname}
                for item in manifest['scopes']:
                    if (item['vendor'],item['channel'])==(source['vendor'],source['channel']): hosts.update(item.get('official_hosts') or [])
                body,observed,fetch_meta=fetch_source(source,hosts);http_status=200;capture_kind='http_body'
            else:
                meta=json.loads((replay_dir/(sid+'.json')).read_text());body=(replay_dir/(sid+'.body')).read_bytes()
                if meta['url']!=source['url'] or meta['sha256']!=digest(body):raise ValueError('Replay source provenance mismatch')
                http_status=meta.get('http_status');capture_kind=meta.get('capture_kind','http_body')
                if http_status!=200 and not (http_status is None and capture_kind=='tool_text'):raise ValueError('Replay was not a successful source capture')
                observed=meta['observed_at'];c.parse_time(observed)
            stage='capture'
            (capture_dir/(sid+'.body')).write_bytes(body)
            meta=dict(url=source['url'],observed_at=observed,http_status=http_status,capture_kind=capture_kind,sha256=digest(body),mode='replay' if replay_dir else 'fresh')
            if replay_dir is None: meta.update(fetch_meta)
            c.atomic_json(capture_dir/(sid+'.json'),meta)
            stage='extract'
            snapshot=parse_source(body,source,observed)
            snapshot=bridge_catalog(snapshot,source,capture_dir,replay_dir)
            extracted=snapshot.pop('_extraction_text');(capture_dir/(sid+'.txt')).write_text(extracted)
            snapshot['extraction_path']=str(capture_dir/(sid+'.txt'))
            snapshot['extraction_sha256']=digest(extracted.encode())
            if http_status!=200:
                snapshot['fetch_status']='unverified';snapshot['errors'].append('tool_text_no_raw_http_status')
            snapshot.update(source_sha256=meta['sha256'],capture_path=str(capture_dir/(sid+'.body')))
        except Exception as error:
            snapshot=dict(vendor=source['vendor'],channel=source['channel'],role=source['role'],source_url=source['url'],observed_at=now,
                complete=False,fetch_status='ok' if http_status==200 else 'failed',extraction_status='failed',records=[],coverage_evidence={'modalities':source['modalities']},
                errors=[stage+': '+type(error).__name__+': '+str(error)])
            c.atomic_json(capture_dir/(sid+'.json'),snapshot)
        inventories.append(snapshot)
    all_urls={(row.get('detail_url') or '').removesuffix('.md') for snap in inventories if snap.get('source_url') in ('https://developers.openai.com/api/docs/models/all','https://developers.openai.com/api/docs/models/all.md') for row in snap.get('records') or []}
    for snap in inventories:
        if snap.get('source_url')=='https://developers.openai.com/api/docs/models' and all_urls:
            kept=[row for row in snap.get('records') or [] if (row.get('detail_url') or '').removesuffix('.md') not in all_urls]
            snap['records']=kept
            snap.setdefault('errors',[]).append('front_page_union_only_cards_absent_from_all:%d' % len(kept))
    apply_anthropic_observations(inventories,capture_dir)
    apply_minimax_observations(inventories,capture_dir,replay_dir)
    apply_native_claims(inventories,capture_dir)
    apply_public_catalog_observations(inventories,capture_dir,replay_dir)
    import public_price_facts
    from discovery_public_api_evidence import attach_api_evidence
    public_ledger=public_price_ledger if public_price_ledger is not None else public_price_facts.load()
    attach_api_evidence(inventories,public_ledger,public_price_root or public_price_facts.ROOT,manifest)
    from discovery_scope_projection import attach_scope_certificates
    attach_scope_certificates(inventories,manifest)
    public_price_facts.attach(inventories,public_ledger)
    c.atomic_json(capture_dir/'inventory.json',inventories)
    return inventories

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-dir',required=True)
    p.add_argument('--expected-code-sha',required=True)
    p.add_argument('--sources',default=str(ROOT/'data/discovery-sources.json'))
    p.add_argument('--scopes',default=str(c.DEFAULT_SCOPES))
    p.add_argument('--replay-dir',type=pathlib.Path,help='Offline verification only; never advances successful monitoring baseline')
    p.add_argument('--replay-database',type=pathlib.Path)
    p.add_argument('--public-price-capture-dir',type=pathlib.Path,help='Reviewed independent HTTP price captures; not a full-discovery fresh proof')
    p.add_argument('--catalog-export-dir',type=pathlib.Path,help='Offline-only original documented Qwen/xAI model catalog HTTP exports; never credentials or a fresh/global universe proof')
    args=p.parse_args();attempt=None
    try:
        attempt=c.begin_attempt(args.state_dir)
        sha=code_identity(args.expected_code_sha)
        manifest=json.loads(pathlib.Path(args.scopes).read_text());c.scope_manifest(manifest)
        config=json.loads(pathlib.Path(args.sources).read_text());validate_sources(config,manifest)
        if not args.replay_dir:
            for supplied,tracked in [(args.sources,'data/discovery-sources.json'),(args.scopes,'data/discovery-scopes.json')]:
                if pathlib.Path(supplied).read_text().strip()!=command(['git','show','HEAD:'+tracked]):
                    raise ValueError('Live discovery input differs from reviewed committed '+tracked)
        if args.replay_dir:
            body=args.replay_database.read_bytes();database=json.loads(body);main_sha=None;baseline_digest=digest(body)
        else:database,main_sha,baseline_digest=remote_main()
        captures=pathlib.Path(args.state_dir)/'captures'/attempt['run_id']
        import public_price_facts
        public_ledger=public_price_facts.load_capture(args.public_price_capture_dir) if args.public_price_capture_dir else public_price_facts.load()
        inventories=execute(config,manifest,database,captures,args.replay_dir,public_price_ledger=public_ledger,public_price_root=args.public_price_capture_dir or public_price_facts.ROOT)
        catalog_exports=None
        if args.catalog_export_dir:
            if not args.replay_dir:raise ValueError('offline catalog exports cannot participate in a fresh success baseline')
            import discovery_universe_contracts as universe
            pages=[]
            for meta_path in sorted(args.catalog_export_dir.glob('*.json')):
                meta=json.loads(meta_path.read_text());meta['body']=meta_path.with_suffix('.body').read_bytes();meta['capture_path']=str(meta_path.with_suffix('.body'));pages.append(meta)
            qwen_pages=[d for d in pages if urlparse(d.get('url','')).hostname!='api.x.ai']
            xai_pages=[d for d in pages if urlparse(d.get('url','')).hostname=='api.x.ai']
            catalog_exports=dict(qwen=universe.qwen_catalog_pages(qwen_pages) if qwen_pages else None,xai=universe.xai_catalog_exports(xai_pages) if xai_pages else None)
            import discovery_export_contracts as exports
            inventories.extend(exports.catalog_snapshots(pages,captures))
            from discovery_scope_projection import attach_scope_certificates
            attach_scope_certificates(inventories,manifest)
            c.atomic_json(captures/'inventory.json',inventories)
        previous=c.previous_success(args.state_dir)
        result=c.compare_catalogs(database,inventories,previous,scopes=manifest)
        import public_price_facts
        ledger=public_ledger
        public_price_facts.attach(inventories,ledger)
        c.atomic_json(captures/'inventory.json',inventories)
        c.atomic_json(captures/'public-price-evidence.json',ledger)
        result['public_price_evidence_ledger_path']=str(captures/'public-price-evidence.json')
        result['public_price_evidence']=public_price_facts.view(ledger)
        result['price_verification_is_not_scope_completion']=True
        result['scope_certificates']=[certificate for snapshot in inventories for certificate in snapshot.get('scope_certificates',[])]
        result['catalog_export_validation']=catalog_exports
        result['comparison_baseline_run_id']=previous.get('run_id') if previous else None
        result.update(code_sha=sha,adapter_version=ADAPTER_VERSION,sources_sha256=digest(pathlib.Path(args.sources).read_bytes()),
            baseline_branch='main' if not args.replay_dir else 'offline-unverified',baseline_commit=main_sha,
            database_sha256=baseline_digest,capture_dir=str(captures),run_mode='replay' if args.replay_dir else 'fresh')
        if args.replay_dir:
            result['status']='incomplete';result.setdefault('execution_notes',[]).append('offline_replay_not_a_fresh_monitoring_run')
    except Exception as error:
        result={'status':'error','discovery_verdict':'inconclusive_execution_failure','errors':[{'type':type(error).__name__,'message':str(error)}]}
    try:
        path=c.save_attempt(args.state_dir,result,attempt);result=json.loads(path.read_text());result['attempt_path']=str(path)
    except Exception as error:
        print(json.dumps({'status':'error','ledger_write_failed':str(error),'result':result},ensure_ascii=False));return 4
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['status']=='error':return 1
    if result['status']!='complete':return 2
    return 0 if result['baseline_update']=='advanced' else 3
if __name__=='__main__':raise SystemExit(main())
