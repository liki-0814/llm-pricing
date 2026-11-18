"""Finite request-model claims, bound to native servers, routes and raw captures.

This is not account entitlement, alias inference, or proof that a pricing label is
an API ID. Examples/responses are never used as request identity evidence.
"""
import copy
import catalog_diff as c

ANNOTATIONS={'title','description','example','examples','default','deprecated','discriminator'}

def request_models(spec, route, server):
    """All declared request media types/branches must close; no fallback on failure."""
    if not isinstance(spec,dict) or not isinstance(spec.get('paths'),dict):raise ValueError('invalid request document paths')
    path=spec['paths'][route]
    if not isinstance(path,dict) or not isinstance(path.get('post'),dict):raise ValueError('invalid request operation')
    op=path['post']
    for level in (op,path,spec):
        if 'servers' in level:
            servers=level['servers']
            if not isinstance(servers,list) or not servers or any(not isinstance(x,dict) or x.get('url')!=server for x in servers):
                raise ValueError('unapproved effective native request server')
            break
    else:raise ValueError('missing effective native request server')
    def resolve(node,seen=()):
        if not isinstance(node,dict) or not node:raise ValueError('empty/non-object schema')
        if '$ref' not in node:return node,seen
        ref=node['$ref']
        if set(node)-{'$ref'}-ANNOTATIONS or not isinstance(ref,str) or not ref.startswith('#/components/schemas/') or ref in seen:
            raise ValueError('external/cyclic/semantic-sibling request ref')
        target=spec
        for part in ref[2:].split('/'):target=target[part.replace('~1','/').replace('~0','~')]
        return resolve(target,seen+(ref,))
    def models(node,seen=()):
        node,seen=resolve(node,seen)
        if any(k in node for k in ('allOf','not','if','then','else')):raise ValueError('unsupported request composition')
        unions=[k for k in ('oneOf','anyOf') if k in node]
        if unions:
            if len(unions)!=1 or set(node)-set(unions)-ANNOTATIONS:raise ValueError('mixed request union')
            branches=node[unions[0]]
            if not isinstance(branches,list) or not branches:raise ValueError('empty request union')
            return set().union(*(models(x,seen) for x in branches))
        if node.get('type')!='object' or set(node)-ANNOTATIONS-{'type','properties','required','additionalProperties'}:
            raise ValueError('unreviewed/non-object request schema')
        required=node.get('required')
        if not isinstance(required,list) or 'model' not in required or any(not isinstance(x,str) for x in required):raise ValueError('model selector is not explicitly mandatory')
        props=node.get('properties')
        if not isinstance(props,dict) or 'model' not in props:raise ValueError('request has no model constraint')
        field,_=resolve(props['model'],seen)
        if set(field)-ANNOTATIONS-{'type','enum'} or field.get('type')!='string':raise ValueError('unreviewed/non-string model constraint')
        values=field.get('enum')
        if not isinstance(values,list) or not values or any(not isinstance(x,str) or c.canonical_id(x)!=x for x in values):
            raise ValueError('model enum is not a finite literal string set')
        return set(values)
    content=op.get('requestBody',{}).get('content')
    if not isinstance(content,dict) or not content:raise ValueError('no request media types')
    claims=[]
    for media,item in content.items():
        if media not in ('application/json','multipart/form-data'):raise ValueError('unreviewed request media type')
        for mid in sorted(models(item['schema'])):
            claims.append(dict(model_id=mid,route=route,media_type=media,server=server,identity_role='request_model_enum'))
    return claims


def scoped_snapshot(root, modality, claims, pending=(), *, verified=False, proof=None):
    """Shared scope projection preserves row-local facts; never cross-multiplies IDs."""
    out={k:copy.deepcopy(v) for k,v in root.items() if k not in ('records','coverage_evidence','errors','_extraction_text')}
    rows={}
    for claim in claims:
        mid=claim['model_id']
        row=rows.setdefault(mid,dict(model_id=mid,api_id_explicit=True,catalog_observation=False,
            output_modalities=[modality],identity_evidence=[],lifecycle_status='unconfirmed',retired_at=None,
            alias_status='unknown_no_explicit_alias_mapping',price_status='unknown_not_a_pricing_source'))
        row['identity_evidence'].append(copy.deepcopy(claim))
    out.update(row_scope_exclusive=True,records=list(rows.values())+list(pending),complete=bool(verified and rows and not pending),
        extraction_status='ok' if verified and rows and not pending else 'partial',errors=[] if verified and rows and not pending else ['scope_contract_unverified'])
    out['coverage_evidence']=dict(source_url=root['source_url'],modalities=[modality],enumeration_verified=out['complete'],
        pagination_complete=out['complete'],native_identity_verified=out['complete'],expected_record_count=len(out['records']),proof=proof or {})
    return out
