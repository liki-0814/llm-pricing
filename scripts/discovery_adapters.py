#!/usr/bin/env python3
"""Official catalog parsers. Literal IDs only; never guess slugs or strip punctuation.

Each adapter returns records plus optional reseller_records and notes. Callers
must keep snapshots partial unless independent full-enumeration evidence exists.
"""
import gzip,re,html
from html.parser import HTMLParser
import catalog_diff as c
import discovery_bridges as bridges
import discovery_text_contracts as text_contracts
import discovery_google_contracts as google_contracts

NATIVE_QWEN = re.compile(r'^(?:qwen|wan|wanx|happyhorse|happyoyster|tongyi|z-image|text-embedding-v|decision-model|qwen-audio)', re.I)
THIRD_QWEN = re.compile(r'^(?:deepseek|glm|kimi|minimax|moonshot|claude|gpt-|o1|o3|grok|mistral|llama|gemini|yi-|doubao|hunyuan|hy\d|zhupu|zhipu)/?', re.I)
NATIVE_HY = re.compile(r'^(?:hy\d|hy-|hunyuan)', re.I)
ID_TOKEN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._/-]*$')


def decode_body(body):
    if not isinstance(body, (bytes, bytearray)):
        return body.encode() if body is None else str(body).encode(), str(body)
    if body.startswith(b'\x1f\x8b'):
        body = gzip.decompress(body)
    return bytes(body), body.decode('utf-8', errors='replace')


class OpenAICards(HTMLParser):
    """Public cards as display observations; NEVER infer API IDs from slugs or alts."""
    def __init__(self):
        super().__init__(); self.in_main=False; self.details=0; self.card=None; self.rows=[]
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='main': self.in_main=True
        if not self.in_main: return
        if tag=='details': self.details+=1
        href=attrs.get('href','')
        if tag=='a' and href.startswith('/') and not href.startswith('//'):
            directory=bool(re.fullmatch(r'/api/docs/models/[^/?#]+', href) and href!='/api/docs/models/all')
            self.card={'detail_url':'https://developers.openai.com'+href,'api_id_explicit':False,
                'model_id':None,'catalog_section':'historical' if self.details else 'current',
                'scope_status':'requires_scope_review','line':self.getpos()[0],'card_text':[],
                'card_kind':'directory' if directory else 'supplemental',
                'catalog_observation':True,'_model_card':directory}
        if tag=='img' and self.card is not None and attrs.get('src','').startswith('/images/api/models/icons/'):
            self.card['_model_card']=True; self.card['image_alt']=attrs.get('alt')
    def handle_data(self, data):
        if self.card is not None and data.strip():
            self.card.setdefault('display_name', data.strip()); self.card['card_text'].append(data.strip())
    def handle_endtag(self, tag):
        if tag=='a' and self.card is not None:
            self.card['card_text']=' '.join(self.card['card_text'])
            if self.card.pop('_model_card'): self.rows.append(self.card)
            self.card=None
        if self.in_main and tag=='details': self.details=max(0,self.details-1)
        if tag=='main': self.in_main=False


def openai_cards(body, source=None):
    raw, text = decode_body(body)
    parser=OpenAICards(); parser.feed(raw.decode('utf-8', errors='replace'))
    rows=[]
    for row in parser.rows:
        rec=dict(row, catalog_observation=True, api_id_explicit=False, model_id=None)
        rows.append(rec)
    return rows, [], ['openai_cards_pending_official_api_id_bridges']


def _html_tables(text):
    tables=[]
    for block in re.finditer(r'<table\b[^>]*>(.*?)</table>', text, re.I|re.S):
        rows=[]
        for tr in re.finditer(r'<tr\b[^>]*>(.*?)</tr>', block.group(1), re.I|re.S):
            cells=[re.sub(r'\s+',' ', re.sub(r'<[^>]+>',' ', html.unescape(td.group(1)))).replace('\ufeff','').strip()
                   for td in re.finditer(r'<t[hd]\b[^>]*>(.*?)</t[hd]>', tr.group(1), re.I|re.S)]
            if cells: rows.append(cells)
        if rows: tables.append({'line': text[:block.start()].count('\n')+1, 'rows': rows})
    return tables


def hunyuan_invocation_tables(body, source=None):
    raw, text = decode_body(body)
    official, reseller = [], []
    for table in _html_tables(text):
        header=[h.lower() for h in table['rows'][0]]
        idx=next((i for i,h in enumerate(header) if '调用' in h or 'model（' in h or h.strip()=='model'), None)
        name_idx=next((i for i,h in enumerate(header) if '名称' in h or 'name' in h), 0)
        if idx is None: continue
        for offset, cells in enumerate(table['rows'][1:], 1):
            if idx>=len(cells): continue
            tokens=[t for t in re.split(r'\s+', cells[idx]) if ID_TOKEN.fullmatch(t)]
            display=cells[name_idx] if name_idx<len(cells) else cells[idx]
            line=table['line']+offset
            if not tokens:
                official.append({'model_id':None,'api_id_explicit':False,'display_name':display,'line':line,
                                 'identity_error':'unresolved_literal_identity','raw_cell':cells[idx]})
                continue
            for token in tokens:
                rec={'model_id':token,'api_id_explicit':True,'display_name':display,'line':line,
                     'origin_vendor':'腾讯混元' if NATIVE_HY.match(token) else 'tokenhub_reseller'}
                if NATIVE_HY.match(token): official.append(rec)
                else:
                    rec['scope_status']='reseller_not_native_hunyuan'; reseller.append(rec)
    return official, reseller, ['tokenhub_mixed_directory_split_native_vs_reseller']


def qwen_recommended_lists(body, source=None):
    raw, text = decode_body(body)
    # Prefer visible labels and table-like tokens, not raw script noise.
    visible=re.sub(r'<script\b[^>]*>.*?</script>',' ', text, flags=re.I|re.S)
    visible=re.sub(r'<style\b[^>]*>.*?</style>',' ', visible, flags=re.I|re.S)
    visible=re.sub(r'<[^>]+>','\n', visible)
    official, reseller=[], []
    seen=set()
    for number, line in enumerate(visible.splitlines(), 1):
        for token in re.findall(r'\b[A-Za-z][A-Za-z0-9_.:/-]{2,}\b', line):
            token=token.rstrip('.,;:')
            if not ID_TOKEN.fullmatch(token) and '/' not in token: continue
            key=token
            if key in seen: continue
            # Catalog identifiers, not hyphenated English or typography class names.
            if '/' in token and not re.search(r'[0-9]', token):
                continue
            official_shape=bool(re.search(r'\d', token) or NATIVE_QWEN.match(token))
            if not official_shape: continue
            if re.fullmatch(r'(?:all|this|high|low|real|non|step|yes|cost|open|third|domain|built|human|role|more)-[a-z-]+', token, re.I):
                continue
            if token.lower() in {'qwen','text','more','model','models','image','video','audio','third-party','cost-effective','high-frequency','high-resolution','step-by-step','yes-or-no','built-in','domain-specific','human-like','role-playing','all-products-head','audio/video'}:
                continue
            seen.add(key)
            rec={'model_id':token,'api_id_explicit':True,'line':number,'literal_id':token}
            if NATIVE_QWEN.match(token):
                rec['origin_vendor']='阿里云 Qwen'; official.append(rec)
            elif (THIRD_QWEN.match(token) or '/' in token) and re.search(r'[0-9]', token):
                rec.update(origin_vendor='alibaba_marketplace_third_party', scope_status='reseller_or_origin_not_verified')
                reseller.append(rec)
            else:
                rec['origin_status']='pending_confirmation'; official.append(rec)
    return official, reseller, ['recommended_or_category_list_not_full_model_plaza']


def deepseek_model_row(body, source=None):
    raw, text = decode_body(body)
    official=[]
    for table in _html_tables(text):
        if not table['rows'] or table['rows'][0][0].strip().upper()!='MODEL': continue
        for cell in table['rows'][0][1:]:
            token=re.sub(r'\s*\(\d+\)\s*','', cell).strip()
            mid=c.canonical_id(token)
            if mid: official.append({'model_id':mid,'api_id_explicit':True,'display_name':cell,'line':table['line']})
        break
    enriched,proof=text_contracts.deepseek_contract(text,source)
    if proof['verified']:return enriched,[],['accepted_legacy_aliases_are_routed_not_retired_invocation_IDs']
    return official, [], ['deepseek_text_contract_incomplete:'+proof.get('error','unknown')]


def kimi_model_tables(body, source=None):
    raw, text = decode_body(body)
    official=[]; section='current'
    for number, line in enumerate(text.splitlines(), 1):
        if re.search(r'deprecated models|no longer available|deprecated', line, re.I):
            if line.strip().startswith('#') or line.strip().startswith('|') is False and 'Deprecated' in line:
                section='deprecated'
        if re.search(r'^##\s+Deprecated', line, re.I): section='deprecated'
        for token in re.findall(r'`([^`\s]+)`', line):
            mid=c.canonical_id(token)
            if mid:
                official.append({'model_id':mid,'api_id_explicit':True,'line':number,'catalog_section':section,
                                 'retirement':'pending_confirmation' if section=='deprecated' else None})
    return official, [], ['kimi_eligibility_and_currency_not_inferred']


def google_endpoint_tables(body, source=None):
    raw,text=decode_body(body)
    try:
        rows,_=google_contracts.directory(text)
        return rows,[],['native_literal_endpoints_retained; output_detail_proof_required']
    except (ValueError,TypeError,KeyError,StopIteration):
        return _google_partial_literals(body,source)


def _google_partial_literals(body, source=None):
    raw, text = decode_body(body)
    official=[]; seen=set()
    # Official "Endpoint" backtick IDs in model tables, plus explicit Model code labels.
    for number, line in enumerate(text.splitlines(), 1):
        codes=re.findall(r'\*Model code\*\s+\*\*([^*`]+)\*\*', line, re.I)
        codes += re.findall(r'`([a-z0-9][a-z0-9._-]*)`', line)
        # Only keep gemini/nano-banana/lyria/imagen/veo-like official families if backtick
        # appears next to endpoint tables or model code; still allow unknown future IDs
        # when the line is inside a model/endpoint table context.
        table_ctx=bool(re.search(r'endpoint|\* model|model code|variant="model"', line, re.I))
        if not codes: continue
        if not table_ctx and 'Model code' not in line and '* Endpoint' not in line and not line.strip().startswith('* `'):
            # bare mentions elsewhere are not catalog proof
            if not re.search(r'^\s*\*\s+`[a-z0-9].+`\s*$', line):
                continue
        for token in codes:
            mid=c.canonical_id(token.strip())
            if mid and mid not in seen:
                seen.add(mid); official.append({'model_id':mid,'api_id_explicit':True,'line':number})
    return official, [], ['card_href_slugs_are_not_api_ids']


def anthropic_claude_api_id(body, source=None):
    raw, text = decode_body(body)
    official, pending=[], []
    for table in _html_tables(text):
        rows=table['rows']
        header=rows[0]
        api_row=next((r for r in rows if r and r[0].strip().lower()=='claude api id'), None)
        if api_row and len(api_row)==len(header):
            for name, token in zip(header[1:], api_row[1:]):
                mid=c.canonical_id(token)
                if mid:
                    label=re.match(r'(Claude (?:Fable|Opus|Sonnet|Haiku|Mythos) \d+(?:\.\d+)?)', name)
                    official.append({'model_id':mid,'api_id_explicit':True,'display_name':label.group(1) if label else re.split(r'\s+For\s+', name, 1)[0].strip(),
                                     'line':table['line'],'origin_vendor':'Anthropic','id_row':'Claude API ID'})
        # pricing/all-models display rows without IDs stay pending, never guessed
        if header and header[0].strip().lower()=='model':
            known={r['display_name'] for r in official}
            for offset, cells in enumerate(rows[1:], 1):
                name=cells[0].strip()
                if name and name not in known and name.lower() not in {'model','name','feature','capabilities','base tokens'}:
                    pending.append({'model_id':None,'api_id_explicit':False,'display_name':name,
                                    'catalog_observation':True,'line':table['line']+offset,
                                    'identity_error':None,'scope_status':'pending_official_api_id'})
    return official+pending, [], ['partner_ids_excluded; older_display_names_pending_api_id']


def markdown_model_rows(text):
    """All explicit Model-column rows, including quoted accordion tables."""
    active=False
    for number,line in enumerate(text.splitlines(),1):
        line=re.sub(r'^\s*(?:>\s*)+', '', line).strip()
        if not line.startswith('|'):
            active=False; continue
        cells=[x.strip() for x in line.strip('|').split('|')]
        if cells[0].lower()=='model':
            active=True; continue
        if not active or re.fullmatch(r'[: -]+',cells[0]): continue
        yield number,cells


def minimax_model_list(body, source=None):
    raw,text=decode_body(body);rows=[]
    for number,cells in markdown_model_rows(text):
        label=cells[0];match=re.fullmatch(r'\[([^]]+)\]\(([^)]+)\)',label)
        name=match[1] if match else label.strip('`')
        retired=len(cells)>=3 and cells[-1].strip().lower()=='retired'
        # A Model display column is not independent invocation-ID proof.
        rows.append({'model_id':None,'api_id_explicit':False,'catalog_observation':True,
            'display_name':name,'line':number,'detail_url':match[2] if match else None,
            'catalog_section':'retired' if retired else 'listed',
            'lifecycle_status':'retired' if retired else 'unconfirmed',
            'lifecycle_quote':' | '.join(cells) if retired else None,
            'retired_at':None,'scope_status':'pending_official_api_id'})
    return rows,[],['model_names_retained_pending_invocation_ids; retired_status_is_not_a_retirement_instant']


def kimi_code_catalog(body, source=None):
    raw,text=decode_body(body);rows=[]
    for table in _html_tables(text):
        for cells in table['rows']:
            if cells[0].strip().lower()!='model id':continue
            for token in cells[1:]:
                mid=c.canonical_id(token)
                rows.append({'model_id':mid,'api_id_explicit':bool(mid),'catalog_observation':not bool(mid),
                    'display_name':token,'line':table['line'],'id_row':'Model ID',
                    'origin_vendor':'Moonshot Kimi','catalog_section':'current_subscription'})
    return rows,[],[]


def kimi_code_proof(body, source, records):
    raw,text=decode_body(body)
    visible=re.sub(r'<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>',' ',text,flags=re.I|re.S)
    visible=html.unescape(re.sub(r'<[^>]+>',' ',visible));visible=re.sub(r'\s+',' ',visible)
    match=re.search(r'Kimi Code currently offers (\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve) model IDs',visible,re.I)
    words=dict(zip('one two three four five six seven eight nine ten eleven twelve'.split(),range(1,13)))
    count=(int(match[1]) if match[1].isdigit() else words[match[1].lower()]) if match else None
    exact_source=(source.get('vendor'),source.get('channel'),source.get('url'),source.get('modalities'),source.get('role'))==('Moonshot Kimi','subscription','https://www.kimi.com/code/docs/en/kimi-code/models',['text'],'catalog')
    ids=[r.get('model_id') for r in records]
    terminal=bool(re.search(r'How to Switch Models',visible))
    continuation=bool(re.search(r'(?:[?&]page=|rel=["\']next["\'])',text,re.I))
    ok=bool(exact_source and count and count==len(ids)==len(set(ids)) and all(ids) and terminal and not continuation)
    return {'verified':ok,'expected_record_count':count,'count_quote':match[0] if match else None,
        'terminal_section_present':terminal,'pagination_continuation_found':continuation,
        'method':'explicit_current-offering_count_vs_literal_Model-ID_row; scope=current_Kimi-Code_subscription_catalog'}


def xai_markdown_models(body, source=None):
    raw,text=decode_body(body);rows=[];seen=set()
    for number,cells in markdown_model_rows(text):
        # Only the Model column, not sidebar/aliases, and only a published price row.
        token=re.sub(r'\s+\([^)]*prompt tokens\)$','',cells[0]).strip('` ')
        mid=c.canonical_id(token)
        if not mid or mid in seen or not any('$' in x for x in cells[1:]):continue
        seen.add(mid);rows.append({'model_id':mid,'api_id_explicit':True,'line':number,'price_public':True,
            'catalog_section':'public_priced_models','origin_vendor':'xAI'})
    return rows,[],['public_pricing_tables_not_proof_of_unpriced_retired_or_subscription_catalog']


def zai_overview_tables(body, source=None):
    raw,text=decode_body(body);rows=[]
    for number,cells in markdown_model_rows(text):
        urls=re.findall(r'\]\((https://docs\.z\.ai/guides/[^)]+)\)', ' '.join(cells[1:]))
        rows.append({'model_id':None,'api_id_explicit':False,'catalog_observation':True,
            'display_name':cells[0],'line':number,'detail_urls':list(dict.fromkeys(urls)),
            'scope_status':'pending_official_api_id','catalog_section':'overview_including_quoted_other_models'})
    return rows,[],['model_display_names_require_official_invocation_ID_bridges']


def explicit_id_labels(body, source=None):
    raw, text = decode_body(body)
    return c.extract_explicit_ids(text), [], []


def bridged_directory(body,source):
 raw,text=decode_body(body)
 if source['vendor']=='OpenAI':rows=bridges.openai_directory(text)
 else:rows=bridges.anthropic_directory(text)
 return rows,[],['literal_ID_bridge_required; channel_and_full_coverage_review_pending']

def zai_openapi_models(body,source=None):
 raw,text=decode_body(body);rows,proof=bridges.zai_request_models(text)
 return rows,[],[] if proof['verified'] else ['request_enum_proof_failed:'+str(proof.get('error'))]

def anthropic_status_ids(body,source=None):
 raw,text=decode_body(body)
 return bridges.anthropic_status(text),[],['official_API_status_and_history; original_dates_not_invented_instants']


ADAPTERS = {
    'openai_markdown_bridged': bridged_directory,
    'anthropic_markdown_bridged': bridged_directory,
    'zai_openapi_models': zai_openapi_models,
    'anthropic_status_ids': anthropic_status_ids,
    'anthropic_release_notes': lambda body,source: ([],[],['entity-bound native notices only; not a directory enumeration']),
    'explicit_id_labels_partial': explicit_id_labels,
    'openai_cards_partial': openai_cards,
    'hunyuan_invocation_tables': hunyuan_invocation_tables,
    'qwen_recommended_lists': qwen_recommended_lists,
    'deepseek_model_row': deepseek_model_row,
    'kimi_model_tables': kimi_model_tables,
    'google_endpoint_tables': google_endpoint_tables,
    'anthropic_claude_api_id': anthropic_claude_api_id,
    'minimax_model_list': minimax_model_list,
    'kimi_code_catalog': kimi_code_catalog,
    'xai_markdown_models': xai_markdown_models,
    'zai_overview_tables': zai_overview_tables,
}


def parse(adapter, body, source=None):
    if adapter not in ADAPTERS:
        raise ValueError('Unsupported/unreviewed adapter: '+str(adapter))
    records, reseller, notes = ADAPTERS[adapter](body, source)
    return c.normalize_rows(records), c.normalize_rows(reseller), notes
