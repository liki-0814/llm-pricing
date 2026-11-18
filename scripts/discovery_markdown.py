"""Shared formal Markdown line eligibility; fenced examples never supply directory facts."""
import re

def sections(text):
    """Line-preserving Markdown sections; legal EOF closes a section, not a fence."""
    result=[];current=dict(name=None,line=1,lines=[],termination=None);fence=None
    for number,line in enumerate(text.splitlines(),1):
        if fence:
            if re.fullmatch(r' {0,3}'+re.escape(fence[0])+r'{'+str(fence[1])+r',}[ \t]*',line):fence=None
            continue
        start=re.match(r' {0,3}(`{3,}|~{3,})(.*)$',line)
        if start:fence=(start[1][0],len(start[1]));continue
        heading=re.match(r'^## (.+?)\s*$',line)
        if heading:
            current['termination']='next_heading';result.append(current)
            current=dict(name=heading[1],line=number,lines=[],termination=None)
        else:current['lines'].append((number,line))
    current['termination']='unclosed_fence' if fence else 'EOF';result.append(current)
    return result


def formal_text(text):
    lines=["" for _ in text.splitlines()]
    for section in sections(text):
        if section["name"] is not None:lines[section["line"]-1]="## "+section["name"]
        for number,line in section["lines"]:lines[number-1]=line
    return "\n".join(lines)
