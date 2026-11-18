"""Source-bound public price observations, independent of exhaustive discovery.

No network, credentials, inferred FX, availability, aliases, or global closure.
Both build consumers and discovery consume this one parser/validator. The
checked-in originals are archival observations at observed_at, not fresh reads.
"""
import datetime as dt
import hashlib
import json
import math
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
QWEN_REGION_LABELS={'华北2（北京）','新加坡','美国（弗吉尼亚）','德国（法兰克福）','日本（东京）','中国香港'}
SOURCES={
 'https://help.aliyun.com/zh/model-studio/model-pricing':('阿里云 Qwen','pay_as_you_go'),
 'https://docs.x.ai/developers/pricing':('xAI','pay_as_you_go'),
}

SOURCES.update({
 'https://platform.claude.com/docs/en/about-claude/pricing.md':('Anthropic','pay_as_you_go'),
 'https://platform.claude.com/docs/en/models/overview.md':('Anthropic','pay_as_you_go'),
 'https://aistudio.google.com/docs/pricing':('Google Gemini','pay_as_you_go'),
 'https://aistudio.google.com/docs/models':('Google Gemini','pay_as_you_go'),
 'https://platform.minimax.io/docs/pricing/overview':('MiniMax','pay_as_you_go'),
 'https://platform.minimax.io/docs/faq/models.md':('MiniMax','pay_as_you_go'),
 'https://developers.openai.com/api/docs/pricing':('OpenAI','pay_as_you_go'),
 'https://developers.openai.com/api/docs/models/all.md':('OpenAI','pay_as_you_go'),
})
CATALOG_URLS={u for u in SOURCES if u.endswith(('overview.md','models','models.md','all.md'))}

def digest(raw):return hashlib.sha256(raw).hexdigest()
def clean(s):return ' '.join(s.split())

class Tables(HTMLParser):
    """Literal table/heading reader; rowspans carry their original source row."""
    def __init__(self,text):
        super().__init__(convert_charrefs=True)
        self.text=text;self.offsets=[0];self.tables=[];self.headings={};self.heading=None;self.table=None;self.row=None;self.cell=None
        for match in re.finditer('\n',text):self.offsets.append(match.end())
    def pos(self):
        line,col=self.getpos();return self.offsets[line-1]+col
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if re.fullmatch('h[1-6]',tag) and self.table is None:self.heading=dict(level=int(tag[1]),start=self.pos(),parts=[])
        if tag=='table':
            if self.table is not None:raise ValueError('nested price tables unsupported')
            self.table=dict(start=self.pos(),headings=dict(self.headings),rows=[])
        if tag=='tr' and self.table is not None:self.row=dict(start=self.pos(),cells=[])
        if tag in ('td','th') and self.row is not None:
            self.cell=dict(parts=[],rowspan=int(attrs.get('rowspan','1')),colspan=int(attrs.get('colspan','1')),header=tag=='th')
        if tag in ('p','br','div','blockquote') and self.cell is not None:self.cell['parts'].append(' ')
    def handle_data(self,data):
        if self.heading is not None:self.heading['parts'].append(data)
        if self.cell is not None:self.cell['parts'].append(data)
    def handle_endtag(self,tag):
        end=self.pos()+len('</'+tag+'>')
        if self.heading is not None and tag=='h'+str(self.heading['level']):
            h=self.heading;h.update(text=clean(''.join(h['parts'])),quote=self.text[h['start']:end]);self.heading=None
            self.headings={k:v for k,v in self.headings.items() if k<h['level']};self.headings[h['level']]=h
        if tag in ('td','th') and self.cell is not None:
            self.cell['text']=clean(''.join(self.cell.pop('parts')));self.row['cells'].append(self.cell);self.cell=None
        if tag=='tr' and self.row is not None:
            self.row.update(quote=self.text[self.row['start']:end]);self.table['rows'].append(self.row);self.row=None
        if tag=='table' and self.table is not None:
            self.table.update(quote=self.text[self.table['start']:end]);self.tables.append(self.table);self.table=None

def expanded(table):
    spans={};rows=[]
    for row in table['rows']:
        cells={};next_spans={}
        for col,(remaining,cell) in spans.items():
            cells[col]=cell
            if remaining>1:next_spans[col]=(remaining-1,cell)
        col=0
        for cell in row['cells']:
            while col in cells:col+=1
            cell=dict(cell,origin_quote=row['quote'])
            if cell['rowspan']<1 or cell['colspan']<1:raise ValueError('invalid table span')
            for j in range(cell['colspan']):
                cells[col+j]=cell
                if cell['rowspan']>1:next_spans[col+j]=(cell['rowspan']-1,cell)
            col+=cell['colspan']
        spans=next_spans
        rows.append((row,[cells.get(i,dict(text='',origin_quote=row['quote'])) for i in range(max(cells,default=-1)+1)]))
    return rows

def verified_document(meta,raw):
    if SOURCES.get(meta.get('source_url'))!=(meta.get('vendor'),meta.get('channel')):raise ValueError('unapproved source/vendor/channel context')
    if meta.get('http_status')!=200 or digest(raw)!=meta.get('source_sha256'):raise ValueError('missing original body/hash or HTTP 200')
    at=dt.datetime.fromisoformat(meta.get('observed_at','').replace('Z','+00:00'))
    if at.tzinfo is None:raise ValueError('observation timezone missing')
    text=raw.decode('utf-8')
    if any(t in text.lower() for t in ('_____tmd_____/punish','x5secdata=','captcha challenge','waf_block_deny')):raise ValueError('access gate is not a price document')
    return text

def fact(meta,text,*,model_id,offering_name,channel,region,modality,component,amount,currency,unit,tier,quote,context):
    # All selectors are derived in the parser, never supplied by a verified flag.
    if not quote or quote not in text or not context or any(not q or q not in text for q in context):raise ValueError('missing literal evidence')
    if currency not in ('CNY','USD') or not region or region=='not_stated_in_source' or not unit or not tier or not component or not modality:raise ValueError('price selectors missing')
    if type(amount) not in (int,float) or not math.isfinite(amount) or amount<0:raise ValueError('invalid amount')
    if model_id is not None and not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._/-]*',model_id):raise ValueError('nonliteral model ID')
    if model_id is None and not offering_name:raise ValueError('identity missing')
    value=dict(vendor=meta['vendor'],model_id=model_id,offering_name=offering_name,identity_kind='literal_model_id' if model_id else 'plan_offering_NOT_API_ID',channel=channel,region=region,modality=modality,component=component,amount=amount,currency=currency,unit=unit,tier=tier,observed_at=meta['observed_at'],effective_from=None,effective_until=None,time_basis='observed_at_NOT_inferred_effective_start',source_url=meta['source_url'],source_sha256=meta['source_sha256'],quote=quote,quote_sha256=digest(quote.encode()),context_quotes=list(dict.fromkeys(context)),price_verified=True,region_scope='explicit_source_region',price_basis='quoted_public_table_NOT_account_or_promotion_quote',eligible_for_estimation=False,availability='not_assessed',scope_complete=False,history_complete=False,account_entitlement='not_assessed')
    value['fact_id']=digest(json.dumps(value,sort_keys=True,ensure_ascii=False).encode())[:24]
    return value

def qwen(meta,text,tables):
    billing='模型调用默认 按量计费 ，涵盖各类模型的计费规则与价格。'
    if billing not in text:raise ValueError('Qwen PAYG billing declaration missing')
    facts=[];pending=[]
    for table in tables:
        hs=table['headings'];section=hs.get(2,{}).get('text','');group=hs.get(3,{}).get('text','');region=hs.get(4,{}).get('text','')
        # Native sections are explicit editorial grouping, never model prefixes.
        mode='text' if section in ('文本生成-千问','文本生成-千问-开源版') else 'image' if section=='图像生成' and ('千问' in group or '万相' in group) else 'video' if section=='视频生成' and ('万相' in group or 'HappyHorse' in group) else None
        if mode is None:continue
        mixed_output=mode=='text' and any(x in group for x in ('Omni','Audio'))
        rows=expanded(table)
        if not rows:continue
        header=[c['text'].replace(' ','') for c in rows[0][1]]
        if not header or header[0]!='模型ID（ModelID）':
            pending.append(dict(reason='unreviewed_price_table_header',section=section,group=group,region=region,quote=table['quote'][:2000]));continue
        header_rows=[rows[0][0]['quote']];start=1
        while start<len(rows) and rows[start][1] and rows[start][1][0]['text'].replace(' ','')==header[0]:
            leaf=[c['text'].replace(' ','') for c in rows[start][1]]
            if len(leaf)!=len(header):break
            header=[base if child==base else base+' / '+child for base,child in zip(header,leaf)]
            header_rows.append(rows[start][0]['quote']);start+=1
        for row,cells in rows[start:]:
            vals=[c['text'] for c in cells]
            candidate=dict(reason='unparsed_price_candidate',section=section,group=group,region=region,cells=vals,quote=row['quote'])
            if len(vals)!=len(header) or region not in QWEN_REGION_LABELS:
                pending.append(candidate);continue
            mid_match=re.match(r'^([A-Za-z0-9][A-Za-z0-9._/-]*)(?:\s|$)',vals[0]);mid=mid_match[1] if mid_match else None
            if mid is None:pending.append(candidate);continue
            tiers={header[i]:v for i,v in enumerate(vals) if i and '单价' not in header[i] and '免费额度' not in header[i]}
            tier=json.dumps(tiers,ensure_ascii=False,sort_keys=True) if tiers else 'table_standard'
            count=0
            for i,h in enumerate(header):
                if not ('单价' in h and ('输入' in h or '输出' in h)):continue
                if mixed_output:
                    # Only a literal component-level text declaration, never the
                    # text-section heading or an image/audio input declaration.
                    leaf=h.split(' / ')[-1] if ' / ' in h else ''
                    if '文本' not in leaf or any(x in leaf for x in ('音频','图片','视频')):continue
                list_price=re.fullmatch(r'原价([0-9]+(?:\.[0-9]+)?)元（限时[0-9]+(?:\.[0-9]+)?折）',vals[i])
                rate_text=list_price[1]+'元' if list_price else vals[i]
                m=re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)\s*元(?:/(张|秒))?',rate_text)
                if not m:continue
                unit='per_image' if m[2]=='张' else 'per_second' if m[2]=='秒' else 'per_1M_tokens' if '每百万' in h else None
                if not unit:continue
                if mode=='text' and unit!='per_1M_tokens':continue
                if mode!='text' and unit=='per_1M_tokens':continue
                contexts=[billing,*header_rows,cells[0]['origin_quote']]+[v['quote'] for v in hs.values()]
                facts.append(fact(meta,text,model_id=mid,offering_name=None,channel='pay_as_you_go',region=region,modality=mode,component='cached_input' if '缓存' in h.split(' / ')[0] and '命中' in h.split(' / ')[0] else 'input' if '输入' in h.split(' / ')[0] else 'output',amount=float(m[1]),currency='CNY',unit=unit,tier=json.dumps(dict(dimensions=tiers,price_header=h),ensure_ascii=False,sort_keys=True),quote=row['quote'],context=contexts));facts[-1]['rate_kind']='explicit_list_price_NOT_discounted_charge' if list_price else 'quoted_table_rate';count+=1
                if list_price:
                    pending.append(dict(candidate,reason='promotion_terms_not_inferred_list_price_only_verified'))
            if not count:pending.append(dict(candidate,reason='missing_literal_component_output_binding' if mixed_output else candidate['reason']))
    return facts,pending

FAST_SENTENCE="Grok 4.7 Fast is the same Grok 4.7 model served on faster infrastructure."

def xai_fast(meta,text,tables):
    facts=[];pending=[]
    plain=clean(re.sub('<[^>]+>',' ',text))
    required=('available only in','Cursor and Grok Build','billed through your plan','not available on the public xAI API')
    if not all(t in plain for t in required):return [],[dict(reason='plan_channel_declaration_missing')]
    for table in tables:
        h=table['headings'].get(2,{})
        if h.get('text')!='Grok 4.7 Fast pricing (Cursor and Grok Build only)':continue
        rows=expanded(table)
        if not rows or [c['text'] for c in rows[0][1]]!=['Prompt tokens','Input','Cached input','Output']:raise ValueError('Fast price header changed')
        # Bound prose to this heading and the next heading, not an unrelated example.
        start=h['start'];stop=text.find('<h2',start+1);stop=stop if stop>=0 else len(text);section=text[start:stop]
        if not all(t in clean(re.sub('<[^>]+>',' ',section)) for t in required):raise ValueError('Fast plan declaration outside entity section')
        for row,cells in rows[1:]:
            vals=[c['text'] for c in cells]
            if len(vals)!=4 or vals[0] not in ('Below 200k','Above 200k'):
                pending.append(dict(reason='unreviewed_fast_tier',quote=row['quote']));continue
            for i,component in enumerate(('input','cached_input','output'),1):
                m=re.fullmatch(r'\$([0-9]+(?:\.[0-9]+)?) / 1M',vals[i])
                if not m:pending.append(dict(reason='unparsed_fast_rate',quote=row['quote']));continue
                pending.append(dict(reason='price_region_not_stated_NOT_verified',vendor='xAI',model_id=None,offering_name='Grok 4.7 Fast',
                    channel='subscription',region=None,modality='text',component=component,amount=float(m[1]),currency='USD',unit='per_1M_tokens',
                    tier=vals[0]+' prompt tokens (boundary not inferred)',price_verified=False,scope_complete=False,
                    source_url=meta['source_url'],source_sha256=meta['source_sha256'],observed_at=meta['observed_at'],quote=row['quote'],quote_sha256=digest(row['quote'].encode()),
                    offering_channel_observation=dict(offering_name='Grok 4.7 Fast',model_id=None,channel='subscription',channel_verified=True,
                    available_in=['Cursor','Grok Build'],public_xai_API=False,free_build_tier_included=False,account_entitlement='not_assessed',
                    scope_complete=False,source_url=meta['source_url'],source_sha256=meta['source_sha256'],observed_at=meta['observed_at'],quote=section,quote_sha256=digest(section.encode()))))
    return facts,pending

def quoted_document_rows(meta,text):
    """Consume remaining public tables without guessing IDs, tabs, units or regions.

    A quote observation confirms the printed amount/conditions, NOT the old
    complete-selector price_verified contract. Unspecified-region semantics
    await review; no assertion of worldwide applicability is made here.
    """
    role='catalog' if meta['source_url'] in CATALOG_URLS else 'pricing'
    observations=[]
    def add(quote,headers=None,heading=None):
        rates=re.findall(r'\$\s*[0-9]+(?:\.[0-9]+)?',quote)
        if role=='pricing' and not rates:return
        if role=='catalog' and not ('`' in quote or '<code' in quote):return
        observations.append(dict(vendor=meta['vendor'],channel=meta['channel'],source_url=meta['source_url'],source_sha256=meta['source_sha256'],
            observed_at=meta['observed_at'],quote=quote,quote_sha256=digest(quote.encode()),headers=headers,heading=heading,
            quoted_rate_literals=rates,quote_verified=True,price_verified=False,region=None,region_scope='unspecified_or_unparsed_NOT_global',
            model_id=None,identity_status='literal_context_retained_NOT_API_ID_certified',scope_complete=False,
            reason='catalog_literal_reference_NOT_identity_certification' if role=='catalog' else 'quoted_price_conditions_retained_selector_contract_pending',
            source_role=role))
    if '<table' in text:
        reader=Tables(text);reader.feed(text)
        for table in reader.tables:
            rows=expanded(table)
            for row,cells in rows[1:]:add(row['quote'],headers=[c['text'] for c in rows[0][1]],heading={k:v['text'] for k,v in table['headings'].items()})
    else:
        heading=''
        for line in text.splitlines(keepends=True):
            if line.lstrip().startswith('#'):heading=line.rstrip()
            if line.lstrip().startswith('|'):add(line,heading=heading)
        # Google public Markdown uses Markdoc tables rather than pipe syntax.
        for match in re.finditer(r'{% table %}(.*?){% /table %}',text,re.S):
            prefix=text[:match.start()];heads=re.findall(r'^## .*$',prefix,re.M);tabs=re.findall(r'{% tab title="([^"]+)" %}',prefix)
            pieces=re.split(r'^\s*---\s*$',match.group(1),flags=re.M)
            for piece in pieces[1:]:add(piece,headers=pieces[0],heading=dict(model_section=heads[-1] if heads else None,tab=tabs[-1] if tabs else None))
        if role=='catalog':
            for line in text.splitlines(keepends=True):
                if not line.lstrip().startswith('|') and '`' in line:add(line)
    return observations


def parse(meta,raw):
    text=verified_document(meta,raw)
    if meta['vendor'] not in ('阿里云 Qwen','xAI'):
        return dict(facts=[],pending=quoted_document_rows(meta,text),scope_complete=False,history_complete=False)
    reader=Tables(text);reader.feed(text);reader.close()
    facts,pending=qwen(meta,text,reader.tables) if meta['vendor']=='阿里云 Qwen' else xai_fast(meta,text,reader.tables)
    return dict(facts=list({r['fact_id']:r for r in facts}.values()),pending=pending,scope_complete=False,history_complete=False)


def assemble(sources,read_body,evidence_kind='archival_public_HTTP_observations_NOT_live_discovery'):
    facts=[];pending=[];offerings={}
    for meta in sources:
        result=parse(meta,read_body(meta));facts.extend(result['facts']);pending.extend(dict(p,source_url=meta['source_url'],vendor=meta['vendor'],source_channel=meta['channel']) for p in result['pending'])
        for candidate in result['pending']:
            offering=candidate.get('offering_channel_observation')
            if offering:offerings[(offering['offering_name'],offering['channel'],offering['source_sha256'])]=offering
    pending=list({json.dumps(p,sort_keys=True,ensure_ascii=False):p for p in pending}.values())
    return dict(quoted_price_statement_count=sum(bool(c.get('quote_verified')) and c.get('source_role')=='pricing' for c in pending),catalog_reference_quote_count=sum(bool(c.get('quote_verified')) and c.get('source_role')=='catalog' for c in pending),schema_version=1,evidence_kind=evidence_kind,price_verified_count=len(facts),scope_complete=False,history_complete=False,account_entitlement='not_assessed',compatibility='additive_evidence_only; audited rates and calculators unchanged; observation is not current availability',sources=sources,facts=facts,pending=pending,offering_channel_observations=list(offerings.values()))


def load(root=None):
    root=Path(root or ROOT);config=json.loads((root/'data/public-price-evidence.json').read_text())
    def read(meta):
        path=(root/meta['body_path']).resolve()
        if not path.is_relative_to((root/'data/evidence/public-prices').resolve()):raise ValueError('price evidence path escapes data boundary')
        return path.read_bytes()
    return assemble(config['sources'],read)


def load_capture(capture_dir):
    root=Path(capture_dir).resolve();manifest=json.loads((root/'capture-manifest.json').read_text());sources=manifest['sources']
    if len({m['source_url'] for m in sources})!=len(sources):raise ValueError('duplicate captured source')
    def read(meta):
        statuses={s['source_url']:s for s in manifest['refresh_run']['source_results']}
        status=statuses.get(meta['source_url'],{})
        if status.get('status')!='fetched_HTTP200' or status.get('reused_cache') is not False or status.get('attempt_id')!=manifest['refresh_run']['attempt_id'] or meta.get('attempt_id')!=status.get('attempt_id') or status.get('source_sha256')!=meta.get('source_sha256') or status.get('observed_at')!=meta.get('observed_at'):
            raise ValueError('capture provenance is not this attempt successful HTTP source')
        path=(root/meta['body_path']).resolve()
        if not path.is_relative_to(root):raise ValueError('capture body escapes source boundary')
        return path.read_bytes()
    ledger=assemble(sources,read,'public_HTTP_capture_NOT_full_discovery_fresh')
    run=dict(manifest['refresh_run']);requested=set(run.get('requested_urls',[]));statuses=run['source_results']
    if not requested<=set(SOURCES) or len({x['source_url'] for x in statuses})!=len(statuses) or {x['source_url'] for x in statuses}!=requested:raise ValueError('capture source coverage mismatch')
    run['all_sources_http_ok']=run.get('transport')=='normal_public_HTTP_GET' and {s['source_url'] for s in sources}==requested and all(s.get('status')=='fetched_HTTP200' and s.get('reused_cache') is False for s in statuses)
    run['full_discovery_fresh']=False;run['scope_complete']=False
    ledger['refresh_run']=run
    ledger['archival_last_known']=manifest.get('archival_last_known',[])
    return ledger


def view(ledger,mixed=True):
    """Versioned API view; v1 never leaks CNY prices, including pending cells."""
    result={k:v for k,v in ledger.items() if k not in ('facts','pending','sources')}
    result['facts']=[f for f in ledger['facts'] if mixed or f['currency']=='USD']
    result['price_verified_count']=len(result['facts'])
    result['pending_candidates']=[{k:v for k,v in p.items() if k!='offering_channel_observation'} for p in ledger['pending'] if mixed or p.get('currency')=='USD']
    result['pending_count']=len(result['pending_candidates'])
    result['price_candidates']=[{k:v for k,v in p.items() if k!='offering_channel_observation'} for p in ledger['pending'] if p.get('currency') and (mixed or p['currency']=='USD')]
    result['sources']=[s for s in ledger['sources'] if mixed or s['vendor']!='阿里云 Qwen']
    result['evidence_version']=digest(json.dumps([result['facts'],result['pending_candidates'],result['sources'],result['offering_channel_observations'],result.get('refresh_run')],sort_keys=True,ensure_ascii=False).encode())
    return result


def attach(inventories,ledger):
    """Join exact literal/vendor/channel only; no price-to-universe promotion.

    Observed request IDs and pending catalog-only IDs can both receive prices,
    but retain their identity/provider status, output and certificate unchanged.
    Non-enumerated offering names (Fast) remain separate observations, not IDs.
    """
    by_key={}
    for f in ledger['facts']:
        if f['model_id'] is not None:by_key.setdefault((f['vendor'],f['channel'],f['model_id']),[]).append(f)
    for snapshot in inventories:
        snapshot['public_offering_channel_observations']=[o for o in ledger['offering_channel_observations'] if snapshot['vendor']=='xAI' and snapshot['channel']==o['channel']]
        snapshot['unparsed_public_price_candidates']=[{k:v for k,v in p.items() if k!='offering_channel_observation'} for p in ledger['pending'] if p['vendor']==snapshot['vendor'] and p.get('channel',p['source_channel'])==snapshot['channel']]
        matched=set()
        for row in snapshot.get('records',[]):
            mid=row.get('model_id') or row.get('observed_model_id')
            found=by_key.get((snapshot['vendor'],snapshot['channel'],mid),[])
            row['public_price_observations']=found
            row['price_observation_status']='price_verified_at_source_observation' if found else 'unknown_no_bound_public_price_observation'
            matched.update(f['fact_id'] for f in found)
        snapshot['public_price_evidence']=dict(matched_fact_count=len(matched),scope_complete=False,history_complete=False,evidence_kind=ledger['evidence_kind'])
    return ledger
