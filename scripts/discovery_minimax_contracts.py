"""MiniMax documented generation universe: full Model List plus indexed request enums.

No display-name canonicalization, inherited input modality, subscription borrowing,
price inference, or missing->retired conversion. Unknowns remain explicit.
"""
import json,re
from discovery_markdown import formal_text
from urllib.parse import urljoin
from discovery_request_contracts import request_models,scoped_snapshot
ROOT='https://platform.minimax.io/docs/faq/models.md'
INDEX='https://platform.minimax.io/docs/llms.txt'
BASE='https://platform.minimax.io/docs/api-reference/'
SPECS={
 'image/generation/api/text-to-image.json':('image','/v1/image_generation'),
 'image/generation/api/image-to-image.json':('image','/v1/image_generation'),
 'image/generation/api/h3-image-generations.json':('image','/v1/images/generations'),
 'image/generation/api/h3-image-edits.json':('image','/v1/images/edits'),
 'video/generation/api/text-to-video.json':('video','/v1/video_generation'),
 'video/generation/api/image-to-video.json':('video','/v1/video_generation'),
 'video/generation/api/start-end-to-video.json':('video','/v1/video_generation'),
 'video/generation/api/subject-reference-to-video.json':('video','/v1/video_generation'),
 'video/generation/api/v2-video-generation.json':('video','/v2/video_generation'),
 'text/api/openapi.json':('text','/v1/text/chatcompletion_v2')}
# Explicitly non-generating supporting specs; new index entries fail certification.
SUPPORT={'image/generation/api/openapi.json','image/generation/api/h3-image-context-ir.json','video/generation/api/openapi.json'}

def indexed_specs(text):
    refs={urljoin(INDEX,m) for m in re.findall(r'\]\(([^)]+\.json)\)',text)}
    generation={u for u in refs if u.startswith(BASE) and any('/'+f+'/generation/api/' in u for f in ('image','video'))}
    expected={BASE+p for p in SPECS if p.startswith(('image/','video/'))}
    if generation != expected|{BASE+p for p in SUPPORT}:raise ValueError('indexed generation schema set changed or incomplete')
    if BASE+'text/api/openapi.json' not in refs:raise ValueError('text request schema absent from official index')
    return sorted(BASE+p for p in SPECS)

def directory(text):
    text=formal_text(text)
    if '# Model List' not in text or 'those that have been retired' not in text or '## Available Models' not in text or '## Retired Models' not in text:
        raise ValueError('full available/retired directory boundary missing')
    if re.search(r'(?i)\b(next page|load more|has_more|next_cursor)\b',text):raise ValueError('unresolved directory continuation')
    section=None;retired=False;rows=[]
    kinds={'LLM':'text','Video Models':'video','Image Models':'image'}
    for line_no,line in enumerate(text.splitlines(),1):
        if line=='## Retired Models':retired=True;section=None
        if line.startswith('### '):section=kinds.get(line[4:])
        if not line.startswith('| '):continue
        cells=[x.strip() for x in line.strip('|').split('|')]
        match=re.fullmatch(r'\[([^]]+)\]\([^)]+\)',cells[0]);name=match[1] if match else cells[0].strip('`')
        if retired:
            if len(cells)<3 or cells[-1]!='Retired':continue
            modality={'LLM':'text','Video':'video','Image':'image'}.get(cells[1])
        else:modality=section
        if modality and name not in ('Model','Model Name') and not re.fullmatch(r'[: -]+',name):
            rows.append(dict(display_name=name,modality=modality,line=line_no,lifecycle_status='retired' if retired else 'listed',quote=line))
    if not rows or not any(r['lifecycle_status']=='retired' for r in rows):raise ValueError('directory sections not actually enumerated')
    return rows

def prove(root,docs):
    entities=directory(docs[ROOT]['text'])
    for entity in entities:entity.update({k:v for k,v in docs[ROOT].items() if k!='text'})
    index=docs[INDEX];urls=indexed_specs(index['text'])
    claims={m:[] for m in ('text','image','video')};failures={m:[] for m in claims}
    for url in urls:
        modality,route=SPECS[url[len(BASE):]]
        doc=docs.get(url,{})
        try:
            spec=json.loads(doc['text'])
            if not isinstance(spec,dict) or not isinstance(spec.get('paths'),dict) or any(not isinstance(item,dict) for item in spec['paths'].values()):raise ValueError('invalid native request document paths')
            routes=[route]
            non_generation=set()
            if url.endswith('/v2-video-generation.json'):
                routes.append('/v2/video_regeneration')
                non_generation.add('/v2/h3_context_ir') # structured prompt interpretation, not video output
            actual_posts={p for p,item in spec.get('paths',{}).items() if 'post' in item}
            if actual_posts!=set(routes)|non_generation:raise ValueError('unreviewed or missing POST request route')
            entries=[]
            for requested_route in routes:entries.extend(request_models(spec,requested_route,'https://api.minimax.io'))
            for entry in entries:entry.update(source_url=url,source_sha256=doc['source_sha256'],capture_path=doc['capture_path'],observed_at=doc['observed_at'])
            claims[modality].extend(entries)
        except (ValueError,KeyError,TypeError) as error:failures[modality].append(dict({k:v for k,v in doc.items() if k!='text'},source_url=url,error=str(error),eligibility='unknown_not_certified'))
    result=[]
    for modality,items in claims.items():
        ids={r['model_id'] for r in items};scope_entities=[r for r in entities if r['modality']==modality]
        pending=[dict(r,model_id=None,api_id_explicit=False,catalog_observation=True,lifecycle_quote=r['quote'] if r['lifecycle_status']=='retired' else None,retired_at=None,scope_status='pending_official_invocation_id') for r in scope_entities if r['display_name'] not in ids]
        # Directory and schema may disagree on availability. Retain all literal
        # IDs, but don't certify the universe until that official disagreement is
        # resolved. A finite endpoint enum alone is not a full lifecycle catalog.
        outside=sorted(ids-{r['display_name'] for r in scope_entities})
        proof=dict(method='full_directory_plus_indexed_native_request_enums',directory_entities=scope_entities,
            required_schema_urls=[u for u in urls if SPECS[u[len(BASE):]][0]==modality],
            index_source={k:v for k,v in index.items() if k!='text'},failures=failures[modality],
            directory_entities_without_literal_bridge=[r['display_name'] for r in pending],
            request_ids_absent_from_full_model_list=outside,
            termination='full saved Markdown documents; finite official index; no next cursor; not API task-list pagination',
            aliases='unknown: no explicit alias mapping in these sources',pricing='unknown: not pricing evidence',
            verified=not pending and not failures[modality] and not outside)
        out=scoped_snapshot(root,modality,items,pending,verified=proof['verified'],proof=proof)
        for row in out['records']:
            same=[r for r in scope_entities if r['display_name']==row.get('model_id')]
            if same:row['directory_evidence']=same
            retired=[r for r in same if r['lifecycle_status']=='retired']
            if retired:row.update(lifecycle_status='retired',lifecycle_quote='\n'.join(dict.fromkeys(r['quote'] for r in retired)),line=retired[0]['line'],lifecycle_evidence=retired)
        out['original_directory_observations']=root.get('records',[])
        result.append(out)
    return result
