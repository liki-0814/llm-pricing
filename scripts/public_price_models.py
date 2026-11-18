"""Model-level public price statements, independent of executable offers.

Called only by the source-bound ledger after document validation. Does not fetch,
certify universe/native IDs, infer region/currency, or change estimator records.
"""
import datetime as dt
import hashlib
import json
import math
import re
from html import unescape

ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+')

def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()

def plain(s):
    return ' '.join(unescape(re.sub(r'<[^>]+>', ' ', s)).split())

def pipes(text):
    """Literal pipe tables; no cross-table header or ID inheritance."""
    lines=text.splitlines(keepends=True); pos=0; i=0
    while i<len(lines):
        line=lines[i]
        if line.lstrip().startswith('|') and i+1<len(lines) and re.fullmatch(r'[\s|:\-]+',lines[i+1]):
            start=pos; header=[x.strip() for x in line.strip().strip('|').split('|')]; rows=[]
            pos+=len(line)+len(lines[i+1]);i+=2
            while i<len(lines) and lines[i].lstrip().startswith('|'):
                raw=lines[i];rows.append((raw,[x.strip() for x in raw.strip().strip('|').split('|')]))
                pos+=len(raw);i+=1
            yield dict(start=start,headers=header,header_quote=line,rows=rows,prefix=text[:start])
        else:pos+=len(line);i+=1

def scalar(s):
    s=plain(re.sub(r'<sup>.*?</sup>','',s,flags=re.S))
    m=re.fullmatch(r'\$\s*(\d+(?:\.\d+)?)(?:\s*/\s*(?:MTok|1M tokens|image|sec|second|minute))?',s)
    return float(m[1]) if m else None

def billing_unit(value,default):
    """An explicit scalar-cell suffix overrides a table's default unit, never FX."""
    value=plain(re.sub(r'<sup>.*?</sup>','',value,flags=re.S))
    m=re.fullmatch(r'\$\s*\d+(?:\.\d+)?\s*/\s*(MTok|1M tokens|image|sec|second|minute)',value)
    return {'MTok':'per_1M_tokens','1M tokens':'per_1M_tokens','image':'per_image','sec':'per_second','second':'per_second','minute':'per_minute'}[m[1]] if m else default

def component(header):
    h=header.lower()
    if 'cache' in h or 'caching' in h:
        if 'write' in h:return 'cache_write_5m' if '5m' in h else 'cache_write_1h' if '1h' in h else 'cache_write_30m' if '30m' in h else 'cache_write_12h' if '12h' in h else None
        return 'cached_input'
    if 'input' in h:return 'input'
    if 'output' in h:return 'output'
    return None

def emit(out, doc, mid, amount, currency, unit, charge, billing, quote, context, conditions, identity=None, region=None):
    """One shared constructor; source context and quote must be actual substrings."""
    meta,text=doc['meta'],doc['text']
    if not ID.fullmatch(mid) or isinstance(amount,bool) or amount is None or not math.isfinite(amount) or amount<0 or not unit or not charge:return
    if quote not in text or any(q not in text for q in context):raise ValueError('model price quote/context not literal')
    if identity is not None and identity['quote'] not in identity['document']['text']:raise ValueError('nonliteral identity bridge')
    selectors=dict(model_id='explicit_catalog_ID_bridge' if identity else 'literal_official_price_table_ID',amount='explicit_scalar',currency='explicit_'+currency+'_declaration' if currency else 'not_stated_dollar_symbol_only',unit='explicit_source_unit',component='explicit_source_header',channel='source_bound_pay_as_you_go',region='explicit_first_party_global_default' if region=='global_default' else 'explicit_source_region' if region else 'not_stated',billing_modality='not_stated' if billing in ('not_stated','token_modality_not_separately_priced') else 'explicit_price_header',conditions='source_qualifiers_preserved_NOT_executable',effective_time='not_inferred')
    if conditions.get('date_condition'):selectors['effective_time']='date_only_timezone_not_stated'
    record=dict(vendor=meta['vendor'],channel=meta['channel'],model_id=mid,amount=amount,currency=currency,currency_symbol='元' if currency=='CNY' else '$',unit=unit,component=charge,billing_modality=billing,conditions=conditions,
        region=region,region_scope='explicit_first_party_global_default_NOT_user_region' if region=='global_default' else 'explicit_source_region' if region else 'not_stated_NOT_global',selector_completeness=selectors,selector_complete=False,
        price_verified=False,quote_verified=True,record_status='normalized_source_statement_with_incomplete_selectors' if currency else 'model_price_candidate_currency_not_stated',
        eligible_for_estimation=False,scope_complete=False,history_complete=False,availability='not_assessed',account_entitlement='not_assessed',
        source_url=meta['source_url'],source_sha256=meta['source_sha256'],observed_at=meta['observed_at'],quote=quote,quote_sha256=sha(quote),context_quotes=list(dict.fromkeys(context)))
    if identity:
        m=identity['document']['meta'];record['identity_evidence']=dict(source_url=m['source_url'],source_sha256=m['source_sha256'],quote=identity['quote'],quote_sha256=sha(identity['quote']),role='price_label_to_literal_ID_NOT_universe_certificate')
    record['price_record_id']=sha(json.dumps(record,sort_keys=True,ensure_ascii=False));out.append(record)

def anthropic(out,doc,docs):
    text=doc['text'];catalog=next((d for d in docs if d['meta']['vendor']=='Anthropic' and '/models/overview.md' in d['meta']['source_url']),None)
    if not catalog:return
    bridges={}
    for table in pipes(catalog['text']):
        for raw,cells in table['rows']:
            if cells and cells[0]=='Claude API ID':
                for label,cell in zip(table['headers'][1:],cells[1:]):
                    mid=re.fullmatch(r'`([^`]+)`',cell)
                    if mid:bridges[label]=(mid[1],dict(quote=table['header_quote']+next(l for l in catalog['text'][table['start']:].splitlines(keepends=True)[1:] if re.fullmatch(r'[\s|:\-]+',l))+''.join(r for r,_ in table['rows'][:table['rows'].index((raw,cells))+1]),document=catalog))
    usd=re.search(r'All prices are in USD\.',text)
    global_default=re.search(r'The Claude API \(first-party\) is global by default',text)
    for table in pipes(text):
        if table['headers']!=['Model','Base input tokens','5m cache writes','1h cache writes','Cache hits and refreshes','Output tokens']:continue
        for raw,cells in table['rows']:
            for label,(mid,identity) in bridges.items():
                if not (cells[0]==label or cells[0].startswith(label+' (')):continue
                for header,value in zip(table['headers'][1:],cells[1:]):
                    if 'MTok' not in value:continue
                    emit(out,doc,mid,scalar(value),'USD' if usd else None,'per_1M_tokens',component(header),'token_modality_not_separately_priced',raw,[table['header_quote']]+([usd[0]] if usd else [])+([global_default[0]] if global_default else []),dict(service_tier='base_model_pricing',model_qualifier=cells[0],price_header=header,footnotes_preserved=value),identity,region='global_default' if global_default else None)

def google(out,doc,docs):
    text=doc['text']
    for match in re.finditer(r'{% table %}(.*?){% /table %}',text,re.S):
        prefix=text[:match.start()];sections=list(re.finditer(r'^## .*$',prefix,re.M))
        if not sections:continue
        section=prefix[sections[-1].start():];ids=re.findall(r'\[`([^`]+)`\]\(/docs/models/[^)]+\)',section)
        if len(set(ids))!=1:continue
        mid=ids[0];tabs=re.findall(r'{% tab title="([^"]+)" %}',section)
        if not tabs:continue
        blocks=re.split(r'^\s*---\s*$',match[1],flags=re.M)
        headers=re.findall(r'^\s*\*\s+(.*)$',blocks[0],re.M)
        if len(headers)!=3 or 'USD' not in headers[2] or '1M tokens' not in headers[2]:continue
        identity=next(re.finditer(r'\[`[^`]+`\]\(/docs/models/[^)]+\)',section))[0]
        for block in blocks[1:]:
            cells=re.split(r'^\s*\*\s+',block,flags=re.M)[1:]
            if len(cells)!=3:continue
            label,free,paid=[x.strip() for x in cells];charge=component(label)
            modes=[x for x in ('text','image','audio','video') if x in label.lower()];billing=modes[0] if len(modes)==1 else 'token_modality_not_separately_priced'
            if charge is None or 'storage' in label.lower():continue
            amounts=list(re.finditer(r'\$(\d+(?:\.\d+)?)',paid))
            if len(amounts)==1 and scalar(paid) is not None:
                emit(out,doc,mid,float(amounts[0][1]),'USD',billing_unit(paid,'per_1M_tokens'),charge,billing,block,[blocks[0],identity],dict(service_tier=tabs[-1],price_header=label,paid_tier=headers[2],qualifier=paid))
            elif amounts:
                # Only the complete, explicit through/starting date-pair grammar.
                schedule=re.fullmatch(r'\$(\d+(?:\.\d+)?)\s+through\s+([A-Za-z]+ \d{1,2}, \d{4})\.\s*\$(\d+(?:\.\d+)?)\s+starting\s+([A-Za-z]+ \d{1,2}, \d{4})\.',paid)
                if not schedule:continue
                for amount,op,date in ((schedule[1],'through_inclusive',schedule[2]),(schedule[3],'starting_inclusive',schedule[4])):
                    emit(out,doc,mid,float(amount),'USD','per_1M_tokens',charge,billing,block,[blocks[0],identity],dict(service_tier=tabs[-1],price_header=label,paid_tier=headers[2],date_condition=dict(operator=op,date=dt.datetime.strptime(date,'%B %d, %Y').date().isoformat(),timezone=None,precision='date_only'),qualifier=paid))

def markdown_prices(out,doc):
    text=doc['text'];vendor=doc['meta']['vendor'];usd=re.search(r'All prices are in USD\.',text)
    for table in pipes(text):
        headers=table['headers']
        if not headers or headers[0]!='Model':continue
        prefix=table['prefix'];heading=re.findall(r'^#{1,4} .+$',prefix,re.M);heading=heading[-1] if heading else ''
        boundaries=list(re.finditer(r'^(?:Flagship models|Multimodal models|Images|Audio|GPT-Live|Realtime & Audio|Specialized models|Fine-tuning)\s*$',prefix,re.M))
        local=prefix[boundaries[-1].start():] if boundaries else prefix
        tiers=re.findall(r'^(Standard|Batch|Flex|Priority)\s*$',local,re.M);tier=tiers[-1] if tiers else None
        # Source section states token units; an explicit per-minute cell overrides.
        units=re.findall(r'Prices per 1M tokens[^\n]*\.',prefix)
        default_unit='per_1M_tokens' if units or (vendor=='xAI' and heading=='### Text API Pricing') else None
        for raw,cells in table['rows']:
            if len(cells)!=len(headers):continue
            m=re.match(r'([A-Za-z0-9][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+)(?=\s|$)',cells[0])
            if not m:continue
            mid=m[1];billing=cells[headers.index('Modality')].lower() if 'Modality' in headers else 'token_modality_not_separately_priced'
            for h,value in zip(headers[1:],cells[1:]):
                charge=component(h);unit=default_unit
                if vendor=='xAI' and heading=='### Image & Video Pricing' and h=='Cost':
                    unit='per_image' if re.fullmatch(r'\$[\d.]+ / image',value) else 'per_second' if re.fullmatch(r'\$[\d.]+ / sec',value) else None
                    billing='image' if unit=='per_image' else 'video';charge='output'
                if h=='Price per minute':unit='per_minute';charge='session';billing='audio'
                if '/ 1M tokens' in h:unit='per_1M_tokens'
                unit=billing_unit(value,unit)
                if not unit or charge is None:continue
                context=[table['header_quote']]+([usd[0]] if usd else [])+([units[-1]] if units else [])
                note=re.search(r'^\*Prices shown per million tokens\..+\*$',text,re.M) if vendor=='xAI' and heading=='### Text API Pricing' else None
                if note:context.append(note[0])
                # Preserve source model/header qualifiers; no guessed context cutoff.
                emit(out,doc,mid,scalar(value),'USD' if usd else None,unit,charge,billing,raw,context,dict(service_tier=tier,section=heading,model_qualifier=cells[0],price_header=h,context_limit=cells[headers.index('Context')] if 'Context' in headers else None,source_conditions='source model/header literals; full applicability not inferred'))

def minimax(out,doc,table_reader,expand_rows):
    text=doc['text'];reader=table_reader(text);reader.feed(text);usd=re.search(r'All prices are in USD\.',text)
    for table in reader.tables:
        rows=expand_rows(table)
        if not rows:continue
        headers=[c['text'] for c in rows[0][1]]
        if not headers or headers[0] not in ('Model','Model / API'):continue
        section=table['headings'].get(2,{}).get('text')
        if section not in ('LLM','Video','Image'):continue
        # The table's actual enclosing tab role is tracked by the HTML reader.
        tier=table.get('tab_label')
        for row,cells in rows[1:]:
            if len(cells)!=len(headers):continue
            model=cells[0]['text'];tokens=model.split()
            if not tokens or not ID.fullmatch(tokens[0]):continue
            # Multiple IDs only if the entire cell consists of literal IDs;
            # descriptive hyphenated words never become extra model identifiers.
            ids=list(dict.fromkeys(tokens)) if all(ID.fullmatch(t) for t in tokens) else [tokens[0]]
            for h,cell in zip(headers[1:],cells[1:]):
                charge=component(h);billing='token_modality_not_separately_priced';unit=None
                bundled=re.fullmatch(r'(\$[0-9]+(?:\.[0-9]+)?) per ([0-9]+P), ([0-9]+)s video',cell['text']) if h=='Price' else None
                if bundled:unit='per_video';charge='output';billing='video'
                if re.search(r'(?:/\s*M tokens|per M tokens)',h):unit='per_1M_tokens'
                if 'Image' in h:billing='image'
                if 'Video' in h:billing='video'
                if 'per second' in h:unit='per_second'
                if 'per image' in h:unit='per_image'
                if h=='Price' and re.fullmatch(r'\$[\d.]+ per image',cell['text']):unit='per_image';charge='output';billing='image'
                if not unit or charge is None:continue
                dims={hh:cc['text'] for hh,cc in zip(headers,cells) if hh not in ('Model','Model / API') and component(hh) is None and hh!='Price'}
                if bundled:dims.update(output_resolution=bundled[2],duration_seconds=int(bundled[3]))
                values=[]
                if '<del>' in cell.get('raw',''):
                    # Only permanent replacements, never undated timed promotions.
                    if 'Permanent 50% off' not in model:continue
                    old=re.search(r'<del>(.*?)</del>',cell['raw'],re.S)
                    remaining=re.sub(r'<del>.*?</del>','',cell['raw'],flags=re.S)
                    values=[(scalar(old[1]),'deleted_list_price_NOT_current_charge'),(scalar(remaining),'explicit_permanent_replacement')]
                else:
                    val=bundled[1] if bundled else cell['text'].replace(' per image','');values=[(scalar(val),'quoted_rate')]
                for mid in ids:
                    for amount,kind in values:
                        origin=cells[0]['origin_quote'];context=[rows[0][0]['quote']]+([table['tab_quote']] if table.get('tab_quote') else [])+([origin] if origin!=row['quote'] else [])+([usd[0]] if usd else [])
                        emit(out,doc,mid,amount,'USD' if usd else None,unit,charge,billing,row['quote'],context,dict(service_tier=tier,section=section,model_qualifier=model,price_header=h,dimensions=dims,rate_kind=kind,tab_context=table.get('tab_quote')))

def normalize(documents,table_reader,expand_rows,qwen_facts,qwen_candidates=()):
    out=[]
    for doc in documents:
        m=doc['meta'];u=m['source_url'];v=m['vendor']
        if u.endswith(('/models/overview.md','/docs/models','/faq/models.md','/models/all.md')):continue
        if v=='Anthropic':anthropic(out,doc,documents)
        elif v=='Google Gemini':google(out,doc,documents)
        elif v=='MiniMax':minimax(out,doc,table_reader,expand_rows)
        elif v in ('OpenAI','xAI'):markdown_prices(out,doc)
    for candidate in qwen_candidates:
        doc=next((d for d in documents if d['meta']['vendor']=='阿里云 Qwen' and d['meta']['source_url']==candidate['source_url']),None)
        if doc is None:continue
        for r in candidate.get('unbound_billing_components',[]):
            emit(out,doc,r['model_id'],r['amount'],'CNY',r['unit'],r['component'],r['billing_modality'],r['quote'],r['context'],dict(price_header=r['price_header'],dimensions=r['dimensions'],model_qualifier=r['model_qualifier'],rate_kind=r['rate_kind'],unresolved='per_ID_output_modality_NOT_certified'),region=r['region'])
    # Existing strict CNY facts retain their exact reviewed semantics and IDs.
    for f in qwen_facts:
        if not f.get('model_id'):continue
        r=dict(f);r.update(price_record_id=sha(f['fact_id']),quote_verified=True,record_status='existing_strict_source_fact_NOT_executable_quote',billing_modality=f['modality'],selector_complete=True,
            selector_completeness=dict(model_id='literal_official_price_table_ID',region='explicit_source_region',currency='explicit_CNY',unit='explicit_source_header',component='explicit_source_header',conditions='existing_source_tier_literal',channel='source_bound_pay_as_you_go'),conditions=dict(source_tier=f['tier'],rate_kind=f.get('rate_kind')))
        out.append(r)
    return list({r['price_record_id']:r for r in out}.values())
