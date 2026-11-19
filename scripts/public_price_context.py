"""Pure shared structural scopes, printed billing units and atomic evidence.

No network, consumer imports or default units. Absence is not a negative claim.
"""
from dataclasses import dataclass, asdict
from functools import lru_cache
import hashlib
import re
from html import unescape


def readable(value):
    return ' '.join(unescape(re.sub(r'<[^>]+>', ' ', value)).split())


def explicit_unit(value, header='', context=''):
    """A printed cell overrides a scoped default; unknown dimensions never do.

    A million is a denominator, not a token dimension. Do not reinterpret chars.
    """
    parts=[readable(s).lower() for s in (value, header, context)]
    unsupported=r'(?:每百万\s*(?!tokens?\b)[^\s）)]|(?:/|per)\s*(?:1m|m|million)\s+(?!tokens?\b)[a-z])'
    if any(re.search(unsupported, s) for s in parts[:2]):
        return None
    patterns={
        'per_1M_tokens':r'(?:每百万\s*tokens?\b|(?:/|per)\s*(?:1m|m|million)\s*tokens?\b|/\s*mtok\b)',
        'per_image':r'(?:/\s*image\b|\bper\s+image\b|元/张|每张)',
        'per_second':r'(?:/\s*(?:sec|second)\b|\bper\s+second\b|元/秒|每秒)',
        'per_minute':r'(?:/\s*minute\b|\bper\s+minute\b)',
        'per_video':r'\bper\s+(?:video\b|[0-9]+p,\s*[0-9]+s\s+video\b)',
    }
    claims=[{u for u,pattern in patterns.items() if re.search(pattern,part)} for part in parts]
    quantity=r'(?:/|per)\s*(?:[0-9]+[mk]?|[mk]|million|thousand)\s*[a-z]{2,}|每[0-9一二三四五六七八九十百千万]+'
    if any(re.search(quantity,part) and not found for part,found in zip(parts[:2],claims[:2])):return None
    if any(len(found)>1 for found in claims):return None
    # A specific price column and its scalar cannot contradict one another.
    # A paragraph/table default is weaker and may be explicitly overridden.
    if claims[0] and claims[1] and claims[0]!=claims[1]:return None
    for found in claims:
        if found:return next(iter(found))
    # Fast's literal scalar /1M is qualified by its own token-rates paragraph.
    if re.search(r'/\s*1m$',parts[0]) and re.search(r'\btoken rates\b',parts[2]):
        return 'per_1M_tokens'
    return None


@dataclass(frozen=True)
class UnitEvidence:
    """Replayable unit derivation, not a caller-supplied verified flag.

    Column and cell spans are always strong. Defaults must be outside the table.
    Every constructor replays the derivation against the same source bytes.
    """
    version: int
    source_url: str
    source_sha256: str
    observed_at: str
    vendor: str
    channel: str
    scope_span: tuple
    cell_span: tuple
    row_span: tuple
    column_spans: tuple
    default_span: tuple | None
    unit: str

    def to_dict(self):
        value=asdict(self)
        for key in ('scope_span','cell_span','row_span'):value[key]=list(value[key])
        value['column_spans']=[list(span) for span in value['column_spans']]
        value['default_span']=list(value['default_span']) if value['default_span'] else None
        return value


@lru_cache(maxsize=16)
def source_digest(text):return hashlib.sha256(text.encode()).hexdigest()


@lru_cache(maxsize=256)
def unit_table_layout(scope):
    """Derive complete header chains and physical source cells, never caller columns.

    All offsets are relative to the one literal table. A spanning cell retains
    its actual origin; its header chain covers every logical column it owns.
    """
    from price_table_structure import Tables, expanded, pipes
    def html_cell(c):return (c['start'],c['start']+len(c.get('raw','')),c.get('raw',''))
    if re.match(r'\s*<table\b',scope,re.I):
        reader=Tables(scope);reader.feed(scope)
        if len(reader.tables)!=1:return None
        table=reader.tables[0];rows=expanded(table)
        if not rows:return None
        first=rows[0][1];label=readable(first[0].get('raw','')) if first else ''
        count=1
        while count<len(rows):
            cells=rows[count][1]
            if not cells or len(cells)!=len(first):break
            blank_label_header=not readable(cells[0].get('raw','')) and all(not re.search(r'[$元]',readable(c.get('raw',''))) for c in cells)
            if not (all(c.get('header') for c in cells) or label and readable(cells[0].get('raw',''))==label or blank_label_header):break
            count+=1
        headers=tuple(tuple(dict.fromkeys(html_cell(cells[i]) for _,cells in rows[:count])) for i in range(len(first)))
        layout=[]
        for row,cells in rows[count:]:
            if len(cells)!=len(headers) or any('start' not in c for c in cells):continue
            layout.append((row['start'],row['start']+len(row['quote']),tuple(html_cell(c) for c in cells)))
        return headers,tuple(layout)
    def pipe_cells(line,offset):
        bars=[m.start() for m in re.finditer(r'\|',line)];cells=[]
        for a,b in zip(bars,bars[1:]):
            raw=line[a+1:b];start=offset+a+1+len(raw)-len(raw.lstrip());value=raw.strip()
            cells.append((start,start+len(value),value))
        return tuple(cells)
    tables=list(pipes(scope))
    if len(tables)==1 and not scope[:tables[0]['start']].strip():
        table=tables[0];head=pipe_cells(table['header_quote'],table['start']);headers=tuple((c,) for c in head);rows=[];cursor=table['start']+len(table['header_quote'])
        for raw,_ in table['rows']:
            start=scope.find(raw,cursor);cursor=start+len(raw)
            cells=pipe_cells(raw,start)
            if len(cells)==len(headers):rows.append((start,cursor,cells))
        return headers,tuple(rows)
    tables=list(markdoc_tables(scope))
    if len(tables)==1 and not scope[:tables[0]['start']].strip():
        table=tables[0];body=table['body'];offset=scope.find(body,table['start']);blocks=re.split(r'^\s*---\s*$',body,flags=re.M);cursor=offset;groups=[]
        for block in blocks:
            start=scope.find(block,cursor);cursor=start+len(block);marks=list(re.finditer(r'^\s*\*\s+',block,re.M));cells=[]
            for i,m in enumerate(marks):
                stop=marks[i+1].start() if i+1<len(marks) else len(block);raw=block[m.end():stop];value=raw.strip();a=start+m.end()+len(raw)-len(raw.lstrip());cells.append((a,a+len(value),value))
            groups.append((start,start+len(block),tuple(cells)))
        if not groups or len(groups[0][2])!=3:return None
        return tuple((c,) for c in groups[0][2]),tuple(r for r in groups[1:] if len(r[2])==3)
    return None


def prove_unit(meta, text, *, cell, scope, row, scope_start=None, default='', cell_index=None, cell_start=None, columns=None):
    """Bind the physical cell to its actual full source header chain.

    cell_index/cell_start identify a source cell, never an authoritative header.
    Legacy columns is only a consistency assertion; it cannot select a column.
    Constructors rebuild solely from source cell position, not column_spans.
    """
    if not cell or not scope or not row:return None
    start=text.find(scope) if scope_start is None else scope_start
    if type(start) is not int or start<0 or text[start:start+len(scope)]!=scope:raise ValueError('unit scope is not literal')
    stop=start+len(scope);at=text.find(row,start,stop)
    if at<0:raise ValueError('unit row outside table')
    row_span=(at,at+len(row));default_span=None
    if default:
        pos=text.rfind(default,0,start)
        if pos<0:raise ValueError('unit default must be a preceding paragraph, not a price column')
        default_span=(pos,pos+len(default))
    layout=unit_table_layout(scope)
    if layout is None:return None
    headers,rows=layout
    matches=[r for r in rows if (start+r[0],start+r[1])==row_span]
    if len(matches)!=1:raise ValueError('unit row is not a complete structural data row')
    cells=matches[0][2]
    indices=[i for i,c in enumerate(cells) if c[2]==cell and (cell_start is None or start+c[0]==cell_start)]
    if cell_index is not None:
        if type(cell_index) is not int or cell_index not in indices:raise ValueError('unit cell index/value not bound to source row')
        indices=[cell_index]
    if not indices:raise ValueError('unit cell outside materialized source row or explicit rowspan')
    physical={cells[i][:2] for i in indices}
    if len(physical)!=1:return None # equal text in different source cells is not an identity
    a,b=next(iter(physical));owned=[i for i,c in enumerate(cells) if c[:2]==(a,b)]
    chain=tuple(dict.fromkeys(c for i in owned for c in headers[i]))
    if any(c[1]<=c[0] for c in chain):return None
    if columns is not None and tuple(map(readable,columns))!=tuple(readable(c[2]) for c in chain):return None
    unit=explicit_unit(cell,' / '.join(c[2] for c in chain),default)
    if unit is None:return None
    actual=source_digest(text)
    if meta.get('source_sha256')!=actual:raise ValueError('unit original hash mismatch')
    return UnitEvidence(2,meta['source_url'],actual,meta['observed_at'],meta['vendor'],meta['channel'],(start,stop),(start+a,start+b),row_span,tuple((start+c[0],start+c[1]) for c in chain),default_span,unit)


def consume_unit(evidence, meta, text, quote, expected=None):
    """Revalidate typed/serialized evidence at *all* materialization exits.

    Altered units, copied evidence from another source/row, bare strings and
    merely decorative dictionaries are rejected, regardless of price_verified.
    """
    if isinstance(evidence,dict):
        try:
            value=dict(evidence)
            for key in ('scope_span','cell_span','row_span'):value[key]=tuple(value[key])
            value['column_spans']=tuple(tuple(x) for x in value['column_spans'])
            value['default_span']=tuple(value['default_span']) if value['default_span'] is not None else None
            evidence=UnitEvidence(**value)
        except (KeyError,TypeError,ValueError):raise ValueError('malformed unit evidence') from None
    if type(evidence) is not UnitEvidence or type(evidence.version) is not int or evidence.version!=2:raise ValueError('typed unit evidence required')
    for key in ('source_url','source_sha256','observed_at','vendor','channel'):
        if getattr(evidence,key)!=meta.get(key):raise ValueError('unit evidence context mismatch')
    def literal(span):
        if len(span)!=2 or any(type(x) is not int for x in span) or not 0<=span[0]<span[1]<=len(text):raise ValueError('unit evidence span invalid')
        return text[span[0]:span[1]]
    scope=literal(evidence.scope_span)
    if not quote or quote!=literal(evidence.row_span) or quote not in scope:raise ValueError('unit evidence not bound to materialized row')
    rebuilt=prove_unit(meta,text,cell=literal(evidence.cell_span),cell_start=evidence.cell_span[0],scope=scope,row=literal(evidence.row_span),scope_start=evidence.scope_span[0],default=literal(evidence.default_span) if evidence.default_span else '')
    if rebuilt!=evidence or expected is not None and evidence.unit!=expected:raise ValueError('unit derivation rejected or changed')
    return evidence


def markdoc_tables(text):
    """Yield tables with actual open tab/heading ownership, including no tab.

    Closing tokens pop the structural stack. A malformed stack is surfaced and
    never used to normalize rates. Quotes remain original substrings.
    """
    token=re.compile(r'^(?P<heading>#{1,6} [^\n]*)|{%\s*(?P<close>/?)\s*(?P<tag>tabs|tab|table)\b(?P<attrs>[^%]*)%}',re.M)
    stack=[];headings={};active=None;errors=[]
    for match in token.finditer(text):
        if match['heading'] is not None:
            if active is not None:continue
            heading=match['heading'];level=len(heading)-len(heading.lstrip('#'))
            headings={k:v for k,v in headings.items() if k<level};headings[level]=heading
            continue
        tag=match['tag']
        if not match['close']:
            if tag=='table':
                if active is not None:errors.append('nested_table')
                tab=next((x for x in reversed(stack) if x['tag']=='tab'),None)
                active=dict(start=match.start(),body_start=match.end(),headings=dict(headings),tab=tab['title'] if tab else None,tab_quote=tab['quote'] if tab else None,scope_errors=list(errors))
            title=re.search(r'title="([^"]+)"',match['attrs'])
            stack.append(dict(tag=tag,title=title[1] if title else None,quote=match[0]))
            continue
        positions=[i for i,item in enumerate(stack) if item['tag']==tag]
        if not positions:
            errors.append('unmatched_close_'+tag)
            if active is not None:active['scope_errors'].append(errors[-1])
            continue
        position=positions[-1]
        if position!=len(stack)-1:
            errors.append('mismatched_close_'+tag)
            if active is not None:active['scope_errors'].append(errors[-1])
        del stack[position:]
        if tag=='table' and active is not None:
            active['body']=text[active.pop('body_start'):match.start()]
            active['quote']=text[active['start']:match.end()]
            if active['scope_errors']:active['tab']=None;active['tab_quote']=None
            yield active
            active=None
    if active is not None:
        active['body']=text[active.pop('body_start'):]
        active['quote']=text[active['start']:]
        active['scope_errors'].append('unclosed_table')
        yield active


def atomic_claim(text, quote, value, predicate):
    """Each projected proposition has its own predicate and literal witness."""
    if quote not in text:raise ValueError('nonliteral claim quote')
    verified=bool(predicate(quote))
    return dict(state='verified' if verified else 'unknown',value=value if verified else None,
                quote=quote if verified else None,
                quote_sha256=hashlib.sha256(quote.encode()).hexdigest() if verified else None)


def entity_clauses(text, anchor):
    """Finite clause/coreference grammar; an unknown/new subject ends the chain.

    Punctuation only delimits clauses. Subject proof, never the choice of a
    semicolon vs period, decides which propositions can describe the entity.
    """
    paragraphs=re.findall(r'<p(?:\s[^>]*)?>.*?</p>',text,re.S) if '<p' in text else re.split(r'\n\s*\n',text)
    found=[]
    for paragraph in paragraphs:
        if not readable(paragraph).startswith(anchor):continue
        # Work on visible characters while retaining exact original quote spans.
        visible=[];mapping=[]
        for m in re.finditer(r'<[^>]*>|\[(?P<label>[^]\n]+)\]\([^)]*\)|&(?:#[0-9]+|#x[0-9a-fA-F]+|[A-Za-z]+);|[^\[<&]+|[\[<&]',paragraph):
            if m[0].startswith('<') and m[0].endswith('>'):continue
            if m['label'] is not None:
                visible.append(m['label']);mapping.extend((m.start('label')+i,m.start('label')+i+1) for i in range(len(m['label'])));mapping[-1]=(mapping[-1][0],m.end());continue
            decoded=unescape(m[0]);visible.append(decoded)
            if decoded==m[0]:mapping.extend((m.start()+i,m.start()+i+1) for i in range(len(decoded)))
            else:mapping.extend([(m.start(),m.end())]*len(decoded))
        clean=''.join(visible)
        # Accept complete finite atoms, not a prefix followed by arbitrary prose.
        # Coordinators inside a consumed noun-list/cost expression are objects;
        # every other coordinator is a boundary even for an unseen next verb.
        reserved=r'(?:and|but|or|nor|while|whereas|because|although|when|if|unless|since|until|that|which|who|though)'
        lower=r'(?!(?:'+reserved+r')\b)[a-z][a-z-]*'
        noun=r'(?:Cursor|Grok Build|the public xAI API|(?:a|the|your|our|its|their) (?:'+lower+r' ){0,8}(?:API|plan|subscription|tier))'
        noun+=r"(?![A-Za-z0-9_'’])"
        objects=noun+r'(?:\s*(?:,? and|,? or|,)\s+'+noun+r')*'
        available=r'(?:not )?available (?:only |somewhere )?(?:in|on) '+objects
        billed=r'(?:not )?billed '+lower+r'(?: '+lower+r'){0,10}'
        cost=r'costs [0-9]+(?:\.[0-9]+)?x the standard token rates(?:, or [0-9]+(?:\.[0-9]+)?x for long-context requests)?'
        predicate=re.compile(r'(?:(?:is|was|remains) (?:'+available+'|'+billed+')|'+cost+')')
        contracted=re.compile(r'(?:'+available+'|'+billed+')')
        boundary=re.compile(r',|[;:!?—]|\.(?=\s|$)|\b'+reserved+r'\b')
        entity=anchor.split(' is ',1)[0]
        clauses=[];focus=False;subject=None;first_subject=None;safe_end=0;prefix_open=True;cursor=0;coordinated=False
        def emit(begin,end,relation,unique,reason=None):
            nonlocal safe_end,prefix_open
            while begin<end and clean[begin].isspace():begin+=1
            while end>begin and clean[end-1].isspace():end-=1
            if begin>=end:return None
            start=mapping[begin][0];stop=mapping[end-1][1];quote=paragraph[start:stop]
            node=dict(quote=quote,quote_span=[start,stop],span_basis='paragraph',paragraph_sha256=hashlib.sha256(paragraph.encode()).hexdigest(),subject_quote=subject if unique else None,relation=relation,complete_consumption=unique,unique_subject=unique)
            if reason:node['unknown_reason']=reason
            clauses.append(node)
            if unique and prefix_open:safe_end=stop
            elif not unique:prefix_open=False
            return quote
        while cursor<len(clean):
            while cursor<len(clean) and clean[cursor].isspace():cursor+=1
            if cursor>=len(clean):break
            punct=re.match(r'[;:!?—]|\.(?=\s|$)|,',clean[cursor:])
            if punct:cursor+=punct.end();coordinated=False;continue
            conjunction=re.match(r'('+reserved+r')\b\s*',clean[cursor:])
            if conjunction:
                word=conjunction[1];cursor+=conjunction.end();coordinated=word in ('and','but','or','nor')
                if not coordinated:focus=False
                continue
            begin=cursor;relation=None;end=None;named=False
            if clean.startswith(anchor,cursor):
                end=cursor+len(anchor);named=True;relation='named_entity'
            else:
                at=cursor;short=False
                if clean.startswith(entity+' ',cursor):at+=len(entity)+1;named=True;relation='named_entity'
                elif clean.startswith("It's ",cursor) or clean.startswith('It’s ',cursor):at+=5;short=True;relation='unique_it'
                elif clean.startswith('It ',cursor):at+=3;relation='unique_it'
                elif clean.startswith("Grok Build's free tier does not include it",cursor) or clean.startswith('Grok Build’s free tier does not include it',cursor):
                    m=re.match(r"Grok Build(?:'s|’s) free tier does not include it",clean[cursor:]);end=cursor+m.end();relation='unique_object_it'
                elif re.match(r'(?:The |the )?[Tt]oken rates(?: below)? are ',clean[cursor:]):
                    m=re.match(r'(?:The |the )?[Tt]oken rates(?: below)? are ',clean[cursor:]);at+=m.end();short=True;relation='entity_rates'
                elif coordinated:relation='coordinated_same_subject'
                if end is None and relation:
                    m=(contracted if short else predicate).match(clean,at)
                    if m:end=m.end()
            # A match must end at a real boundary, not midway through an unknown
            # complement. Failure invalidates the chain; absence of detection is
            # never positive proof that the subject is still the same.
            if end is not None and end<len(clean) and clean[end-1] not in '.!?' and not (clean[end:].lstrip()=='' or boundary.match(clean,end) or re.match(r'\s+(?:'+reserved+r')\b',clean[end:])):end=None
            if end is None:
                match=boundary.search(clean,cursor+1);end=match.start() if match else len(clean)
                emit(begin,end,'unresolved',False,'unconsumed syntax or unproved subject; explicit entity naming required to restore')
                focus=False;cursor=max(end,cursor+1);coordinated=False;continue
            unique=named or focus
            if named:
                focus=True
                subject=paragraph[mapping[begin][0]:mapping[end-1][1]]
                if first_subject is None:first_subject=subject
            quote_end=end
            if end<len(clean) and re.match(r'[.!?;:](?=\s|$)',clean[end:]):quote_end+=1
            emit(begin,quote_end,relation,unique,None if unique else 'pronoun/object continuation after unresolved subject')
            cursor=quote_end;coordinated=False
        subject=first_subject
        found.append((clauses,subject,paragraph[:safe_end] if safe_end else ''))
    return found[0] if len(found)==1 else ([],None,'')


def entity_prose(text, anchor):
    clauses,subject,prefix=entity_clauses(text,anchor)
    return prefix,subject


def entity_claim(text, clauses, value, predicate):
    witnesses=[c for c in clauses if c.get('complete_consumption') is True and c.get('unique_subject') is True and predicate(c['quote'])]
    if not witnesses:return dict(state='unknown',value=None,quote=None,quote_sha256=None,unknown_reason='no completely consumed unique-subject witness',unresolved_witnesses=[c for c in clauses if not c.get('unique_subject') and predicate(c['quote'])])
    witness=witnesses[0]
    result=atomic_claim(text,witness['quote'],value,predicate)
    result.update(subject_quote=witness['subject_quote'],subject_relation=witness['relation'])
    return result
