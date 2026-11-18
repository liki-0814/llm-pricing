"""Bounded public text-directory contracts. No prices, guessed IDs or network I/O."""
import copy,html,re
from html.parser import HTMLParser
import catalog_diff as c


def clean(value):
 return re.sub(r'\s+',' ',value.replace('\ufeff','').replace('\u200b','')).strip()


class Tables(HTMLParser):
 """Parse actual HTML elements, never embedded script strings; reject broken tables."""
 def __init__(self,text):
  super().__init__(convert_charrefs=True);self.tables=[];self.headings=[];self.path={};self.heading=None;self.table=None;self.row=None;self.cell=None;self.cell_kind=None;self.paragraph=None;self.paragraphs=[];self.code=None;self.skip=0;self.html_open=0;self.html_close=0;self.body_close=0;self.article_open=0;self.article_close=0;self.links=[]
  if not isinstance(text,str) or not text:raise ValueError('HTML source must be nonempty text')
  self.feed(text);self.close()
  if self.html_open!=1 or self.html_close!=1 or self.body_close!=1 or any(x is not None for x in (self.table,self.row,self.cell,self.heading,self.paragraph,self.code)):raise ValueError('incomplete HTML/table termination')
 def handle_starttag(self,tag,attrs):
  if self.html_close:raise ValueError('content after closed HTML')
  if tag in ('script','style'):self.skip+=1;return
  if self.skip:return
  if tag=='html':self.html_open+=1
  if tag=='article':self.article_open+=1
  if tag=='a':self.links.append(dict(attrs))
  if tag in ('h1','h2','h3','h4','h5','h6'):
   if self.heading is not None:raise ValueError('nested heading')
   self.heading=[tag,[]]
  if tag=='table':
   if self.table is not None:raise ValueError('nested table')
   self.table={'path':dict(self.path),'rows':[]}
  if tag=='tr':
   if self.table is None or self.row is not None:raise ValueError('invalid table row')
   self.row=[]
  if tag in ('td','th'):
   if self.row is None or self.cell is not None:raise ValueError('invalid table cell')
   self.cell=[];self.cell_kind=tag
  if tag=='p':
   if self.paragraph is not None:raise ValueError('nested paragraph')
   self.paragraph={'text':[],'codes':[],'path':dict(self.path)}
  if tag=='code' and self.paragraph is not None:self.code=[]
 def handle_data(self,data):
  if self.html_close and data.strip():raise ValueError('data after closed HTML')
  if self.skip:return
  if self.heading is not None:self.heading[1].append(data)
  if self.cell is not None:self.cell.append(data)
  if self.paragraph is not None:self.paragraph['text'].append(data)
  if self.code is not None:self.code.append(data)
 def handle_endtag(self,tag):
  if tag in ('script','style'):
   self.skip=max(0,self.skip-1);return
  if self.skip:return
  if tag in ('h1','h2','h3','h4','h5','h6'):
   if self.heading is None or self.heading[0]!=tag:raise ValueError('heading mismatch')
   label=clean(''.join(self.heading[1]));level=int(tag[1]);self.path={k:v for k,v in self.path.items() if k<level};self.path[level]=label;self.headings.append((level,label));self.heading=None
  if tag in ('td','th'):
   if self.cell is None or self.row is None or tag!=self.cell_kind:raise ValueError('unmatched cell end')
   self.row.append(clean(' '.join(self.cell)));self.cell=None;self.cell_kind=None
  if tag=='tr':
   if self.row is None or self.cell is not None:raise ValueError('unmatched row end')
   self.table['rows'].append(self.row);self.row=None
  if tag=='table':
   if self.table is None or self.row is not None or self.cell is not None:raise ValueError('unmatched table end')
   self.tables.append(self.table);self.table=None
  if tag=='code' and self.code is not None:
   self.paragraph['codes'].append(clean(''.join(self.code)));self.code=None
  if tag=='p':
   if self.paragraph is None:raise ValueError('unmatched paragraph end')
   self.paragraph['text']=clean(''.join(self.paragraph['text']));self.paragraphs.append(self.paragraph);self.paragraph=None
  if tag=='article':self.article_close+=1
  if tag=='html':self.html_close+=1
  if tag=='body':self.body_close+=1


def no_continuation(doc):
 if any('next' in link.get('rel','').split() or re.search(r'[?&](?:page|cursor|offset|continuation)=',link.get('href',''),re.I) for link in doc.links):raise ValueError('unresolved directory continuation link')


def source_is(source,vendor,url):
 return isinstance(source,dict) and (source.get('vendor'),source.get('channel'),source.get('role'),source.get('modalities'),source.get('url'))==(vendor,'pay_as_you_go','catalog',['text'],url)


def legal(token):
 return isinstance(token,str) and bool(token) and c.canonical_id(token)==token


def deepseek_contract(text,source):
 rows=[];proof={'verified':False,'method':'bounded_model_details_with_explicit_accepted_alias_routing'}
 try:
  if not source_is(source,'DeepSeek','https://api-docs.deepseek.com/quick_start/pricing/'):raise ValueError('DeepSeek original text source identity mismatch')
  doc=Tables(text);no_continuation(doc)
  if doc.article_open!=1 or doc.article_close!=1:raise ValueError('complete DeepSeek article boundary required')
  if any(level>2 for level,value in doc.headings):raise ValueError('unreviewed DeepSeek subsection')
  if [value for level,value in doc.headings if level==1]!=['Models & Pricing']:raise ValueError('unknown DeepSeek article title')
  expected=['Model Details','Web Search & Fetch Pricing','File Parsing & OCR Pricing','Speech Pricing','Deduction Rules']
  if [v for level,v in doc.headings if level==2]!=expected:raise ValueError('unknown/missing DeepSeek article sections')
  tables=[x for x in doc.tables if x['path'].get(2)=='Model Details']
  if len(tables)!=1 or not tables[0]['rows'] or tables[0]['rows'][0][0]!='MODEL':raise ValueError('one complete MODEL table required')
  if any(x is not tables[0] and x['rows'] and x['rows'][0][0]=='MODEL' for x in doc.tables):raise ValueError('unreviewed additional model table')
  for para in doc.paragraphs:
   if para['path'].get(2)=='Model Details' and not (para['text'].startswith('(1) Use ') or (not para['codes'] and (para['text'].startswith('(2) Off-peak rates are half of the peak rates.') or para['text'].startswith('(3) For more details on concurrency limits,')))):raise ValueError('unreviewed Model Details paragraph/footnote')
  allowed_rows={'MODEL','BASE URL (OpenAI Format)','BASE URL (Anthropic Format)','MODEL VERSION','THINKING MODE','CONTEXT LENGTH','MAX OUTPUT','FEATURES','Tool Calls','Responses API','Anthropic API','Chat Prefix Completion（Beta）','FIM Completion（Beta）','Vision','PRICING (2)','PEAK','1M INPUT TOKENS (CACHE MISS)','1M OUTPUT TOKENS','Concurrency Limit (3)'}
  table=tables[0]['rows']
  if any(not row or row[0] not in allowed_rows for row in table) or sum(row[0]=='MODEL' for row in table)!=1:raise ValueError('unknown/duplicate model table row schema')
  refs={ref for row in table for cell in row for ref in re.findall(r'\((\d+)\)',cell)}
  notes_present={m[1] for para in doc.paragraphs if para['path'].get(2)=='Model Details' for m in [re.match(r'\((\d+)\)',para['text'])] if m}
  if not refs.issubset(notes_present):raise ValueError('unresolved model-table footnote reference')
  ids=[re.sub(r'\s*\(\d+\)$','',x).strip() for x in table[0][1:]]
  if not ids or any(not legal(x) for x in ids) or len(set(ids))!=len(ids):raise ValueError('invalid/duplicate MODEL literal ID column')
  versions=[x for x in table if x[0]=='MODEL VERSION'];bases=[x for x in table if x[0]=='BASE URL (OpenAI Format)']
  if len(versions)!=1 or len(versions[0])!=len(ids)+1 or any(not x for x in versions[0][1:]):raise ValueError('MODEL VERSION columns do not bind every model')
  if len(bases)!=1 or bases[0][1:]!=['https://api.deepseek.com']:raise ValueError('native BASE URL not proven')
  for mid,entity in zip(ids,versions[0][1:]):rows.append({'model_id':mid,'api_id_explicit':True,'modality':'text','model_entity':entity,'origin_vendor':'DeepSeek','id_evidence':'literal MODEL invocation column'})
  notes=[p for p in doc.paragraphs if p['text'].startswith('(1) Use ')]
  if len(notes)!=1:raise ValueError('single accepted-alias routing footnote required')
  note=notes[0];codes=note['codes'];m=re.fullmatch(r'\(1\) Use (\S+) as the model name\. The legacy names (.+) are still accepted, but the corresponding models have been retired, their requests are served by the (\S+) model and billed at the Flash price\.',note['text'])
  if not m or len(codes)<2 or m[1]!=codes[0] or codes[0] not in ids:raise ValueError('unknown legacy alias routing semantics')
  aliases=re.split(r',\s*|\s+and\s+',m[2]);aliases=[x for x in aliases if x]
  if aliases!=codes[1:] or any(not legal(x) for x in codes) or len(set(codes))!=len(codes) or set(aliases)&set(ids):raise ValueError('alias literals missing/duplicate/conflicting')
  target=next(row for row in rows if row['model_id']==codes[0])
  if m[3]!=target['model_entity']:raise ValueError('alias served-by entity does not match target MODEL VERSION')
  for mid in aliases:
   evidence={'kind':'accepted_legacy_alias_not_retired_invocation','alias':mid,'canonical':codes[0],'served_by_entity':m[3],'previous_entity_retired':True,'quote':note['text']}
   rows.append({'model_id':mid,'api_id_explicit':True,'modality':'text','origin_vendor':'DeepSeek','alias_of':codes[0],'lifecycle_status':'accepted_alias','previous_entity_retired':True,'retired_at':None,'identity_evidence':evidence})
  if 'Product prices may vary and DeepSeek reserves the right to adjust them.' not in text:raise ValueError('Deduction Rules terminal paragraph missing')
  proof.update(verified=True,expected_record_count=len(rows),current_model_ids=ids,accepted_aliases=aliases,pagination_termination='complete Model Details table, explicit alias footnote, Deduction Rules and closed HTML')
 except (ValueError,KeyError,TypeError,AttributeError,IndexError) as error:proof['error']=str(error)
 return rows,proof


def native_hunyuan_identity(row):
 return isinstance(row,dict) and isinstance(row.get('display_name'),str) and legal(row.get('model_id')) and bool(re.match(r'^(?:hy(?=[-\d])|hunyuan|混元)',row['display_name'],re.I)) and bool(re.match(r'^(?:hy(?=[-\d])|hunyuan)',row['model_id'],re.I))


def hunyuan_text_contract(text,source):
 rows=[];reseller=[];proof={'verified':False,'method':'native_brand_and_invocation_in_all_text_output_sections'}
 try:
  if not source_is(source,'腾讯混元','https://cloud.tencent.com/document/product/1823/130051'):raise ValueError('Hunyuan original text source identity mismatch')
  doc=Tables(text);no_continuation(doc)
  if [value for level,value in doc.headings if level==1]!=['模型列表'] or any(level>3 for level,value in doc.headings):raise ValueError('unknown Hunyuan article structure')
  supported_subsections={'图像生成','视频生成','3D 生成','深度思考','结构化输出','Function Calling','Cache 缓存','图片、视频理解'}
  if any(level==3 and value not in supported_subsections for level,value in doc.headings):raise ValueError('unreviewed Hunyuan subsection')
  if any(table['path'].get(2) not in ('语言模型','视觉模型','语音模型','多模态理解模型','向量模型') for table in doc.tables):raise ValueError('table outside reviewed model sections')
  expected=['本页目录：','语言模型','视觉模型','语音模型','多模态理解模型','向量模型','能力说明']
  if [v for level,v in doc.headings if level==2]!=expected:raise ValueError('unknown/missing Hunyuan model-section boundary')
  native_brand=re.compile(r'^(?:hy(?=[-\d])|hunyuan|混元)',re.I);native_id=re.compile(r'^(?:hy(?=[-\d])|hunyuan)',re.I)
  third_brand=re.compile(r'^(?:DeepSeek|GLM|Kimi|MiniMax|MiMo|Step|YT-)',re.I)
  sections={}
  for section in ('语言模型','多模态理解模型'):
   tables=[x for x in doc.tables if x['path'].get(2)==section]
   if len(tables)!=1:raise ValueError('required text section needs exactly one full invocation table: '+section)
   table=tables[0]['rows'];header=table[0]
   if len(header)<2 or header[:2]!=['模型名称','model（调用参数）'] or len(table)<2:raise ValueError('unsupported invocation table header')
   section_ids=[]
   for cells in table[1:]:
    if len(cells)!=len(header) or not cells[0]:raise ValueError('incomplete text invocation row')
    ids=cells[1].split()
    if not ids or any(not legal(x) for x in ids) or len(set(ids))!=len(ids):raise ValueError('nonliteral/malformed invocation cell')
    branded_native=bool(native_brand.match(cells[0]));branded_third=bool(third_brand.match(cells[0]))
    if not branded_native and not branded_third:raise ValueError('unknown model origin; not safe to classify by hosting page')
    for mid in ids:
     if branded_native!=bool(native_id.match(mid)):raise ValueError('native display brand/invocation identity conflict')
     row={'model_id':mid,'api_id_explicit':True,'display_name':cells[0],'modality':'text','catalog_section':section,'id_evidence':'literal model（调用参数） cell; brand evidence is separate','origin_vendor':'腾讯混元' if branded_native else 'tokenhub_reseller'}
     if branded_native:rows.append(row);section_ids.append(mid)
     else:row['scope_status']='tokenhub_third_party_not_native_hunyuan';reseller.append(row)
   if not section_ids:raise ValueError('native text section is empty: '+section)
   sections[section]=section_ids
  if len({x['model_id'] for x in rows})!=len(rows):raise ValueError('duplicate native text invocation rows')
  proof.update(verified=True,expected_record_count=len(rows),text_sections=sections,reseller_count=len(reseller),pagination_termination='both text-output sections fully enumerated to 能力说明 and closed HTML; no continuation section')
 except (ValueError,KeyError,TypeError,AttributeError,IndexError) as error:proof['error']=str(error)
 return rows,reseller,proof


def anthropic_retired_bridges(rows,status_text):
 """Only an explicit single-entity notice can bridge a display name to an ID.
 Multi-entity retirement groups remain pending: never guess by ID typography.
 """
 out=copy.deepcopy(rows)
 if isinstance(status_text,str):status_text='\n'+status_text
 if not isinstance(status_text,str) or '\n## Deprecation history\n' not in status_text or '\n## API parameter deprecations\n' not in status_text:return out
 history=status_text.split('\n## Deprecation history\n',1)[1].split('\n## API parameter deprecations\n',1)[0]
 blocks=re.split(r'(?m)^### ',history)
 for row in out:
  name=row.get('display_name')
  if row.get('api_id_explicit') or row.get('lifecycle_status')!='retired' or not isinstance(name,str):continue
  hits=[]
  for block in blocks:
   direct=re.search(r'Anthropic notified developers using '+re.escape(name)+r' of its upcoming retirement on the Claude API\.',block)
   if not direct:continue
   tables=re.findall(r'^\| Retirement date[^\n]*\n(?:^\|[^\n]*\n?)+',block,re.M)
   if len(tables)!=1:continue
   lines=tables[0].splitlines();header=[x.strip() for x in lines[0].strip('|').split('|')]
   if header not in (['Retirement date','Model','Recommended replacement'],['Retirement date','Deprecated model','Recommended replacement']):continue
   entries=[];valid=True
   for line in lines[1:]:
    cells=[x.strip() for x in line.strip('|').split('|')]
    if len(cells)==3 and all(re.fullmatch(r'[-: ]+',x) for x in cells):continue
    if len(cells)!=3:valid=False;break
    mid=re.fullmatch(r'`([^`]+)`',cells[1])
    if not mid or not legal(mid[1]):valid=False;break
    entries.append((mid[1],line))
   if valid and len(entries)==1:hits.append((entries[0],direct[0],block.splitlines()[0]))
  if len(hits)!=1:continue
  (mid,line),quote,heading=hits[0]
  row.update(model_id=mid,literal_id=mid,api_id_explicit=True,catalog_observation=False,retired_at=None,identity_evidence={'kind':'explicit_single_entity_Claude_API_retirement_notice','display_name':name,'literal_api_id':mid,'notice_quote':quote,'table_quote':line,'notice_heading':heading})
 return out
