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
ADAPTER_VERSION='discovery-adapters/4-literal-detail-bridges'
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
    if command(['git','status','--porcelain','--','scripts','data/discovery-scopes.json','data/discovery-sources.json']):
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
    complete=proof['verified']
    errors=[] if complete else ['adapter_partial_not_full_enumeration']+list(notes)

    return dict(_extraction_text=text,vendor=source['vendor'],channel=source['channel'],role=source['role'],
        source_url=source['url'],observed_at=observed_at,complete=complete,
        fetch_status='ok',extraction_status='ok' if complete else 'partial',
        errors=errors,records=records,reseller_records=reseller,
        coverage_evidence=dict(source_url=source['url'],modalities=source['modalities'],
            enumeration_verified=complete,pagination_complete=complete,expected_record_count=proof.get('expected_record_count'),
            native_identity_verified=complete,proof=proof))

def bridge_catalog(snapshot,source,capture_dir,replay_dir=None):
    """One bounded fetch per official linked Markdown page. Every child is captured.
    Missing child/ID leaves its entity pending; no saved-body fallback in live mode.
    """
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

def execute(config,manifest,database,capture_dir,replay_dir=None):
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
        inventories=execute(config,manifest,database,captures,args.replay_dir)
        previous=c.previous_success(args.state_dir)
        result=c.compare_catalogs(database,inventories,previous,scopes=manifest)
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
