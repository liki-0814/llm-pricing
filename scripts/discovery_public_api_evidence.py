"""Bounded first-party API identity/billing evidence, not price-to-universe promotion.

No network, currencies, amounts, provider authorship, output or entitlement inference.
The independent raw source must be verified before any exact existing ID is joined.
"""
import copy,re
from pathlib import Path
from discovery_claim_contract import canonical_id,claim,project
from discovery_markdown import formal_text
from discovery_universe_contracts import scope_certificate
from price_table_structure import Tables,expanded,pipes
from public_price_context import readable
from public_price_facts import verified_document

OPENAI='https://developers.openai.com/api/docs/pricing'
QWEN='https://help.aliyun.com/zh/model-studio/model-pricing'
ANTHROPIC='https://platform.claude.com/docs/en/models/overview.md'
GOOGLE='https://aistudio.google.com/docs/pricing'
SOURCES={OPENAI:'OpenAI',QWEN:'阿里云 Qwen',ANTHROPIC:'Anthropic',GOOGLE:'Google Gemini'}
CATALOGS={'Anthropic':{ANTHROPIC},'Google Gemini':{'https://aistudio.google.com/docs/models'},'OpenAI':{'https://developers.openai.com/api/docs/models/all.md'},'阿里云 Qwen':{'https://www.alibabacloud.com/help/en/model-studio/models'}}
INLINE_ABSENCE='inline ID has no bound native endpoint/channel evidence'
ABSENCE_FIELDS={'source_url','source_sha256','capture_path','observed_at','vendor','channel','catalog_source_url','model_id','kind','status','reason'}
BILLING='模型调用默认 按量计费 ，涵盖各类模型的计费规则与价格。'


def model_column_id(cell):
    value=readable(cell).strip()
    match=re.fullmatch(r'(?:`([A-Za-z0-9][A-Za-z0-9._/-]*)`|([A-Za-z0-9][A-Za-z0-9._/-]*))(?: \((?:short|long) context\))?',value)
    return canonical_id(match[1] or match[2]) if match else None


def model_column_observations(meta,text):
    """Pure exact named-Model-column reader; no first-column/category guessing."""
    url=meta.get('source_url')
    if SOURCES.get(url)!=meta.get('vendor') or meta.get('channel')!='pay_as_you_go':return []
    out=[]
    if url==OPENAI:
        for table in pipes(formal_text(text)):
            headers=[readable(x).strip() for x in table['headers']]
            if headers.count('Model')!=1:continue
            i=headers.index('Model')
            for row,cells in table['rows']:
                if len(cells)!=len(headers):continue
                mid=model_column_id(cells[i])
                if mid and row in text and table['header_quote'] in text:
                    out.append(dict(model_id=mid,quote=row,header_quote=table['header_quote'],model_cell=cells[i],model_column=i,billing_scope='official OpenAI API pricing; not access approval'))
    elif url==QWEN and BILLING in text:
        reader=Tables(text);reader.feed(text)
        for table in reader.tables:
            rows=expanded(table)
            if not rows:continue
            headers=[c['text'].replace(' ','') for c in rows[0][1]]
            if headers.count('模型ID（ModelID）')!=1:continue
            i=headers.index('模型ID（ModelID）')
            for row,cells in rows[1:]:
                if len(cells)!=len(headers):continue
                mid=model_column_id(cells[i].get('raw',cells[i]['text']))
                if mid:
                    out.append(dict(model_id=mid,quote=row['quote'],header_quote=rows[0][0]['quote'],model_cell=cells[i].get('raw',cells[i]['text']),model_column=i,table_heading_evidence=[h['quote'] for h in table.get('headings',{}).values()],billing_quote=BILLING,billing_scope='documented regional API billing only; not international entitlement, native authorship or availability'))
    elif url==ANTHROPIC:
        for table in pipes(formal_text(text)):
            if not table['headers'] or table['headers'][0]!='Feature':continue
            pricing=[row for row,cells in table['rows'] if cells and re.fullmatch(r'\[Pricing\]\(https://platform\.claude\.com/docs/en/about-claude/pricing\)',cells[0])]
            if len(pricing)!=1:continue
            for row,cells in table['rows']:
                if len(cells)!=len(table['headers']) or cells[0]!='Claude API ID':continue
                for i,cell in enumerate(cells[1:],1):
                    mid=model_column_id(cell)
                    if mid:out.append(dict(model_id=mid,quote=row,header_quote=table['header_quote'],model_cell=cell,model_column=i,billing_quote=pricing[0],billing_scope='documented first-party Claude API pricing; not current availability or access approval'))
    elif url==GOOGLE:
        billing='pay-as-you-go pricing for your production-ready applications.'
        formal=formal_text(text)
        if billing not in formal or '# Gemini Developer API pricing' not in formal:return out
        for line in formal.splitlines():
            match=re.fullmatch(r'\*?\[`([A-Za-z0-9][A-Za-z0-9._/-]*)`\]\(/docs/models/[^)]+\)\*?',line.strip())
            if match:out.append(dict(model_id=match[1],quote=line,header_quote='# Gemini Developer API pricing',model_cell=match[1],model_column=None,billing_quote=billing,billing_scope='documented Gemini Developer API PAYG service; not user entitlement or lifecycle'))
    return out


def read_api_evidence(ledger,source_root):
    root=Path(source_root).resolve();index={}
    for meta in ledger.get('sources',[]):
        if meta.get('source_url') not in SOURCES:continue
        path=(root/meta['body_path']).resolve()
        if not path.is_relative_to(root):raise ValueError('API source body escapes capture boundary')
        text=verified_document(meta,path.read_bytes())
        for item in model_column_observations(meta,text):
            key=(meta['vendor'],meta['channel'],item['model_id'])
            evidence=dict(item,source_url=meta['source_url'],source_sha256=meta['source_sha256'],observed_at=meta['observed_at'],capture_path=str(path),vendor=meta['vendor'],channel=meta['channel'])
            index.setdefault(key,[]).append(evidence)
    return index


def attach_api_evidence(inventories,ledger,source_root,manifest=None):
    """Consume only existing exact IDs. Preserve every non-placeholder unknown."""
    index=read_api_evidence(ledger,source_root);changed=0
    for snap in inventories:
        if snap.get('channel')!='pay_as_you_go' or snap.get('role')!='catalog' or snap.get('source_url') not in CATALOGS.get(snap.get('vendor'),set()):continue
        edits=0
        for row in snap.get('records',[]):
            mid=row.get('model_id') or row.get('observed_model_id')
            if canonical_id(mid)!=mid or mid is None:continue
            found=index.get((snap['vendor'],snap['channel'],mid),[])
            if not found:continue
            existing=list(row.get('native_claims',[]))
            if snap['vendor'] in ('Anthropic','Google Gemini'):
                if row.get('api_id_explicit') is not True or manifest is None:continue
                from discovery_scope_projection import qualified_producer_claims
                existing=qualified_producer_claims(snap,row,manifest)
                if not any(c.get('kind')=='identity' for c in existing):continue
            inline=any(c.get('kind')=='identity' and c.get('role')=='inline_directory_literal' and c.get('model_id')==mid and c.get('source_url')==snap['source_url'] and c.get('catalog_source_url')==snap['source_url'] for c in existing)
            if snap['vendor']=='OpenAI' and not inline:continue
            if any(c.get('evidence_role')=='exact_official_API_ID_billing_witness' for c in existing):continue
            # This one reason is a previous absence placeholder, not an observed
            # conflict. All other unknown claims remain sticky under project().
            superseded=[c for c in existing if inline and c.get('kind')=='native_channel' and c.get('status')=='unknown' and c.get('reason')==INLINE_ABSENCE and c.get('model_id')==mid and c.get('catalog_source_url')==snap['source_url'] and c.get('source_url')==snap['source_url'] and set(c)==ABSENCE_FIELDS]
            claims=[c for c in existing if c not in superseded]
            for e in found:
                doc=dict(e,catalog_source_url=snap['source_url'])
                fields={k:e[k] for k in ('quote','header_quote','model_cell','model_column','billing_scope')}
                if e.get('billing_quote'):fields['billing_quote']=e['billing_quote']
                if e.get('table_heading_evidence'):fields['table_heading_evidence']=e['table_heading_evidence']
                if not any(c.get('kind')=='identity' for c in claims):claims.append(claim(doc,mid,'identity',role='explicit_API_Model_column',**fields))
                claims.append(claim(doc,mid,'native_channel',status='verified',reason='exact literal API ID in official first-party billing evidence; not user access or model authorship',evidence_role='exact_official_API_ID_billing_witness',**fields))
            projected=project(claims)
            row.update(model_id=mid,api_id_explicit=True,native_claims=claims,channel_applicability=projected['channel_applicability'],channel_unknown_reasons=projected['channel_unknown_reasons'])
            row['bounded_API_identity_evidence']=found
            if superseded:row.setdefault('superseded_absence_claims',[]).extend(superseded)
            # Do not change native_vendor_status, provider/author, outputs,
            # request-parameter proof, lifecycle, alias, prices or currencies.
            edits+=1
        if not edits:continue
        changed+=edits
        for i,cert in enumerate(snap.get('scope_certificates',[])):
            facts=cert['obligations']
            snap['scope_certificates'][i]=scope_certificate(snap['vendor'],snap['channel'],cert['modality'],snap['records'],**{k:copy.deepcopy(facts[k]) for k in ('population','pagination','alias_enumeration','lifecycle')},source_evidence=cert.get('source_evidence',[]))
        snap['bounded_API_evidence_consumption']=dict(method='verified raw official API ID/header exact-ID join',matched_existing_records=edits,scope_complete=False,native_authorship='not_inferred',account_entitlement='not_assessed')
    return changed
