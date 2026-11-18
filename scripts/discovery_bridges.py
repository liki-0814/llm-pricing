"""Literal official model-ID bridges. No slug/name canonicalization or price writes."""
import json,re
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
  row=pending(m[1],i,href if allowed_detail(href,'OpenAI') else None,section,line)
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
 ids=[]
 for line in text.splitlines():
  cells=[x.strip() for x in line.strip('|').split('|')]
  if line.startswith('|') and cells[0]=='Claude API':ids+=re.findall(r'`([^`]+)`',' '.join(cells[1:]))
 return list(dict.fromkeys(x for x in ids if c.canonical_id(x)))

def anthropic_status(text):
 rows=[];active=False
 for i,line in enumerate(text.splitlines(),1):
  if line.startswith('## Model status'):active=True;continue
  if active and line.startswith('## '):break
  if not active or not line.startswith('|'):continue
  cells=[x.strip() for x in line.strip('|').split('|')]
  mid=c.canonical_id(cells[0].strip('`'))
  if not mid or len(cells)<4 or cells[1] not in ('Active','Deprecated','Retired'):continue
  rows.append(dict(model_id=mid,api_id_explicit=True,line=i,lifecycle_status=cells[1].lower(),
   lifecycle_quote=line,retired_at=None,retirement_date_original=cells[3],retirement_timezone=None))
 # Older retired IDs are explicitly enumerated in the history tables; never take replacement column.
 active=False
 for i,line in enumerate(text.splitlines(),1):
  if line.startswith('## Deprecation history'):active=True;continue
  if active and line.startswith('## API parameter'):break
  if not active or not line.startswith('|'):continue
  cells=[x.strip() for x in line.strip('|').split('|')]
  if len(cells)!=3:continue
  m=re.fullmatch(r'`([^`]+)`',cells[1])
  if m and c.canonical_id(m[1]) and not any(x['model_id']==m[1] for x in rows):
   rows.append(dict(model_id=m[1],api_id_explicit=True,line=i,lifecycle_status='unconfirmed_historical_notice',
    lifecycle_quote=line,retired_at=None,retirement_date_original=cells[0],retirement_timezone=None))
 return rows

def minimax_ids(text):
 ids=re.findall(r'["\']model["\']\s*:\s*["\']([^"\']+)["\']|\bmodel\s*=\s*["\']([^"\']+)["\']',text)
 found=[a or b for a,b in ids]
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
  if not any(x.get('url')=='https://api.z.ai/api' for x in spec.get('servers',[])):raise ValueError('native public API server missing')
  schemas=spec.get('components',{}).get('schemas',{})
  def models(node,seen=()):
   if '$ref' in node:
    ref=node['$ref'];prefix='#/components/schemas/'
    if not ref.startswith(prefix) or ref in seen:raise ValueError('unresolved/cyclic request ref')
    return models(schemas[ref[len(prefix):]],seen+(ref,))
   if 'oneOf' in node or 'anyOf' in node:
    branches=node.get('oneOf',node.get('anyOf'));return sum((models(x,seen) for x in branches),[])
   field=node.get('properties',{}).get('model',{})
   values=field.get('enum')
   if not isinstance(values,list) or not values or any(not isinstance(x,str) or c.canonical_id(x)!=x for x in values):raise ValueError('request model enum not closed/valid')
   return values
  routes={'/paas/v4/chat/completions':'text','/paas/v4/images/generations':'image','/paas/v4/async/images/generations':'image'}
  unexpected=[path for path,node in spec.get('paths',{}).items() if 'post' in node and any(marker in path for marker in ('/images/','/chat/','/responses')) and path not in routes]
  if unexpected:raise ValueError('unreviewed text/image request routes: '+str(unexpected))
  evidence=[]
  for route,modality in routes.items():
   node=spec['paths'][route]['post']['requestBody']['content']['application/json']['schema']
   ids=models(node);evidence.append({'request_path':route,'literal_ids':ids})
   for mid in ids:
    rows.setdefault(mid,dict(model_id=mid,api_id_explicit=True,origin_vendor='智谱 Z.ai',modality=modality,
     id_evidence='OpenAPI request model enum',line_basis='JSON pointer paths/'+route+'/post/requestBody'))
  proof.update(verified=True,expected_record_count=len(rows),requests=evidence,pagination_termination='one complete JSON document and closed enum for every text/image request branch')
 except (ValueError,KeyError,TypeError,AttributeError) as e:proof['error']=str(e)
 return list(rows.values()),proof
