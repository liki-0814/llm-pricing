"""Literal official model-ID bridges. No slug/name canonicalization or price writes."""
import ast,json,re
from urllib.parse import urlsplit,urljoin,unquote
import catalog_diff as c

def allowed_detail(url,vendor):
 p=urlsplit(url)
 prefixes={'OpenAI':('developers.openai.com','/api/docs/models/'),
  'Anthropic':('platform.claude.com','/docs/en/models/'),
  'MiniMax':('platform.minimax.io','/docs/guides/')}
 if vendor not in prefixes:return False
 host,prefix=prefixes[vendor]
 return bool(p.scheme=='https' and p.hostname==host and not p.username and not p.password
  and not p.query and not p.fragment and p.path.startswith(prefix) and p.path.endswith('.md')
  and '..' not in unquote(p.path).split('/'))

def pending(name,line,url=None,section=None,quote=None):
 return dict(model_id=None,api_id_explicit=False,catalog_observation=True,display_name=name,
  line=line,detail_url=url,catalog_section=section,lifecycle_status='retired' if quote and 'Shut down.' in quote else 'unconfirmed',
  lifecycle_quote=quote if quote and 'Shut down.' in quote else None,retired_at=None)

def openai_directory(text):
 rows=[];section=None
 for i,line in enumerate(text.splitlines(),1):
  if line.startswith('## '):section=line[3:]
  m=re.match(r'- \[([^]]+)\]\(([^)]+)\):?(.*)',line)
  if not m:continue
  href=urljoin('https://developers.openai.com',m[2]);inline=re.search(r'Model ID:\s*`([^`]+)`',m[3])
  if not (allowed_detail(href,'OpenAI') or inline):continue
  row=pending(m[1],i,href,section,line)
  if inline and c.canonical_id(inline[1]):row.update(model_id=inline[1],api_id_explicit=True,catalog_observation=False,id_evidence='directory literal Model ID')
  rows.append(row)
 return rows

def openai_ids(text):
 ids=re.findall(r'(?im)^Model ID:\s*`([^`]+)`',text)
 match=re.search(r'(?m)^## (?:Model IDs|Snapshots)\s*\n(.*?)(?=^## |\Z)',text,re.S)
 if match:
  ids+=re.findall(r'(?m)^- `([^`]+)`',match[1])
 return list(dict.fromkeys(x for x in ids if c.canonical_id(x)))

def anthropic_directory(text):
 rows=[];section=False
 for i,line in enumerate(text.splitlines(),1):
  if line=='## All models':section=True;continue
  if section and line.startswith('## '):break
  if not section or not line.startswith('| '):continue
  cells=[x.strip() for x in line.strip('|').split('|')]
  if not cells[0].startswith(('Claude ','[Claude ')):continue
  m=re.search(r'\[([^]]+)\]\((https://platform\.claude\.com/docs/en/models/[^)]+)\)',cells[0])
  name=m[1] if m else cells[0].split(' (')[0]
  row=pending(name,i,m[2]+'.md' if m else None,'all_models')
  if 'retired' in cells[0]:row.update(lifecycle_status='retired',lifecycle_quote=cells[0])
  rows.append(row)
 return rows

def anthropic_ids(text):
 import discovery_anthropic_contracts as native
 doc=dict(text=text,source_url=native.ROOT,source_sha256=None,observed_at=None)
 # ID projection is not capture validation: an unproven identity must not
 # turn a hash-checked child body into a fetch failure before observation union.
 try:claims=native.detail_claims(doc,strict=False)
 except native.DetailClaimsError:return []
 return list(dict.fromkeys(x['model_id'] for x in claims if x['kind'] in ('canonical','alias')))

def anthropic_status(text):
 import discovery_anthropic_contracts as native
 doc=dict(text=text,source_url=native.STATUS,source_sha256=None,observed_at=None)
 rows,_=native.aggregate(native.status_claims(doc,strict=False))
 for row in rows:row.pop('identity_evidence',None)  # Capture provenance is attached by the runner, not fabricated here.
 return rows

def minimax_ids(text):
 ids=re.findall(r'["\']model["\']\s*:\s*["\']([^"\']+)["\']|\bmodel\s*=\s*["\']([^"\']+)["\']',text)
 found=[a or b for a,b in ids]
 # Static, single-assignment def/use only. Never execute documentation examples,
 # import their modules, read environment variables, or resolve expressions.
 for block in re.finditer(r'(?m)^(`{3,}|~{3,})python[^\n]*\n(.*?)(?=^\1[ \t]*$)',text,re.S):
  try:tree=ast.parse(block[2])
  except SyntaxError:continue
  constants={}
  for stmt in tree.body:
   if isinstance(stmt,ast.Assign) and len(stmt.targets)==1 and isinstance(stmt.targets[0],ast.Name) and isinstance(stmt.value,ast.Constant) and isinstance(stmt.value.value,str):
    name=stmt.targets[0].id
    writes=sum(isinstance(n,ast.Name) and isinstance(n.ctx,(ast.Store,ast.Del)) and n.id==name for n in ast.walk(tree))
    shadows=any((isinstance(n,ast.arg) and n.arg==name) or (isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name==name) or (isinstance(n,ast.alias) and (n.asname or n.name.split('.')[0])==name) or (isinstance(n,ast.ExceptHandler) and n.name==name) for n in ast.walk(tree))
    if writes==1 and not shadows:constants[name]=stmt.value.value
  for node in ast.walk(tree):
   if isinstance(node,ast.Dict):
    for key,value in zip(node.keys,node.values):
     if isinstance(key,ast.Constant) and key.value=='model' and isinstance(value,ast.Name) and value.id in constants:found.append(constants[value.id])
 if '| `model` | See [Supported Models](#supported-models) above |' in text:
  section=re.search(r'### Supported Models(.*?)(?=^### |\Z)',text,re.S|re.M)
  if section:
   for l in section[1].splitlines():
    if l.startswith('| '):
     token=l.strip('|').split('|')[0].strip()
     if c.canonical_id(token):found.append(token)
 return list(dict.fromkeys(x for x in found if c.canonical_id(x)))

def zai_request_models(text):
 rows={};proof={'verified':False,'method':'closed_public_OpenAPI_request_model_enums','scope':'documented Z.ai PAYG text/image API, not account entitlement'}
 try:
  spec=json.loads(text)
  schemas=spec.get('components',{}).get('schemas',{})
  annotations={'title','description','example','default','deprecated'}
  def object_only(value):
   return value=='object' or value==['object']
  def string_only(value):
   return value=='string' or value==['string']
  def local_ref(node,seen):
   ref=node['$ref'];prefix='#/components/schemas/'
   if not isinstance(ref,str) or not ref.startswith(prefix) or ref in seen:raise ValueError('unresolved/cyclic request ref')
   if set(node)-{'$ref'}-annotations:raise ValueError('unsupported semantic siblings of request ref')
   resolved=schemas[ref[len(prefix):]]
   if not isinstance(resolved,dict) or not resolved:raise ValueError('request ref does not resolve to a nonempty schema')
   return resolved,seen+(ref,)
  def models(node,seen=()):
   if not isinstance(node,dict) or not node:raise ValueError('request branch is not a nonempty schema')
   if any(key in node for key in ('allOf','not','if','then','else')):raise ValueError('unsupported request composition')
   if '$ref' in node:
    resolved,next_seen=local_ref(node,seen);return models(resolved,next_seen)
   combinations=[key for key in ('oneOf','anyOf') if key in node]
   if combinations:
    if set(node)-set(combinations)-annotations-{'type'}:raise ValueError('unsupported mixed request composition keywords')
    if 'type' in node and not object_only(node['type']):raise ValueError('request composition is not an object request')
    if len(combinations)!=1:raise ValueError('ambiguous multiple request compositions')
    branches=node[combinations[0]]
    if not isinstance(branches,list) or not branches:raise ValueError('request composition has no nonempty branch list')
    ids=[]
    for branch in branches:
     branch_ids=models(branch,seen)
     if not branch_ids:raise ValueError('request composition contains an empty model branch')
     ids.extend(branch_ids)
    return ids
   # properties.model only constrains object instances; the branch itself must
   # prove it is an object request before the enum can close the model set.
   if set(node)-annotations-{'type','properties','required'}:raise ValueError('unsupported request schema keywords')
   if 'type' not in node or not object_only(node['type']):raise ValueError('request branch is not a supported object schema')
   if 'required' in node and (not isinstance(node['required'],list) or any(not isinstance(x,str) for x in node['required'])):raise ValueError('invalid object required list')
   props=node.get('properties')
   if not isinstance(props,dict) or not props:raise ValueError('object request has no property map')
   field=props.get('model',{})
   if not isinstance(field,dict):raise ValueError('request model field is not a schema')
   while '$ref' in field:field,seen=local_ref(field,seen)
   if any(key in field for key in ('oneOf','anyOf','allOf','not','if','then','else')):raise ValueError('unsupported model-field composition')
   if 'type' in field and not string_only(field['type']):raise ValueError('request model enum not closed/valid')
   values=field.get('enum')
   if not isinstance(values,list) or not values or any(not isinstance(x,str) or c.canonical_id(x)!=x for x in values):raise ValueError('request model enum not closed/valid')
   return values
  def effective_servers(path_item,operation):
   # OpenAPI precedence is operation > path > root. Presence of an invalid/empty
   # override is not permission to fall back to a less-specific native server.
   for level,node in (('operation',operation),('path',path_item),('root',spec)):
    if 'servers' not in node:continue
    servers=node['servers']
    if not isinstance(servers,list) or not servers:raise ValueError('empty/invalid effective '+level+' servers')
    urls=[]
    for server in servers:
     if not isinstance(server,dict) or server.get('url')!='https://api.z.ai/api':raise ValueError('unapproved effective '+level+' server')
     urls.append(server['url'])
    return level,urls
   raise ValueError('no explicitly approved effective request server')
  routes={'/paas/v4/chat/completions':'text','/paas/v4/images/generations':'image','/paas/v4/async/images/generations':'image'}
  unexpected=[path for path,node in spec.get('paths',{}).items() if 'post' in node and any(marker in path for marker in ('/images/','/chat/','/responses')) and path not in routes]
  if unexpected:raise ValueError('unreviewed text/image request routes: '+str(unexpected))
  evidence=[];modality_ids={'text':set(),'image':set()}
  for route,modality in routes.items():
   path_item=spec['paths'][route];operation=path_item['post']
   level,servers=effective_servers(path_item,operation)
   node=operation['requestBody']['content']['application/json']['schema']
   ids=models(node)
   if not ids:raise ValueError('required request route has no model IDs: '+route)
   modality_ids[modality].update(ids)
   evidence.append({'request_path':route,'modality':modality,'literal_ids':ids,'effective_server_level':level,'effective_servers':servers})
   for mid in ids:
    rows.setdefault(mid,dict(model_id=mid,api_id_explicit=True,origin_vendor='智谱 Z.ai',modality=modality,
     id_evidence='OpenAPI request model enum',line_basis='JSON pointer paths/'+route+'/post/requestBody'))
  if any(not ids for ids in modality_ids.values()):raise ValueError('claimed modality has no legal model enum')
  proof.update(verified=True,expected_record_count=len(rows),requests=evidence,modality_record_counts={key:len(ids) for key,ids in modality_ids.items()},pagination_termination='one complete JSON document and closed enum for every text/image request branch')
 except (ValueError,KeyError,TypeError,AttributeError) as e:proof['error']=str(e)
 return list(rows.values()),proof


def kimi_payg_proof(text,source,records):
 """Finite official Model List, current plus deprecated, not a pricing proof."""
 native=(source.get('vendor'),source.get('channel'),source.get('url'),source.get('modalities'),source.get('role'))==('Moonshot Kimi','pay_as_you_go','https://platform.kimi.ai/docs/models.md',['text'],'catalog')
 rows=[];tables=0;in_table=False
 for line in text.splitlines():
  if line.startswith('| Model Name |'):tables+=1;in_table=True;continue
  if not line.startswith('|'):in_table=False;continue
  if in_table:
   first=line.strip('|').split('|')[0].strip()
   if re.fullmatch(r'[-: ]+',first):continue
   m=re.fullmatch(r'`([^`]+)`',first);rows.append(m[1] if m and c.canonical_id(m[1]) else None)
 heads=[line for line in text.splitlines() if line.startswith('## ')]
 allowed=['## Multi-modal Model','## Deprecated Models']
 terminal='For further assistance, please [contact sales](https://platform.kimi.ai/contact-sales).' in text
 ids=[row.get('model_id') for row in records]
 ok=bool(native and '# Model List' in text and 'currently available Kimi' in text and 'discontinued models' in text and heads==allowed and tables==2 and rows and all(rows) and len(rows)==len(set(rows)) and rows==ids and terminal and not re.search(r'(?:[?&]page=|rel=["\']next)',text,re.I))
 return dict(verified=ok,expected_record_count=len(rows),method='official_native_Model-List_current_and_deprecated_tables_to_contact-sales_terminal',scope='documented PAYG text model directory; eligibility is per description, not global retirement',terminal_section_present=terminal)
