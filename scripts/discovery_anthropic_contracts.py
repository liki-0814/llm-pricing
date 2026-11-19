"""Partial native Anthropic observation contracts. No network, examples or ID guessing.
Structural validation is not completeness: unknown current capabilities remain unknown.
"""
import json,re
from urllib.parse import urlsplit
import catalog_diff as c
ROOT='https://platform.claude.com/docs/en/models/overview.md'
STATUS='https://platform.claude.com/docs/en/about-claude/model-deprecations.md'
NOTES='https://platform.claude.com/docs/en/release-notes/overview.md'

def markdown_lines(text):
 # CommonMark line endings are CR, LF or CRLF, not Python's Unicode splitlines.
 lines=re.split(r'\r\n|\r|\n',text)
 if text.endswith(('\r','\n')):lines.pop()
 return lines

def prose_lines(text):
 """Top-level CommonMark 4.5 fences; yield original 1-based prose positions.
 0..3 ASCII spaces; >=3 identical ` or ~; backtick info cannot contain `.
 Only same-character runs >= opening length plus spaces/tabs can close.
 Tabs before a fence indent to column4+, so are not top-level fence markers.
 An unclosed code block consumes the remaining document, per CommonMark.
 """
 marker=None;length=0
 for number,line in enumerate(markdown_lines(text),1):
  if marker:
   if re.fullmatch(r' {0,3}'+re.escape(marker)+'{'+str(length)+r',}[ \t]*',line):marker=None;length=0
   continue
  opening=re.fullmatch(r' {0,3}(`{3,}|~{3,})(.*)',line)
  if opening and not (opening[1][0]=='`' and '`' in opening[2]):
   marker=opening[1][0];length=len(opening[1]);continue
  yield number,line

def unfenced(text):
 if not isinstance(text,str):raise ValueError('document must be text')
 visible=dict(prose_lines(text));lines=markdown_lines(text)
 return '\n'.join(visible.get(i,'') for i in range(1,len(lines)+1))+('\n' if text.endswith(('\r','\n')) else '')

def section(text,start,end):
 text=unfenced(text)
 if not isinstance(text,str) or text.count(start+'\n')!=1 or text.count(end+'\n')!=1:raise ValueError('missing/duplicate section boundary: '+start+' -> '+end)
 before,tail=text.split(start+'\n',1)
 if end+'\n' not in tail:raise ValueError('reversed section boundary')
 return tail.split(end+'\n',1)[0]

def tables(text,errors=None):
 def reject(message):
  if errors is None:raise ValueError(message)
  errors.append(message)
 lines=markdown_lines(unfenced(text));out=[];i=0
 while i<len(lines):
  if not lines[i].startswith('|'):i+=1;continue
  block=[]
  while i<len(lines) and lines[i].startswith('|'):block.append(lines[i]);i+=1
  cells=lambda l:[x.strip() for x in l.strip('|').split('|')]
  if len(block)<2:reject('truncated table');continue
  header=cells(block[0]);sep=cells(block[1])
  if len(header)!=len(sep) or not all(re.fullmatch(r'[: -]+',v) for v in sep):reject('unknown table separator')
  rows=[]
  for line in block[2:]:
   row=cells(line)
   if len(row)!=len(header):reject('table row width changed');continue
   rows.append((row,line))
  out.append((header,rows))
 return out

def literal(value):
 m=re.fullmatch(r'`([^`]+)`',value)
 if not m or not c.canonical_id(m[1]):raise ValueError('not an explicit literal API ID')
 return m[1]

def witness(doc,quote,line_number=None,**fields):
 if line_number is None:line_number=next((i for i,line in prose_lines(doc['text']) if line==quote),None)
 return dict(fields,source_url=doc['source_url'],source_sha256=doc['source_sha256'],observed_at=doc['observed_at'],capture_path=doc.get('capture_path'),line=line_number,quote=quote)

def validate_doc(doc,url=None):
 if not isinstance(doc,dict) or not isinstance(doc.get('text'),str):raise ValueError('missing captured document')
 u=urlsplit(doc.get('source_url',''))
 if url and doc['source_url']!=url:raise ValueError('wrong official source')
 if u.scheme!='https' or u.hostname!='platform.claude.com' or u.username or u.password or u.query or u.fragment:raise ValueError('wrong native origin')
 if not url and (not u.path.startswith('/docs/en/models/') or not u.path.endswith('/overview.md') or '..' in u.path):raise ValueError('wrong native detail')
 if not re.fullmatch('[0-9a-f]{64}',doc.get('source_sha256','')) or not doc.get('observed_at'):raise ValueError('missing capture provenance')
 c.parse_time(doc['observed_at'])

def directory(doc):
 part=section(doc['text'],'## All models','## Using the Models API');ts=tables(part)
 header=['Model','Capabilities: Context window','Capabilities: Max output','Base tokens: Input','Base tokens: Output']
 if len(ts)!=1 or ts[0][0]!=header:raise ValueError('unknown all-models table')
 entities=[]
 for cells,line in ts[0][1]:
  name=cells[0].lstrip('[').split(']')[0].split(' (')[0]
  if not name.startswith('Claude '):raise ValueError('unknown directory entity')
  link=re.search(r'\]\((https://platform\.claude\.com/docs/en/models/[^)]+)\)',cells[0])
  entities.append(dict(display_name=name,detail_url=link[1]+'.md' if link else None,quote=line))
 if not entities:raise ValueError('empty directory')
 return entities

class DetailClaimsError(ValueError):
 """Validation failed; independent nonliteral row observations survive rejection."""
 def __init__(self,message,observations):
  super().__init__(message);self.observations=observations

def detail_claims(doc,strict=True):
 observations=[]
 try:return _detail_claims(doc,strict,observations)
 except (ValueError,KeyError,TypeError) as error:
  raise DetailClaimsError(str(error),observations) from error

def _detail_claims(doc,strict,observations):
 text=unfenced(doc['text'])
 part=section(text,'### Model IDs','### Pricing') if strict else text.split('### Model IDs\n',1)[-1].split('### Pricing',1)[0]
 table_errors=[];ts=tables(part,errors=table_errors)
 if len(ts)!=1 or ts[0][0]!=['Platform','Model ID']:table_errors.append('unknown native identity table')
 # Capture every classifiable row before literal/canonical/capability validation.
 # Never infer row roles from an unknown header or outside the bounded section.
 positions={};identity_start=text.find('### Model IDs\n');identity_end=text.find('### Pricing',identity_start)
 first=text[:identity_start].count('\n')+1 if identity_start>=0 else 0
 last=text[:identity_end].count('\n')+1 if identity_end>=0 else len(markdown_lines(text))+1
 for number,line in prose_lines(doc['text']):
  if first<number<last:positions.setdefault(line,[]).append(number)
 known_rows=[];unclassified=[]
 for header,entries in ts:
  if header!=['Platform','Model ID']:continue
  for cells,line in entries:
   label,value=cells
   linked=re.fullmatch(r'\[([^]]+)\]\(https://platform\.claude\.com/[^)]+\)',label)
   if linked:label=linked[1]
   foreign=bool(re.fullmatch(r'(?:Amazon Bedrock(?: \(bedrock-runtime\))?|Claude Models on Google Cloud \((?:Anthropic|Google) managed\)|Microsoft Foundry|Claude Platform on AWS)(?: ID)?',label))
   known=label in ('Claude API','Claude API alias') or foreign
   raw=witness(doc,line,line_number=positions[line].pop(0),model_id=None,kind='unclassified_identity_role',identity_role=label,raw_identifier=value,identity_error='dependent_detail_unproven' if known else 'unknown_role')
   observations.append(raw)
   if label in ('Claude API','Claude API alias'):known_rows.append((label,value,line))
   elif not foreign:unclassified.append(raw)
 native=[];aliases=[]
 for label,value,line in known_rows:
  try:mid=literal(value)
  except ValueError as error:table_errors.append(str(error));continue
  (native if label=='Claude API' else aliases).append((mid,line))
 if len({mid for mid,_ in native})!=1:table_errors.append('ambiguous canonical identity')
 if table_errors:raise ValueError('; '.join(table_errors))
 canonical=native[0][0];declarations=[]
 if strict:
  caps=tables(section(text,'### Capabilities','### Availability'))
  if len(caps)!=1 or caps[0][0]!=['Feature','Value']:raise ValueError('unknown capabilities table')
  cap_start=next(i for i,line in prose_lines(doc['text']) if line=='### Capabilities')
  cap_end=next(i for i,line in prose_lines(doc['text']) if line=='### Availability')
  cap_positions={}
  for number,line in prose_lines(doc['text']):
   if cap_start<number<cap_end:cap_positions.setdefault(line,[]).append(number)
  for cells,line in caps[0][1]:
   if cells[0]!='Input → output':continue
   raw=cells[1].split('→')[-1].strip().lower()
   values=re.split(r'\s*(?:,| and |\+)\s*',raw)
   known=bool(cells[1].count('→')==1 and values and set(values)<={'text','image','audio','video'})
   declarations.append(dict(output_modalities=values if known else None,output_declaration_unknown=not known,output_evidence=witness(doc,line,line_number=cap_positions[line].pop(0),declared_output=raw)))
 if not declarations:declarations=[dict(output_modalities=None,output_declaration_unknown=True)]
 claims=[]
 for kind,entries in [('canonical',native),('alias',aliases)]:
  for mid,line in entries:
   for declaration in declarations:
    fields=dict(model_id=mid,kind=kind,**declaration)
    if kind=='alias':fields['alias_of']=canonical
    claims.append(witness(doc,line,**fields))
 return claims+unclassified

def status_claims(doc,strict=True):
 text=unfenced(doc['text']);claims=[]
 part=section(text,'## Model status','## Deprecation history') if strict else text.split('## Model status\n',1)[-1].split('## Deprecation history',1)[0]
 ts=tables(part)
 if len(ts)!=1 or ts[0][0]!=['API model name','Current state','Deprecated','Tentative retirement date']:raise ValueError('unknown status table')
 for cells,line in ts[0][1]:
  mid=c.canonical_id(cells[0].strip('`'))
  if not mid or cells[1] not in ('Active','Deprecated','Retired','Legacy'):raise ValueError('unknown current lifecycle row')
  claims.append(witness(doc,line,model_id=mid,kind='current_status',lifecycle_status=cells[1].lower(),retirement_date_original=cells[3]))
 if strict:history=section(text,'## Deprecation history','## API parameter deprecations')
 else:history=text.split('## Deprecation history\n',1)[-1].split('## API parameter deprecations',1)[0] if '## Deprecation history\n' in text else ''
 for block in re.split(r'(?m)^### ',history):
  ts=tables(block)
  if not ts:continue
  if len(ts)!=1 or ts[0][0] not in (['Retirement date','Deprecated model','Recommended replacement'],['Retirement date','Model','Recommended replacement']):raise ValueError('unknown historical lifecycle table')
  notes=re.findall(r'<Note>\s*((?:This model was|These models were) retired ([^.]+)\.)\s*</Note>',block)
  if len(notes)>1:raise ValueError('ambiguous retirement Notes')
  retired=re.search(r'(?:This model was|These models were) retired ([^.]+)\.',notes[0][0]) if notes else None
  single=re.search(r'Anthropic notified developers using (Claude [^\n]+?) of its upcoming retirement on the Claude API\.',block)
  entries=ts[0][1]
  for cells,line in entries:
   if retired and cells[0]!=retired[1]:raise ValueError('retirement Note/table date conflict')
   fields=dict(model_id=literal(cells[1]),kind='historical_notice',lifecycle_status='retired' if retired else 'unconfirmed_historical_notice',retirement_date_original=cells[0],lifecycle_note=retired[0] if retired else None,notice_heading=block.splitlines()[0])
   if single and len(entries)==1:fields['display_name']=single[1]
   claims.append(witness(doc,line,**fields))
 return claims

def release_claims(doc):
 """Bind lifecycle predicates to a contiguous coordinated subject noun-list.
 A recommendation/relative/complement clause cannot inherit that predicate.
 """
 claims=[]
 prefix=re.compile(r"^\* We(?:[’']ve retired| announced the deprecation of) ")
 entity=re.compile(r'the (Claude [A-Za-z0-9. -]+?) model \(`([^`]+)`\)')
 conjunction=re.compile(r'(?:,\s+(?:and\s+)?|\s+and\s+)(?=the\s+)')
 for number,line in prose_lines(doc['text']):
  start=prefix.match(line)
  if not start or 'Claude API' not in line:continue
  subject=line.split('. ',1)[0];position=start.end()
  while True:
   match=entity.match(subject,position)
   if not match:break
   name,mid=match.groups()
   if ' and ' in name or name.count('Claude')!=1 or not c.canonical_id(mid):break
   retired=bool(re.search(r'We[’\']ve retired',line) and 'will now return an error' in line)
   claims.append(witness(doc,line,line_number=number,model_id=mid,display_name=name,kind='explicit_entity_parenthetical',lifecycle_status='retired' if retired else None))
   following=conjunction.match(subject,match.end())
   if not following:break
   position=following.end()
 return claims

def aggregate(claims):
 groups={};rows=[];conflicts=[]
 for claim in claims:groups.setdefault(claim['model_id'],[]).append(claim)
 for mid,items in sorted(groups.items()):
  items=sorted(items,key=lambda x:json.dumps(x,sort_keys=True));states={x.get('lifecycle_status') for x in items}-{None,'unconfirmed_historical_notice'}
  aliases={x['alias_of'] for x in items if x.get('alias_of')};bad_alias=len(aliases)>1 or bool(aliases and any(x['kind']=='canonical' for x in items) and aliases!={mid})
  if len(states)>1 or bad_alias:conflicts.append(mid)
  outputs=[set(x['output_modalities']) for x in items if x.get('output_modalities') is not None]
  unresolved=any(x.get('output_declaration_unknown') for x in items)
  output_conflict=len({frozenset(v) for v in outputs})>1
  if output_conflict or unresolved:conflicts.append('output:'+mid)
  certain=set.intersection(*outputs) if outputs and not unresolved else set();union=set.union(*outputs) if outputs else set()
  dates={x['retirement_date_original'] for x in items if x.get('lifecycle_status')=='retired' and x.get('retirement_date_original')}
  status='unknown_conflict' if len(states)>1 else next(iter(states)) if states else 'unconfirmed'
  rows.append(dict(model_id=mid,literal_id=mid,api_id_explicit=True,catalog_observation=False,alias_of=next(iter(aliases)) if len(aliases)==1 and not bad_alias else None,lifecycle_status=status,lifecycle_quote=' | '.join(sorted({x['quote'] for x in items if x.get('lifecycle_status')=='retired'})) or None,retired_at=None,retirement_timezone=None,retirement_date_original=next(iter(dates)) if len(dates)==1 else None,output_modalities=sorted(certain),unknown_output_modalities=['text'] if unresolved or not outputs or ('text' in union and 'text' not in certain) else [],identity_conflict=bad_alias,identity_evidence={'kind':'all_native_literal_claims','claims':items}))
 return rows,conflicts

def observe(root,docs,status,release=None):
 claims=[];errors=[];entities=[]
 try:validate_doc(root,ROOT);entities=directory(root)
 except (ValueError,KeyError,TypeError) as e:errors.append('directory: '+str(e))
 for doc in sorted(docs,key=lambda x:x.get('source_url','')):
  try:validate_doc(doc);claims+=detail_claims(doc)
  except DetailClaimsError as e:
   claims+=e.observations;errors.append('detail: '+str(e))
  except (ValueError,KeyError,TypeError) as e:errors.append('detail: '+str(e))
 try:validate_doc(status,STATUS);claims+=status_claims(status)
 except (ValueError,KeyError,TypeError) as e:errors.append('lifecycle: '+str(e))
 if release:
  try:validate_doc(release,NOTES);claims+=release_claims(release)
  except (ValueError,KeyError,TypeError) as e:errors.append('release: '+str(e))
 else:errors.append('release notes missing in same attempt')
 for entity in entities:
  for claim in claims:
   if claim['source_url']==entity.get('detail_url') and claim['kind'] in ('canonical','alias'):
    claim['display_name']=entity['display_name'];claim['directory_evidence']=witness(root,entity['quote'],detail_url=entity['detail_url'])
 names={}
 for claim in claims:
  if claim.get('display_name'):names.setdefault(claim['display_name'],set()).add(claim.get('alias_of') or claim['model_id'])
 pending=[x['display_name'] for x in entities if len(names.get(x['display_name'],set()))!=1]
 unclassified=[x for x in claims if x['kind']=='unclassified_identity_role']
 claims=[x for x in claims if x['kind']!='unclassified_identity_role']
 errors+=[('unknown platform identity role: ' if x.get('identity_error')=='unknown_role' else 'unproven identity row after detail error: ')+x['identity_role'] for x in unclassified]
 rows,conflicts=aggregate(claims)
 conflicts+=['display:'+name for name,mids in names.items() if len(mids)>1]
 unknown=[r['model_id'] for r in rows if r['lifecycle_status']!='retired' and 'text' in r['unknown_output_modalities']]
 proof=dict(verified=False,method='native canonical/alias/status/history/entity-parenthetical observations; not exhaustive scope proof',structures_verified=not errors and not conflicts,errors=sorted(errors),conflicts=sorted(conflicts),pending_display_entities=sorted(pending),unknown_non_retired_text_ids=unknown,observed_record_count=len(rows),retired_record_count=sum(r['lifecycle_status']=='retired' for r in rows),error='scope completeness remains unproven; unknown capabilities and enumeration not promoted')
 for entity in entities:
  if entity['display_name'] in pending:
   rows.append(dict(model_id=None,api_id_explicit=False,catalog_observation=True,display_name=entity['display_name'],retired_at=None,lifecycle_status='unconfirmed',identity_evidence={'kind':'pending_directory_entity','claims':[witness(root,entity['quote'])]}))
 for claim in unclassified:
  rows.append(dict(model_id=None,api_id_explicit=False,catalog_observation=True,display_name='Unclassified identity role: '+claim['identity_role'],raw_identifier=claim['raw_identifier'],lifecycle_status='unconfirmed',retired_at=None,identity_evidence={'kind':'unclassified_identity_role','claims':[claim]}))
 proof['unclassified_identity_observations']=unclassified
 proof['unclassified_identity_record_count']=len(unclassified)
 proof['pending_record_count']=len(pending)
 return rows,proof
