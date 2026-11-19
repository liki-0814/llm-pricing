#!/usr/bin/env python3
"""Bounded public-GET source capture. No auth, link crawling or stale-as-fresh.

Only the ten reviewed official public documents are fetchable. A failed source
is recorded once and never retried. Last-known cache provenance is retained
separately; it never enters this attempt's successfully fetched document set.
"""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import uuid
import public_price_facts as facts


def now():return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
def atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');temp.write_bytes(data);os.replace(temp,path)
def save(path,value):atomic(path,(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())

class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self):super().__init__();self.hops=0
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        self.hops+=1;target=urllib.parse.urljoin(req.full_url,newurl)
        # Exact reviewed documents, not merely a trusted domain/private API.
        if self.hops>3 or target not in facts.SOURCES:raise ValueError('unreviewed public redirect')
        return urllib.request.Request(target,headers={'User-Agent':'llm-pricing-public-price-capture/1','Accept':'text/html,text/plain,text/markdown'},method='GET')

def public_get(url):
    if url not in facts.SOURCES:raise ValueError('unreviewed source URL')
    req=urllib.request.Request(url,headers={'User-Agent':'llm-pricing-public-price-capture/1','Accept':'text/html,text/plain,text/markdown'},method='GET')
    with urllib.request.build_opener(PublicRedirect()).open(req,timeout=25) as response:
        if response.status!=200 or response.geturl() not in facts.SOURCES:raise ValueError('not an approved HTTP200 original')
        body=response.read(8*1024*1024+1)
        if len(body)>8*1024*1024:raise ValueError('public document exceeds bounded capture size')
        return body,response.geturl()


def refresh(output,cache_dir,urls=None,fetcher=None):
    output=Path(output);cache=Path(cache_dir);urls=list(facts.SOURCES if urls is None else urls)
    if output.exists():raise ValueError('new capture directory required')
    if not urls or len(urls)!=len(set(urls)) or any(u not in facts.SOURCES for u in urls):raise ValueError('invalid reviewed source set')
    output.mkdir(parents=True);cache.mkdir(parents=True,exist_ok=True)
    attempt=uuid.uuid4().hex;started=now();transport='normal_public_HTTP_GET' if fetcher is None else 'test_injected_NOT_network';fetcher=fetcher or public_get
    def one(url):
        sid=hashlib.sha256(url.encode()).hexdigest();index=cache/(sid+'.json');previous=None
        if index.exists():
            try:
                candidate=json.loads(index.read_text());sha=candidate.get('source_sha256','')
                if re.fullmatch('[a-f0-9]{64}',sha) and candidate.get('source_url')==url:
                    cached_body=cache/(sha+'.body')
                    if cached_body.is_file() and facts.digest(cached_body.read_bytes())==sha:previous=candidate
            except (OSError,ValueError,TypeError):
                previous=None  # Corrupt cache is not evidence; one normal GET only.
        blocked=cache/(sid+'.blocked.json')
        if blocked.exists():
            return None,dict(source_url=url,status='skipped_blocked_NOT_fresh',checked_at=now(),attempt_id=attempt,reused_cache=False,retry_count=0),dict(previous,cache_only=True,not_fresh=True,cache_body_key=previous['source_sha256']+'.body') if previous else None
        try:
            body,final=fetcher(url)
            if final!=url:raise ValueError('reviewed source redirected to a different context; retain as failure pending review')
            vendor,channel=facts.SOURCES[url]
            meta=dict(vendor=vendor,channel=channel,source_url=url,observed_at=now(),source_sha256=facts.digest(body),body_path=sid+'.body',http_status=200,source_role='catalog' if url in facts.CATALOG_URLS else 'pricing',capture_kind='http_body',attempt_id=attempt)
            facts.verified_document(meta,body)
            # Original bytes before any parser. Both caches are content/address scoped.
            atomic(output/meta['body_path'],body);save(output/(sid+'.json'),meta)
            atomic(cache/(meta['source_sha256']+'.body'),body);save(index,meta)
            return meta,dict(source_url=url,status='fetched_HTTP200',observed_at=meta['observed_at'],source_sha256=meta['source_sha256'],attempt_id=attempt,reused_cache=False),None
        except (OSError,ValueError,UnicodeError,urllib.error.URLError) as error:
            gate=isinstance(error,urllib.error.HTTPError) and error.code in (401,403,429) or isinstance(error,ValueError) and 'access gate' in str(error)
            if gate:save(blocked,dict(source_url=url,blocked_at=now(),reason=str(error)[:500],automatic_retry=False))
            status=dict(source_url=url,status='blocked_NOT_fresh' if gate else 'failed_NOT_fresh',checked_at=now(),error_type=type(error).__name__,message=str(error)[:500],attempt_id=attempt,reused_cache=False,retry_count=0)
            old=dict(previous,cache_only=True,not_fresh=True,cache_body_key=previous['source_sha256']+'.body') if previous else None
            return None,status,old
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(one,urls))
    sources=[m for m,_,_ in results if m];statuses=[s for _,s,_ in results];old=[o for _,_,o in results if o]
    run=dict(attempt_id=attempt,started_at=started,finished_at=now(),transport=transport,requested_urls=urls,source_results=statuses,
        all_sources_http_ok=transport=='normal_public_HTTP_GET' and len(sources)==len(urls),scope_complete=False,full_discovery_fresh=False)
    manifest=dict(version=1,sources=sources,refresh_run=run,archival_last_known=old);save(output/'capture-manifest.json',manifest)
    ledger=facts.load_capture(output);save(output/'price-ledger.json',ledger)
    return ledger


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--cache-dir',required=True);parser.add_argument('--only-url',action='append',choices=sorted(facts.SOURCES));args=parser.parse_args()
    ledger=refresh(args.output,args.cache_dir,args.only_url);r=ledger['refresh_run']
    print(json.dumps(dict(attempt_id=r['attempt_id'],transport=r['transport'],all_sources_http_ok=r['all_sources_http_ok'],source_results=r['source_results'],price_verified_count=len(ledger['facts']),scope_complete=False,full_discovery_fresh=False),ensure_ascii=False,indent=2))
    return 0 if r['all_sources_http_ok'] else 2

if __name__=='__main__':raise SystemExit(main())
