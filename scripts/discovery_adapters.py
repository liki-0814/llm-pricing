#!/usr/bin/env python3
"""Official catalog parsers. Literal IDs only; never guess slugs or strip punctuation.

Each adapter returns records plus optional reseller_records and notes. Callers
must keep snapshots partial unless independent full-enumeration evidence exists.
"""
import gzip,re,html
from html.parser import HTMLParser
import catalog_diff as c

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
    return official, [], ['model_row_parsed_aliases_and_media_not_fully_classified']


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


def minimax_model_list(body, source=None):
    raw, text = decode_body(body)
    official=[]
    section='available'
    for number, line in enumerate(text.splitlines(), 1):
        if re.search(r'^##\s+.*retir', line, re.I) or re.search(r'retired models', line, re.I):
            section='retired_notice'
        if not line.lstrip().startswith('|'):
            continue
        for label in re.findall(r'\[([^\]]+)\]\([^)]+\)', line):
            token=label.strip()
            if ID_TOKEN.fullmatch(token) or re.fullmatch(r'MiniMax-[A-Za-z0-9][A-Za-z0-9._-]*', token):
                official.append({'model_id':token,'api_id_explicit':True,'line':number,'catalog_section':section,
                                 'origin_note':'list_label_not_always_invocation_id'})
    return official, [], ['list_labels_need_invocation_id_confirmation; retirement_conflict_not_auto_applied']


def explicit_id_labels(body, source=None):
    raw, text = decode_body(body)
    return c.extract_explicit_ids(text), [], []


ADAPTERS = {
    'explicit_id_labels_partial': explicit_id_labels,
    'openai_cards_partial': openai_cards,
    'hunyuan_invocation_tables': hunyuan_invocation_tables,
    'qwen_recommended_lists': qwen_recommended_lists,
    'deepseek_model_row': deepseek_model_row,
    'kimi_model_tables': kimi_model_tables,
    'google_endpoint_tables': google_endpoint_tables,
    'anthropic_claude_api_id': anthropic_claude_api_id,
    'minimax_model_list': minimax_model_list,
}


def parse(adapter, body, source=None):
    if adapter not in ADAPTERS:
        raise ValueError('Unsupported/unreviewed adapter: '+str(adapter))
    records, reseller, notes = ADAPTERS[adapter](body, source)
    return c.normalize_rows(records), c.normalize_rows(reseller), notes
