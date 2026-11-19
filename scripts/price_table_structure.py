"""Shared literal HTML grid and Markdown tables; no consumer imports or network."""
import re
from html.parser import HTMLParser

def clean(s):return ' '.join(s.split())

class Tables(HTMLParser):
    """Literal table/heading reader; rowspans carry their original source row."""
    def __init__(self,text):
        super().__init__(convert_charrefs=True)
        self.text=text;self.offsets=[0];self.tables=[];self.headings={};self.heading=None;self.table=None;self.row=None;self.cell=None;self.elements=[]
        for match in re.finditer('\n',text):self.offsets.append(match.end())
    def pos(self):
        line,col=self.getpos();return self.offsets[line-1]+col
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag not in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'):self.elements.append((tag,attrs,self.get_starttag_text()))
        if re.fullmatch('h[1-6]',tag) and self.table is None:self.heading=dict(level=int(tag[1]),start=self.pos(),parts=[])
        if tag=='table':
            if self.table is not None:raise ValueError('nested price tables unsupported')
            panel=next(((a,q) for _,a,q in reversed(self.elements) if a.get('role')=='tabpanel'),None)
            self.table=dict(start=self.pos(),headings=dict(self.headings),rows=[],tab_label=panel[0].get('aria-labelledby') if panel else None,tab_quote=panel[1] if panel else None)
        if tag=='tr' and self.table is not None:self.row=dict(start=self.pos(),cells=[])
        if tag in ('td','th') and self.row is not None:
            self.cell=dict(start=self.pos(),parts=[],rowspan=int(attrs.get('rowspan','1')),colspan=int(attrs.get('colspan','1')),header=tag=='th')
        if tag in ('p','br','div','blockquote') and self.cell is not None:self.cell['parts'].append(' ')
    def handle_data(self,data):
        if self.heading is not None:self.heading['parts'].append(data)
        if self.cell is not None:self.cell['parts'].append(data)
    def handle_endtag(self,tag):
        end=self.pos()+len('</'+tag+'>')
        for i in range(len(self.elements)-1,-1,-1):
            if self.elements[i][0]==tag:
                del self.elements[i:];break
        if self.heading is not None and tag=='h'+str(self.heading['level']):
            h=self.heading;h.update(text=clean(''.join(h['parts'])),quote=self.text[h['start']:end]);self.heading=None
            self.headings={k:v for k,v in self.headings.items() if k<h['level']};self.headings[h['level']]=h
        if tag in ('td','th') and self.cell is not None:
            self.cell['raw']=self.text[self.cell['start']:end]
            self.cell['text']=clean(''.join(self.cell.pop('parts')));self.row['cells'].append(self.cell);self.cell=None
        if tag=='tr' and self.row is not None:
            self.row.update(quote=self.text[self.row['start']:end]);self.table['rows'].append(self.row);self.row=None
        if tag=='table' and self.table is not None:
            self.table.update(quote=self.text[self.table['start']:end]);self.tables.append(self.table);self.table=None

def expanded(table):
    spans={};rows=[]
    for row in table['rows']:
        cells={};next_spans={}
        for col,(remaining,cell) in spans.items():
            cells[col]=cell
            if remaining>1:next_spans[col]=(remaining-1,cell)
        col=0
        for cell in row['cells']:
            while col in cells:col+=1
            cell=dict(cell,origin_quote=row['quote'])
            if cell['rowspan']<1 or cell['colspan']<1:raise ValueError('invalid table span')
            for j in range(cell['colspan']):
                cells[col+j]=cell
                if cell['rowspan']>1:next_spans[col+j]=(cell['rowspan']-1,cell)
            col+=cell['colspan']
        spans=next_spans
        rows.append((row,[cells.get(i,dict(text='',origin_quote=row['quote'])) for i in range(max(cells,default=-1)+1)]))
    return rows

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
            yield dict(start=start,end=pos,headers=header,header_quote=line,rows=rows,prefix=text[:start])
        else:pos+=len(line);i+=1
