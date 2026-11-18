"""Finite native Google model-directory proofs. No prices, guessed IDs or I/O.

All model rows and continuation endpoints are retained. Explicit detail Model/Agent
code and Versions bind output types; input modalities never prove output scope.
"""
import hashlib,html,re
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit,unquote
import catalog_diff as c

ROOT_URL='https://aistudio.google.com/docs/models'
TAIL=['Audio models','Generative media models','Music generation models','Tool and agent models','Specialized task models','Previous models','Model version name patterns','Model deprecations']
PROPERTIES={'Model code','Agent code','Supported data types','Token limits','Versions','Latest update','Pricing','Capabilities','Consumption options','Model card','Knowledge cutoff','Limits','Rate limits','Audio limits','Streaming limits'}
OUTPUTS={'text':('text',),'audio':('audio',),'image and text':('image','text'),'text and audio':('text','audio'),'audio and text':('audio','text'),'audio (mp3), text (lyrics)':('audio','text'),'text (cited reports), images':('text','image'),'text embeddings':('embedding',),'video with native audio, text':('video','audio','text'),'video':('video',),'calibrated probabilities (yes/no, choice, and score, with 0 output tokens)':('probability',),'text, word annotations':('text','word_annotations'),'audio (raw 16-bit pcm)':('audio',),'audio (translated speech) and text (transcript)':('audio','text')}

def clean(value):return re.sub(r'\s+',' ',value).strip()

class Payload(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.parts=[];self.inside=False;self.count=0
 def handle_starttag(self,tag,attrs):
  if tag=='pre':
   if self.inside:raise ValueError('nested HTML documentation payload')
   self.inside=True;self.count+=1
 def handle_endtag(self,tag):
  if tag=='pre':
   if not self.inside:raise ValueError('unmatched documentation payload')
   self.inside=False
 def handle_data(self,data):
  if self.inside:self.parts.append(data)

def document(value):
 if not isinstance(value,str) or not value or '\ufffd' in value:raise ValueError('nonempty UTF-8 text required')
 if '<html' in value[:1000].lower():
  if not value.rstrip().lower().endswith('</html>'):raise ValueError('truncated HTML document')
  p=Payload();p.feed(value);p.close()
  if p.count!=1 or p.inside:raise ValueError('one complete documentation pre required')
  value=''.join(p.parts)
 # Heading id/class annotations are not open block directives. All other
 # directives must be known and balanced; hidden conditional schemas are refused.
 stack=[];known={'section','table','card','card-grid','callout','button','sup','icon','badge','tabs','tab'}
 for m in re.finditer(r'{%\s*(.*?)\s*%}',value,re.S):
  token=m[1].strip()
  if re.fullmatch(r'(?:(?:id|class)="[^"]*"\s*)+',token):continue
  tag=token.split()[0]
  if tag.lstrip('/') not in known:raise ValueError('unknown template directive: '+tag)
  if tag.startswith('/'):
   if not stack or stack.pop()!=tag[1:]:raise ValueError('unbalanced template directive')
  elif not token.endswith('/'):stack.append(tag)
 if stack:raise ValueError('truncated template document')
 return value

def allowed_detail(url):
 if not isinstance(url,str):return False
 p=urlsplit(url)
 return bool(p.scheme=='https' and p.netloc=='aistudio.google.com' and not p.query and not p.fragment and not p.username and '..' not in unquote(p.path).split('/') and (re.fullmatch(r'/docs/models/[A-Za-z0-9._-]+\.md',p.path) or p.path=='/docs/robotics-overview.md'))

def tables(text):
 pattern=r'{% table(?: variant="model")? %}(.*?){% /table %}'
 found=list(re.finditer(pattern,text,re.S))
 if len(found)!=len(re.findall(r'{%\s*table(?:\s|%)',text)):raise ValueError('unknown/nested/unclosed table grammar')
 for match in found:
  chunks=re.split(r'(?m)^  ---\s*$',match[1]);parsed=[]
  for chunk in chunks:
   cells=re.split(r'(?m)^  \* ',chunk)
   if cells[0].strip():raise ValueError('unparsed content before table cells')
   cells=[x.strip() for x in cells[1:]]
   if not cells or any(not x for x in cells):raise ValueError('empty/unparsed table row')
   parsed.append(cells)
  header=parsed[0]
  if any(len(row)!=len(header) for row in parsed[1:]):raise ValueError('table cell count mismatch')
  if len(parsed)<2:raise ValueError('empty table is not a catalog proof')
  yield match.start(),header,parsed[1:]

def literal_list(cell):
 if not re.fullmatch(r'(?:`[^`]+`\s*)+',cell):raise ValueError('endpoint cell not a closed literal list')
 ids=re.findall(r'`([^`]+)`',cell)
 if len(ids)!=len(set(ids)) or any(c.canonical_id(mid)!=mid for mid in ids):raise ValueError('invalid/duplicate endpoint literal')
 return ids

def directory(value):
 text=document(value)
 if len(re.findall(r'^# Models\s*$',text,re.M))!=1:raise ValueError('native Models title absent')
 heads=[]
 for m in re.finditer(r'^## (.*)$',text,re.M):
  label=re.sub(r'\s*{%.*?%}\s*$','',m[1]).strip();heads.append((m.start(),label))
 labels=[x[1] for x in heads]
 if len(labels)!=len(set(labels)) or labels[-len(TAIL):]!=TAIL:raise ValueError('unknown/missing/reordered catalog sections')
 if not labels[:-len(TAIL)] or any(not re.fullmatch(r'(?:All )?Gemini [0-9]+(?:\.[0-9]+)?(?: [A-Za-z-]+)?(?: models)?',h) for h in labels[:-len(TAIL)]):raise ValueError('unreviewed family section grammar')
 terminal=text[heads[-1][0]:].split('\n',1)[1]
 if clean(terminal)!='For information about model deprecations, visit the [Gemini deprecations](/docs/deprecations) page.':raise ValueError('directory terminal missing/has trailing observations')
 if re.search(r'(?:[?&]page=|rel=["\']next|load more|next page)',text,re.I):raise ValueError('unclosed catalog pagination')
 rows=[];linked=set();seen_sections=set()
 for start,header,entries in tables(text):
  section=next(label for pos,label in reversed(heads) if pos<start)
  if header not in (['Model','Endpoint'],['Model','Description','Endpoint']):raise ValueError('unknown directory table header')
  if section in TAIL[-2:]:raise ValueError('model table after directory boundary')
  seen_sections.add(section)
  for cells in entries:
   name=cells[0];description=cells[1] if len(cells)==3 else '';links=re.findall(r'\[[^]]+\]\(([^)]+)\)',name)
   url=None
   if links:
    if len(links)!=1:raise ValueError('ambiguous model detail link')
    url=urljoin(ROOT_URL,links[0]);url=url if url.endswith('.md') else url+'.md'
    if not allowed_detail(url):raise ValueError('unapproved model detail URL')
    linked.add(url)
   retired='(Shut down)' in name or '(shut down)' in description
   for mid in literal_list(cells[-1]):rows.append(dict(model_id=mid,api_id_explicit=True,origin_vendor='Google Gemini',price_public=False,display_name=name,description=description,detail_url=url,catalog_section=section,line_basis='native template table Endpoint cell',lifecycle_status='retired' if retired else 'unconfirmed',lifecycle_quote=clean(name+' '+description) if retired else None,retired_at=None))
 if any(h not in seen_sections for h in TAIL[:-2]):raise ValueError('a required catalog section has no complete table')
 if not rows:raise ValueError('empty native directory')
 # Model cards are an independent presentation of entities, not ID authority.
 cardlinks=re.findall(r'{% card\s[^%]*?href="([^"]+)"',text)
 for href in cardlinks:
  if href.startswith('/docs/models/') and urljoin(ROOT_URL,href)+'.md' not in linked:raise ValueError('uncovered model card')
 codes=re.findall(r'\*Model code\*\s+\*\*([^*]+)\*\*',text)
 if any(mid not in {r['model_id'] for r in rows} for mid in codes):raise ValueError('uncovered explicit Model code card')
 references=re.findall(r'For example:\s*`([^`]+)`',text)
 return rows,dict(directory_row_count=len(rows),directory_literal_count=len({r['model_id'] for r in rows}),required_detail_urls=sorted(linked),reference_example_literals=references,termination='all native model/endpoint tables; version-pattern and deprecations terminal')

def detail_tables(value):
 """Classify EVERY table before any consumer may use or exclude its cells.

 Property tables pair literal invocation identity, output and Versions. The only
 supported non-model role is a native robotics guide-navigation section: heading,
 schema, non-code descriptive cells and native guide-only targets all corroborate
 that role. A header alone never authorizes ignoring a table. Unknown means stop.
 """
 text=document(value);result=[]
 for start,header,entries in tables(text):
  evidence=dict(position=start,header=header)
  if header==['Property','Description']:
   props={}
   for label,cell in entries:
    label=clean(re.sub(r'\[\[\*\]\]\([^)]+\)','',re.sub(r'{%.*?%}','',label,flags=re.S)))
    if label in props:raise ValueError('duplicate detail property')
    props[label]=cell
   if set(props)-PROPERTIES:raise ValueError('unknown model property grammar')
   identity=[key for key in ('Model code','Agent code') if key in props]
   if len(identity)!=1 or not {'Supported data types','Versions'}.issubset(props):raise ValueError('model identity/output/versions not paired')
   evidence.update(kind='model_properties',property_names=sorted(props),identity_property=identity[0],basis='known properties paired with one invocation identity, output and Versions')
   result.append((evidence,props));continue
  # This is a positive semantic classification, NOT an unknown-table fallback.
  headings=list(re.finditer(r'^#{1,6}\s+(.+)$',text[:start],re.M))
  heading=headings[-1][1] if headings else ''
  guides=[]
  if header==['Capability','Description','Guide'] and re.fullmatch(r'Robotics capabilities(?:\s+{% id="capabilities" %})?',heading) and entries:
   for name,description,target in entries:
    match=re.fullmatch(r'\[([^]`]+)\]\((/docs/robotics-[a-z0-9-]+)\)',target)
    if not match or not name.strip() or not description.strip() or any(ch in name+description for ch in '`[]<>') or clean(name) in PROPERTIES:break
    guides.append(urljoin(ROOT_URL,match[2]))
   else:
    evidence.update(kind='guide_navigation',heading=heading,rows=entries,guide_urls=guides,basis='native capability heading + guide schema + non-code descriptive cells + exclusively native robotics guide links')
    result.append((evidence,None));continue
  raise ValueError('unclassified native detail table: '+repr(header))
 return result

def aggregate_claims(claims):
 """One identity algebra for local AND cross-document claims, never first-wins.

 Literal Model/Agent code is stronger than a repeated family Versions list.
 All primary claims, or ALL alias claims when none are primary, are applicable.
 Contradictory outputs stay unknown (union minus intersection), never disappear.
 Every claim including weaker family context remains in the evidence.
 """
 preferred=[x for x in claims if x['primary']] or claims
 certain=set.intersection(*(set(x['output']) for x in preferred));possible=set.union(*(set(x['output']) for x in preferred))
 status={x['status'] for x in claims if x['status']}
 return dict(primary_identity=any(x['primary'] for x in claims),output_modalities=sorted(certain),unknown_output_modalities=sorted(possible-certain),identity_quote=[x['identity_quote'] for x in preferred],versions_quote=[x['versions_quote'] for x in claims],output_quote=[x['output_quote'] for x in preferred],lifecycle_status='retired' if status=={'Shut down'} else 'unconfirmed',lifecycle_quote='\n'.join(x['versions_quote'] for x in claims) if status=={'Shut down'} else None,routing_quotes=sorted(set(q for x in claims for q in x['route_quotes'])),declarations=claims)

def version_links(value):
 links=set()
 for evidence,props in detail_tables(value):
  if evidence['kind']=='guide_navigation':continue
  for label,cell in props.items():
   if 'Versions' not in label:continue
   for href in re.findall(r'\]\(([^)]+)\)',cell):
    if '/docs/models/' not in href:continue
    url=urljoin(ROOT_URL,href.split('#',1)[0]);url=url if url.endswith('.md') else url+'.md'
    if not allowed_detail(url):raise ValueError('unapproved version reference')
    links.add(url)
 return links

def primary_models(value):
 result={}
 for evidence,props in detail_tables(value):
  if evidence['kind']=='guide_navigation':continue
  for label,cell in props.items():
   label=clean(re.sub(r'{%.*?%}','',label,flags=re.S))
   if label not in ('Model code','Agent code'):continue
   cell=re.sub(r'^\*\*(?:Gemini API|Interactions API)\*\*\s*','',cell)
   for mid in literal_list(cell):result[mid]={'primary_identity':True}
 return result

def detail_models(value,reference_models=None):
 text=document(value);result={};declarations={};seen_model_table=False
 for evidence,props in detail_tables(text):
  if evidence['kind']=='guide_navigation':continue
  identity=[key for key in ('Model code','Agent code') if key in props]
  field=props[identity[0]]
  if 'Vertex' in field or 'Bedrock' in field:raise ValueError('mixed invocation platform identity')
  field=re.sub(r'^\*\*(?:Gemini API|Interactions API)\*\*\s*','',field)
  codes=literal_list(field);seen_model_table=True
  m=re.fullmatch(r'\*\*Inputs?\*\*\s*(.*?)\s*\*\*Outputs?\*\*\s*(.*?)\s*',props['Supported data types'],re.S)
  if not m or '**' in m[2]:raise ValueError('missing/ambiguous supported output declaration')
  output=OUTPUTS.get(clean(m[2]).lower())
  if not output:raise ValueError('unknown output type grammar: '+clean(m[2]))
  aliases=[];statuses={};route_quotes=[]
  version_text=re.sub(r'Read the \[model version patterns\]\(/docs/models#model-versions\)\s+for more details\.\s*','',props['Versions'],count=1)
  for line in version_text.splitlines():
   if not line.strip():continue
   if '`' not in line:
    ref=re.fullmatch(r'\s*(?:\*\s*)?(Shut down|Stable|Preview|Latest|Experimental|Deprecated): \[([^]]+)\]\(([^)]+)\)\s*',line)
    if ref:
     url=urljoin(ROOT_URL,ref[3].split('#',1)[0]);url=url if url.endswith('.md') else url+'.md'
     if not allowed_detail(url) or not reference_models or url not in reference_models:raise ValueError('version reference needs captured literal Model code')
     referenced=reference_models[url]
     primary=[mid for mid,data in referenced.items() if data.get('primary_identity')]
     if not primary:raise ValueError('version reference has no literal primary identity')
     for mid in primary:aliases.append(mid);statuses[mid]=ref[1]
    else:raise ValueError('unparsed nonliteral version declaration')
    continue
   line=line.replace('*Shut down*:', 'Shut down:')
   def linked_code(match):
    target=urljoin(ROOT_URL,match[2].split('#',1)[0]);target=target if target.endswith('.md') else target+'.md'
    if not allowed_detail(target):raise ValueError('foreign version-link identity')
    return '`'+match[1]+'`'
   line=re.sub(r'\[`([^`]+)`\]\(([^)]+)\)',linked_code,line)
   bare=re.fullmatch(r'\s*(?:\*\s*)?`([^`]+)`(?:\s+\((?:Unary|Live API)\))?\s*',line)
   if bare:
    if c.canonical_id(bare[1])!=bare[1]:
     if re.fullmatch(r'(?:Stable|Preview|Latest|Experimental|Deprecated): (.+)',bare[1]):pass
     else:raise ValueError('invalid literal version ID')
    else:aliases.append(bare[1]);continue
   embedded=re.fullmatch(r'\s*(?:\*\s*)?`(Stable|Preview|Latest|Experimental|Deprecated): ([^`]+)`\s*',line)
   if embedded:
    if embedded[2] not in codes:raise ValueError('version label cannot manufacture an API ID')
    aliases.append(embedded[2]);statuses[embedded[2]]=embedded[1];continue
   match=re.match(r'\s*(?:\*\s*)?(Stable|Preview|Latest|Experimental|Deprecated|Shut down|Max): `([^`]+)`(.*)$',line)
   if not match or c.canonical_id(match[2])!=match[2]:raise ValueError('unknown version declaration grammar')
   tail=match[3].strip()
   if tail and not (re.fullmatch(r'\(routes to `[^`]+` on [A-Za-z]+ [0-9]{1,2}, [0-9]{4}\)',tail) or re.fullmatch(r'\(effective [A-Za-z]+ [0-9]{1,2}, [0-9]{4}, automatically routed to `[^`]+`\)',tail)):raise ValueError('unknown version qualifier grammar')
   aliases.append(match[2]);statuses[match[2]]=match[1]
   if tail:route_quotes.append(line.strip())
  if not aliases:raise ValueError('empty version declaration')
  for mid in dict.fromkeys(codes+aliases):
   declarations.setdefault(mid,[]).append(dict(primary=mid in codes,output=sorted(output),table_position=evidence['position'],identity_quote=props[identity[0]],versions_quote=props['Versions'],output_quote=props['Supported data types'],status=statuses.get(mid),route_quotes=route_quotes))
 for mid,claims in declarations.items():result[mid]=aggregate_claims(claims)
 if not seen_model_table:raise ValueError('no native model property table')
 return result

def prove(value,source,docs):
 records=[];proof=dict(verified=False,method='native_Google_directory_tables_plus_literal_model_properties_and_versions',scope='all documented native directory model endpoints and explicit detail variants; text/video output, not account entitlement',modalities=['text','video'])
 try:
  if (source.get('vendor'),source.get('channel'),source.get('url'),source.get('role'),source.get('modalities'))!=('Google Gemini','pay_as_you_go',ROOT_URL,'catalog',['text','image','video']):raise ValueError('native source/channel contract mismatch')
  rows,evidence=directory(value)
  if not isinstance(docs,dict):raise ValueError('details must be a provenance map')
  root_urls=set(evidence['required_detail_urls'])
  if not root_urls.issubset(docs):raise ValueError('missing root-linked native detail captures')
  refs=set().union(*(version_links(docs[url]['text']) for url in root_urls))
  if set(docs)!=root_urls|refs:raise ValueError('missing or unindexed native version-reference captures')
  by_id={};models={};seeds={url:primary_models(doc['text']) for url,doc in docs.items()}
  for url in sorted((set(docs)-root_urls))+sorted(root_urls):
   doc=docs[url]
   if not isinstance(doc,dict) or doc.get('source_url')!=url:raise ValueError('detail source identity mismatch')
   c.parse_time(doc['observed_at'])
   if not isinstance(doc.get('source_sha256'),str) or not re.fullmatch(r'[0-9a-f]{64}',doc['source_sha256']):raise ValueError('detail raw hash missing')
   models[url]=detail_models(doc['text'],seeds)
  # Preserve raw claims from every page/table before aggregating any identity.
  claims_by_id={}
  for url,declared in sorted(models.items()):
   doc=docs[url]
   for mid,data in sorted(declared.items()):
    for claim in data['declarations']:
     claims_by_id.setdefault(mid,[]).append(dict(claim,source_url=url,source_sha256=doc['source_sha256'],observed_at=doc['observed_at'],capture_path=doc.get('capture_path')))
  aggregated={mid:aggregate_claims(claims) for mid,claims in sorted(claims_by_id.items())}
  for row in rows:
   mid=row['model_id'];url=row['detail_url']
   if url:
    if mid not in models[url]:raise ValueError('directory endpoint absent from explicit Model/Agent code or Versions: '+mid)
    witness=aggregated[mid]
   else:
    if row['description']!='Text-to-image model featuring fast and ultra-fast generation (shut down).' or row['lifecycle_status']!='retired':raise ValueError('unlinked endpoint has no supported explicit output witness')
    if mid in aggregated and (aggregated[mid]['output_modalities']!=['image'] or aggregated[mid]['unknown_output_modalities']):raise ValueError('conflicting unlinked directory/detail output attribution')
    witness=dict(output_modalities=['image'],unknown_output_modalities=[],identity_quote='native Endpoint cell',output_quote=row['description'],source_url=ROOT_URL)
   by_id.setdefault(mid,dict(row,identity_evidence=witness,output_modalities=witness['output_modalities'],unknown_output_modalities=witness.get('unknown_output_modalities',[])))
  # No alias/backend canonicalization, price filtering, or cross-page first-wins.
  for mid,data in aggregated.items():
   if mid in by_id:
    by_id[mid].update(identity_evidence=data,output_modalities=data['output_modalities'],unknown_output_modalities=data['unknown_output_modalities'])
   else:by_id[mid]=dict(model_id=mid,api_id_explicit=True,origin_vendor='Google Gemini',price_public=False,lifecycle_status=data['lifecycle_status'],lifecycle_quote=data['lifecycle_quote'],retired_at=None,unknown_output_modalities=data['unknown_output_modalities'],output_modalities=data['output_modalities'],identity_evidence=data,line_basis='native detail Model/Agent code or Versions literal')
  proof['detail_table_classifications']={url:[ev for ev,_ in detail_tables(docs[url]['text'])] for url in sorted(docs)}
  records=[by_id[mid] for mid in sorted(by_id)];counts={kind:sum(kind in row['output_modalities'] for row in records) for kind in proof['modalities']}
  decisions={kind:dict(verified=bool(counts[kind]) and not any(kind in row.get('unknown_output_modalities',[]) for row in records),unknown_ids=[row['model_id'] for row in records if kind in row.get('unknown_output_modalities',[])]) for kind in proof['modalities']}
  proven=[kind for kind in proof['modalities'] if decisions[kind]['verified']]
  proof.update(scope_decisions=decisions,modality_record_counts=counts,modalities=proven)
  if not proven:raise ValueError('no output scope has complete explicit attribution')
  proof.update(evidence,root_detail_urls=sorted(root_urls),version_reference_urls=sorted(refs-root_urls),verified=True,modalities=proven,scope_decisions=decisions,expected_record_count=len(records),modality_record_counts=counts,reference_example_policy='naming-convention examples are retained as references, not current endpoint declarations',detail_document_count=len(docs))
 except (ValueError,TypeError,KeyError,AttributeError,StopIteration) as error:proof['error']=str(error)
 return records,proof
