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
    return any(token in text.lower() for token in ('waf_block_deny','gateway-diagnostic','request rejected at client classification gate','captcha challenge','sessionstorage.x5referer','_____tmd_____/punish','x5secdata='))

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

def qwen_details(doc,entity):
    """Lossless per-H1 observations; no cross-version output/provider inheritance.

    A service-provider sentence or heading is not an invocation-ID or authorship
    declaration. Unsupported/blocked pages remain evidence, never empty catalogs.
    """
    url=urlsplit(doc['source_url'])
    if url.scheme!='https' or url.netloc!='www.alibabacloud.com' or not re.fullmatch(r'/help/en/model-studio/[A-Za-z0-9-]+\.md',url.path) or url.query or url.fragment:raise ValueError('unapproved Qwen detail')
    if access_gate(doc['text']):raise ValueError('access_blocked_HTTP_body_not_model_document')
    lines=formal_text(doc['text']).splitlines();starts=[];stops=[];snapshots=False
    for i,line in enumerate(lines):
        heading=re.match(r'^(#{1,6}) (.*)',line)
        if not heading:continue
        level=len(heading[1]);label=re.sub(r'\s*<span[^>]*>.*?</span>','',heading[2]).strip()
        if level==1:starts.append(i);snapshots=False
        elif level==2:
            if snapshots or label=='Snapshot Versions':stops.append(i)
            snapshots=label=='Snapshot Versions'
        elif level==3 and snapshots:starts.append(i)
    if not starts:starts=[0]
    elif any(line.strip() for line in lines[:starts[0]]):raise ValueError('unclassified preamble before model entities')
    rows=[]
    for start,next_start in zip(starts,starts[1:]+[len(lines)]):
        end=min([next_start]+[i for i in stops if start<i<next_start])
        block=lines[start:end];parameters=[];services=[];declarations=[];outputs=[];provider=[];evidence=[]
        for local,line in enumerate(block,start+1):
            m=re.fullmatch(r'Model ID(?: \(the value of the `model` parameter\))?: `([^`]+)`',line)
            if m:parameters.append((local,line,m[1]));declarations.append(dict(kind='explicit_model_parameter',line=local,quote=line,literal=m[1]))
            m=re.fullmatch(r'The inference service provider for `([^`]+)` is ([^.]+)\.',line)
            if m:services.append((local,line,m[1]));declarations.append(dict(kind='service_provider_NOT_origin',line=local,quote=line,literal=m[1],provider=m[2]))
            if 'Output Modality' not in line and 'Model Provider' not in line:continue
            parser=CapabilityRows();parser.feed(line);parser.close()
            for cells in parser.rows:
                for index,label in enumerate(cells[:-1]):
                    if label=='Output Modality':
                        values=cells[index+1].split();known={'Text':'text','Image':'image','Video':'video','Audio':'audio'}
                        if not values or any(v not in known for v in values):raise ValueError('unreviewed explicit output modality')
                        outputs.append(set(known[v] for v in values));evidence.append(dict(line=local,quote=line))
                    if label=='Model Provider':provider.append(cells[index+1])
        literals={x[2] for x in parameters or services};mid=next(iter(literals)) if len(literals)==1 else None
        valid_literal=bool(mid and canonical_id(mid)==mid);explicit=bool(parameters and valid_literal and len({p[2] for p in parameters})==1)
        native=bool(explicit and provider and set(provider)<={'Alibaba Cloud','Qwen','Tongyi Qianwen','Wan','HappyHorse'})
        header=re.sub(r'^#{1,6} ','',block[0]) if block and block[0].startswith('#') else entity['display_name']
        header=re.sub(r'\s*<span[^>]*>.*?</span>','',header).strip()
        agreed=set.intersection(*outputs) if outputs else set();possible=set.union(*outputs) if outputs else set()
        first=(parameters or services or [(start+1,block[0] if block else '',None)])[0]
        proof=dict(qualified(dict(doc,vendor='阿里云 Qwen',channel='pay_as_you_go',catalog_source_url=QWEN+'models')),identity_quote=first[1],identity_line=first[0],formal_declarations=declarations,output_declarations=evidence,model_provider_declarations=provider,entity_heading=header,entity_start_line=start+1,entity_end_line=end)
        rows.append(dict(model_id=mid if native else None,observed_model_id=mid if valid_literal else None,observed_entity_label=header,api_id_explicit=native,catalog_observation=not native,display_name=header,identity_evidence=proof,request_parameter_ID_explicit=explicit,inference_service_provider_evidence=[d for d in declarations if d['kind']=='service_provider_NOT_origin'],output_modalities=sorted(agreed),unknown_output_modalities=sorted(possible-agreed) if outputs else ['text','image','audio','video'],output_conflict=len({tuple(sorted(o)) for o in outputs})>1,native_vendor_status='verified_explicit_provider' if native else 'unknown_provider_not_explicit',channel_applicability='unknown',channel_unknown_reasons=['platform/service-provider declaration does not establish native author and PAYG entitlement'],lifecycle_status='unconfirmed',alias_status='unknown_no_direct_mapping',scope_status='pending_catalog_provider_and_universe',line=first[0],observation_status='literal_parameter_observed' if explicit else 'formal_service_entity_observed' if valid_literal else 'entity_heading_only_NOT_API_ID',unclassified_literal_declarations=declarations if len(literals)!=1 else []))
    return rows


def qwen_detail(doc,entity):
    """Single-entity compatibility surface; multi-entity callers use qwen_details."""
    rows=qwen_details(doc,entity)
    if len(rows)!=1:raise ValueError('multiple model entities require qwen_details')
    return rows[0]

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
