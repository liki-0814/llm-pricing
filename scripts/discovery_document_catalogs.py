"""Public, published catalog indexes and per-entity request/output observations.

No website internal API, execution of examples, input=>output inference, author
inference from a model-name prefix, or subscription borrowing.
"""
import html,re
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit,unquote
from discovery_markdown import formal_text,sections
from discovery_claim_contract import canonical_id,qualified,claim,project

QWEN='https://www.alibabacloud.com/help/en/model-studio/'
QWEN_INDEXES={QWEN+'model-list-text-generation.md':'Text Generation',QWEN+'model-list-image-generation.md':'Image Generation',QWEN+'model-list-video-generation.md':'Video Generation'}
XAI_INDEX='https://docs.x.ai/llms.txt'

def access_gate(text):
    return any(token in text.lower() for token in ('waf_block_deny','gateway-diagnostic','request rejected at client classification gate','captcha challenge'))

def qwen_index(text,url):
    if url not in QWEN_INDEXES or access_gate(text):raise ValueError('unapproved/blocked Qwen published category')
    clean=formal_text(text);lines=clean.splitlines()
    if not lines or lines[0]!='# '+QWEN_INDEXES[url]:raise ValueError('Qwen category title changed')
    entries=[];unparsed=[]
    for number,line in enumerate(lines[1:],2):
        if not line.strip() or re.fullmatch(r'<meta property="og:title" content="[^"]+" />',line):continue
        m=re.fullmatch(r'- \[([^]]+)\]\((/help/en/model-studio/[A-Za-z0-9-]+)\)',line)
        if not m:unparsed.append(dict(line=number,quote=line));continue
        entries.append(dict(display_name=m[1],detail_url=urljoin(QWEN,m[2])+'.md',line=number,quote=line))
    if not entries or unparsed:raise ValueError('category contains empty/unparsed rows: '+str(unparsed))
    return entries,dict(index_rows=len(entries),document_terminated=True,global_exhaustiveness='not_asserted_by_category_index',published_index=url)

class CapabilityRows(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.rows=[];self.row=None;self.cell=None;self.depth=0
    def handle_starttag(self,tag,attrs):
        if tag=='tr':
            if self.row is not None:raise ValueError('nested capability table rows')
            self.row=[]
        if tag in ('td','th') and self.row is not None:self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:self.row.append(' '.join(' '.join(self.cell).split()));self.cell=None
        if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None

def qwen_detail(doc,entity):
    url=urlsplit(doc['source_url'])
    if url.scheme!='https' or url.netloc!='www.alibabacloud.com' or not re.fullmatch(r'/help/en/model-studio/[A-Za-z0-9-]+\.md',url.path) or url.query or url.fragment or access_gate(doc['text']):raise ValueError('unapproved/blocked Qwen detail')
    text=formal_text(doc['text']);matches=[]
    for number,line in enumerate(text.splitlines(),1):
        m=re.fullmatch(r'Model ID(?: \(the value of the `model` parameter\))?: `([^`]+)`',line)
        if m:matches.append((number,line,m[1]))
    request_id_explicit=bool(matches)
    service_declarations=[]
    if not matches:
        for number,line in enumerate(text.splitlines(),1):
            m=re.fullmatch(r'The inference service provider for `([^`]+)` is ([^.]+)\.',line)
            if m:service_declarations.append(dict(line=number,quote=line,provider=m[2]));matches.append((number,line,m[1]))
    if len(matches)!=1 or canonical_id(matches[0][2])!=matches[0][2]:raise ValueError('unique formal model parameter/service declaration missing')
    number,identity_quote,mid=matches[0];outputs=[];provider=[];evidence=[]
    for ln,line in enumerate(text.splitlines(),1):
        if 'Output Modality' not in line and 'Model Provider' not in line:continue
        parser=CapabilityRows();parser.feed(line);parser.close()
        for row in parser.rows:
            for index,label in enumerate(row[:-1]):
                if label=='Output Modality':
                    values=row[index+1].split();known={'Text':'text','Image':'image','Video':'video','Audio':'audio'}
                    if not values or any(v not in known for v in values):raise ValueError('unreviewed explicit output modality')
                    outputs.append(set(known[v] for v in values));evidence.append(dict(line=ln,quote=line))
                if label=='Model Provider':provider.append(row[index+1])
    agreed=set.intersection(*outputs) if outputs else set();possible=set.union(*outputs) if outputs else set()
    proof=dict(qualified(dict(doc,vendor='阿里云 Qwen',channel='pay_as_you_go',catalog_source_url=QWEN+'models')),identity_quote=identity_quote,identity_line=number,output_declarations=evidence,model_provider_declarations=provider)
    # A documented Model Studio invocation ID is NOT automatically an Alibaba-origin model.
    # Without explicit provider evidence retain a nonformal observation, never native certify.
    native=bool(request_id_explicit and provider and set(provider)<={'Alibaba Cloud','Qwen','Tongyi Qianwen','Wan','HappyHorse'})
    return dict(model_id=mid if native else None,observed_model_id=mid,api_id_explicit=native,catalog_observation=not native,display_name=entity['display_name'],identity_evidence=proof,request_parameter_ID_explicit=request_id_explicit,inference_service_provider_evidence=service_declarations,output_modalities=sorted(agreed),unknown_output_modalities=sorted(possible-agreed) if outputs else ['text','image','audio','video'],native_vendor_status='verified_explicit_provider' if native else 'unknown_provider_not_explicit',channel_applicability='unknown',channel_unknown_reasons=['platform request declaration does not establish native-author global catalog or account entitlement'],lifecycle_status='unconfirmed',alias_status='unknown_no_direct_mapping',scope_status='pending_catalog_provider_and_universe',line=number)

def xai_subscription_urls(text):
    if access_gate(text):raise ValueError('blocked official documentation index')
    urls=[]
    for part in sections(text):
        if part['name'] not in ('Grok Build','The X Subscription'):continue
        for number,line in part['lines']:
            m=re.fullmatch(r'- \[([^]]+)\]\((https://docs\.x\.ai/(?:build|x-subscription)/[A-Za-z0-9/-]+\.md)\)(?::.*)?',line)
            if not line.strip():continue
            if not m:raise ValueError('unparsed subscription documentation index row')
            urls.append(m[2])
    if not urls or len(urls)!=len(set(urls)) or len(urls)>100:raise ValueError('empty/duplicate/oversized subscription documentation section')
    return sorted(urls)

def xai_subscription_catalog(doc):
    """Only an explicitly subscription-native literal model table can enumerate.

    Config examples, custom/BYOK endpoints, API-key catalogs and generic model
    placeholders remain nonformal evidence. No fallback to PAYG's IDs.
    """
    url=urlsplit(doc['source_url'])
    if url.scheme!='https' or url.netloc!='docs.x.ai' or not re.fullmatch(r'/(?:build|x-subscription)/[A-Za-z0-9/-]+\.md',url.path) or url.query or url.fragment or access_gate(doc['text']):raise ValueError('unapproved subscription catalog source')
    text=formal_text(doc['text']);rows=[]
    for part in sections(text):
        if part['name']!='Subscription model catalog':continue
        lines=part['lines'];header='| Model ID | Output modalities | Lifecycle |'
        if header not in [line for _,line in lines]:raise ValueError('unreviewed subscription model table header')
        for number,line in lines:
            m=re.fullmatch(r'\| `([^`]+)` \| (text|image|video|audio)(?:, (text|image|video|audio))* \| (Available|Deprecated|Retired) \|',line)
            if not m:continue
            if canonical_id(m[1])!=m[1]:raise ValueError('nonliteral subscription model candidate')
            scoped=dict(doc,vendor='xAI',channel='subscription',catalog_source_url=doc['source_url']);modes=[v.strip() for v in line.split('|')[2].split(',')]
            claims=[claim(scoped,m[1],'identity',line=number,quote=line,role='explicit_subscription_native_catalog'),claim(scoped,m[1],'output',values=modes,line=number,quote=line),claim(scoped,m[1],'native_channel',status='verified',reason='explicit subscription-native literal model table',line=number,quote=line),claim(scoped,m[1],'lifecycle',status={'Available':'listed','Deprecated':'deprecated','Retired':'retired'}[m[4]],line=number,quote=line)]
            rows.append(dict(model_id=m[1],api_id_explicit=True,catalog_observation=False,identity_evidence=dict(qualified(scoped),line=number,quote=line),**project(claims)))
    return rows
