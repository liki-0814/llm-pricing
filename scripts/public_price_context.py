"""Pure shared structural scopes, printed billing units and atomic evidence.

No network, consumer imports or default units. Absence is not a negative claim.
"""
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
        'per_video':r'\bper\s+video\b',
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


def entity_prose(text, anchor):
    """Return one literal, subject-bound paragraph/coreference chain.

    Pronouns can continue the named subject; a new named sentence or another
    paragraph cannot lend its exclusions to that subject. Unknown grammar fails
    closed without discarding independently retained price-table candidates.
    """
    paragraphs=re.findall(r'<p(?:\s[^>]*)?>.*?</p>',text,re.S) if '<p' in text else re.split(r'\n\s*\n',text)
    found=[]
    for paragraph in paragraphs:
        if not readable(paragraph).startswith(anchor):continue
        boundaries=list(re.finditer(r'(?<=\.)\s+(?=[A-Z])',paragraph))
        spans=[];start=0
        for boundary in boundaries:
            spans.append((start,boundary.start()));start=boundary.end()
        spans.append((start,len(paragraph)));end=spans[0][1]
        for start,stop in spans[1:]:
            if not readable(paragraph[start:stop]).startswith(('It ',"It's ",'It’s ')):break
            end=stop
        found.append((paragraph[:end],paragraph[:spans[0][1]]))
    return found[0] if len(found)==1 else ('',None)
