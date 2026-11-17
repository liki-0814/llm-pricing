#!/usr/bin/env python3
"""Fixed fetch -> raw capture -> literal-ID extraction -> diff -> durable ledger.

Current adapters are explicitly PARTIAL. This is executable plumbing, NOT proof
of full directory coverage or a connected routine. No automatic data/PR writes.
"""
import argparse,base64,datetime as dt,hashlib,json,pathlib,re,subprocess,sys
import urllib.request,urllib.error
from html.parser import HTMLParser
import catalog_diff as c
ROOT=pathlib.Path(__file__).resolve().parents[1]
ADAPTER_VERSION='discovery-adapters/1-partial'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
class VisibleText(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
        elif not self.hidden:
            if tag in ('p','div','tr','li','br','h1','h2','h3'):self.parts.append('\n')
            if tag=='code':self.parts.append('`')
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.hidden=max(0,self.hidden-1)
        elif not self.hidden and tag=='code':self.parts.append('`')
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)
class OpenAICards(HTMLParser):
    """Read public cards as display observations, NEVER infer API IDs from slugs."""
    def __init__(self):
        super().__init__();self.in_main=False;self.details=0;self.card=None;self.rows=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='main':self.in_main=True
        if not self.in_main:return
        if tag=='details':self.details+=1
        href=attrs.get('href','')
        if tag=='a' and href.startswith('/') and not href.startswith('//'):
            self.card={'detail_url':'https://developers.openai.com'+href,'api_id_explicit':False,
                'model_id':None,'catalog_section':'historical' if self.details else 'current',
                'scope_status':'requires_scope_review','line':self.getpos()[0],'card_text':[],
                'card_kind':'directory' if re.fullmatch(r'/api/docs/models/[^/?#]+',href) and href!='/api/docs/models/all' else 'supplemental',
                '_model_card':bool(re.fullmatch(r'/api/docs/models/[^/?#]+',href) and href!='/api/docs/models/all')}
        if tag=='img' and self.card is not None and attrs.get('src','').startswith('/images/api/models/icons/'):
            self.card['_model_card']=True;self.card['image_alt']=attrs.get('alt')
    def handle_data(self,data):
        if self.card is not None and data.strip():
            self.card.setdefault('display_name',data.strip());self.card['card_text'].append(data.strip())
    def handle_endtag(self,tag):
        if tag=='a' and self.card is not None:
            self.card['card_text']=' '.join(self.card['card_text'])
            if self.card.pop('_model_card'):self.rows.append(self.card)
            self.card=None
        if self.in_main and tag=='details':self.details=max(0,self.details-1)
        if tag=='main':self.in_main=False

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
        if source.get('adapter') not in ('explicit_id_labels_partial','openai_cards_partial'):raise ValueError('Unsupported/unreviewed adapter')
        if source.get('role') not in ('catalog','price','detail','lifecycle'):raise ValueError('Explicit source role required')
        if not source.get('modalities'):raise ValueError('Source modalities required')

def fetch_source(source):
    request=urllib.request.Request(source['url'],headers={'User-Agent':'llm-pricing-public-discovery/1'})
    with urllib.request.build_opener(NoRedirect).open(request,timeout=25) as response:
        if response.status!=200:raise ValueError('Non-200 source response')
        body=response.read(8*1024*1024+1)
        if len(body)>8*1024*1024:raise ValueError('Source exceeds 8MiB capture limit')
        return body,dt.datetime.now(dt.timezone.utc).isoformat()

def parse_source(body,source,observed_at):
    text=body.decode('utf-8',errors='replace')
    if '<html' in text.lower() or '<!doctype' in text.lower():
        parser=VisibleText();parser.feed(text);text=''.join(parser.parts)
    if source['adapter']=='openai_cards_partial':
        cards=OpenAICards();cards.feed(body.decode('utf-8',errors='replace'));rows=c.normalize_rows(cards.rows)
    else:rows=c.normalize_rows(c.extract_explicit_ids(text))
    for row in rows:row['line_basis']='raw_capture' if source['adapter']=='openai_cards_partial' else 'extraction_text'
    # This generic label extractor CANNOT prove it saw the whole source. Do not
    # accept complete/pagination flags from sources config or arbitrary content.
    return dict(_extraction_text=text,vendor=source['vendor'],channel=source['channel'],role=source['role'],
        source_url=source['url'],observed_at=observed_at,complete=False,
        fetch_status='ok',extraction_status='partial',
        errors=['full_catalog_adapter_not_reviewed'],records=rows,
        coverage_evidence=dict(source_url=source['url'],modalities=source['modalities'],
            enumeration_verified=False,pagination_complete=False,expected_record_count=None))

def execute(config,manifest,database,capture_dir,replay_dir=None):
    validate_sources(config,manifest)
    capture_dir.mkdir(parents=True,exist_ok=False);inventories=[]
    for source in config['sources']:
        sid=source['id'];now=dt.datetime.now(dt.timezone.utc).isoformat();stage='fetch';http_status=None
        try:
            if replay_dir is None:
                body,observed=fetch_source(source);http_status=200;capture_kind='http_body'
            else:
                meta=json.loads((replay_dir/(sid+'.json')).read_text());body=(replay_dir/(sid+'.body')).read_bytes()
                if meta['url']!=source['url'] or meta['sha256']!=digest(body):raise ValueError('Replay source provenance mismatch')
                http_status=meta.get('http_status');capture_kind=meta.get('capture_kind','http_body')
                if http_status!=200 and not (http_status is None and capture_kind=='tool_text'):raise ValueError('Replay was not a successful source capture')
                observed=meta['observed_at'];c.parse_time(observed)
            stage='capture'
            (capture_dir/(sid+'.body')).write_bytes(body)
            meta=dict(url=source['url'],observed_at=observed,http_status=http_status,capture_kind=capture_kind,sha256=digest(body),mode='replay' if replay_dir else 'fresh')
            c.atomic_json(capture_dir/(sid+'.json'),meta)
            stage='extract'
            snapshot=parse_source(body,source,observed)
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
