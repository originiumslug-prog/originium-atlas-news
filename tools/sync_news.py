#!/usr/bin/env python3
"""Read official public news, validate, sanitize and preserve last good articles."""
import argparse, datetime as dt, hashlib, html, json, os, re, ssl, time
import urllib.parse as U
import urllib.request as R
from html.parser import HTMLParser
from pathlib import Path

API = 'https://arknights.jp/api/resource/news/list'
ALLOWED = {'arknights.jp', 'webusstatic.yo-star.com'}
MAX_JSON = 16 * 1024**2
MAX_IMAGE = 30 * 1024**2

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def digest(b): return hashlib.sha256(b).hexdigest()
def safe_url(s, base='https://arknights.jp/news'):
    try:
        if any(ord(c)<32 for c in str(s)): return None
        u = U.urlsplit(U.urljoin(base, str(s)))
        if u.scheme != 'https' or not u.hostname or u.username or u.password or u.port not in (None,443): return None
        return U.urlunsplit(u)
    except (ValueError, TypeError): return None

def allowed_url(s):
    u=safe_url(s)
    if not u or U.urlsplit(u).hostname not in ALLOWED: raise ValueError('Download host not approved')
    return u
class Redirect(R.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, allowed_url(newurl))

def fetch(url, limit):
    url=allowed_url(url)
    for attempt in range(3):
        try:
            req=R.Request(url,headers={'User-Agent':'OriginiumAtlas-NewsSync/1.0 (public news; bounded requests)','Accept':'application/json,image/*;q=0.8,*/*;q=0.5'})
            with R.build_opener(Redirect()).open(req,timeout=40) as r:
                if int(r.headers.get('Content-Length','0'))>limit: raise ValueError('Response too large')
                b=r.read(limit+1)
                if len(b)>limit: raise ValueError('Response too large')
                return b, r.headers.get('Content-Type','').split(';')[0].lower()
        except Exception:
            if attempt==2: raise
            time.sleep(2**attempt)

def atomic(path, b):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp');tmp.write_bytes(b);os.replace(tmp,path)
def save(path, x): atomic(path,(json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode())
def image_type(b):
    if b.startswith(b'\x89PNG\r\n\x1a\n'): return '.png'
    if b.startswith(b'\xff\xd8\xff'): return '.jpg'
    if b.startswith((b'GIF87a',b'GIF89a')): return '.gif'
    if b[:4]==b'RIFF' and b[8:12]==b'WEBP': return '.webp'
    raise ValueError('Unsupported image signature (HTML/SVG rejected)')

class Cleaner(HTMLParser):
    tags={'p','br','h1','h2','h3','h4','h5','h6','strong','b','em','i','u','s','ul','ol','li','blockquote','table','thead','tbody','tr','th','td','hr','a','img','span','div','pre','code'}
    void={'br','hr','img'}
    blocked={'script','style','iframe','object','embed','svg','math','form','template'}
    def __init__(self):
        super().__init__(convert_charrefs=True);self.out=[];self.stack=[];self.suppressed=[];self.images=[];self.unsupported=set();self.text=[]
    def handle_starttag(self, tag, attrs):
        if self.suppressed:
            if tag not in self.void:self.suppressed.append(tag)
            return
        if tag in self.blocked:
            self.unsupported.add(tag)
            if tag not in {'embed'}: self.suppressed.append(tag)
            return
        if tag not in self.tags: self.unsupported.add(tag);return
        d=dict(attrs);a=[]
        if tag=='a':
            u=safe_url(d.get('href','')) if d.get('href') else None
            if u:a=[('href',u),('target','_blank'),('rel','noopener noreferrer')]
        if tag=='img':
            u=safe_url(d.get('src','')) if d.get('src') else None
            if not u:self.unsupported.add('invalid-image');return
            self.images.append(u);a=[('src',u),('alt',d.get('alt') or ''),('loading','lazy'),('referrerpolicy','no-referrer')]
        if tag in {'td','th'}:
            for k in ('colspan','rowspan'):
                if d.get(k,'').isdigit() and 1<=int(d[k])<=30:a.append((k,d[k]))
        # No style, events, class, srcset or arbitrary attributes survive.
        self.out.append('<'+tag+''.join(' '+k+'="'+html.escape(v,quote=True)+'"' for k,v in a)+'>')
        if tag not in self.void:self.stack.append(tag)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag,attrs)
        if tag not in self.void:self.handle_endtag(tag)
    def handle_endtag(self, tag):
        if self.suppressed:
            if tag in self.suppressed:
                while self.suppressed:
                    if self.suppressed.pop()==tag:break
            return
        if tag in self.stack:
            while self.stack:
                t=self.stack.pop();self.out.append('</'+t+'>')
                if t==tag:break
    def handle_data(self,s):
        if not self.suppressed:self.out.append(html.escape(s));self.text.append(s)
    def result(self):
        while self.stack:self.out.append('</'+self.stack.pop()+'>')
        return ''.join(self.out)

def validate(payload):
    if not isinstance(payload,dict) or payload.get('code')!=0:raise ValueError('Official API did not report success')
    d=payload.get('data')
    if not isinstance(d,dict) or not isinstance(d.get('rows'),list) or not isinstance(d.get('count'),int):raise ValueError('Invalid API schema')
    return d

def transform(r):
    i=r.get('id');ts=r.get('publishTime');title=r.get('title');body=r.get('content')
    if type(i)!=int or i<=0 or type(ts)!=int or ts<=0 or not isinstance(title,str) or not title.strip() or not isinstance(body,str):raise ValueError('Invalid article fields')
    url=safe_url(r.get('link') or f'https://arknights.jp/news/{i}')
    if not url or U.urlsplit(url).hostname!='arknights.jp':raise ValueError('Invalid official article URL')
    c=Cleaner();c.feed(body);c.close();body_html=c.result()
    if not body_html.strip():raise ValueError('Empty article body')
    image=safe_url(r.get('smallImage') or r.get('bigImage') or '') if (r.get('smallImage') or r.get('bigImage')) else None
    source={k:r.get(k) for k in ('id','title','type','publishTime','offlineTime','content','smallImage','bigImage','link')}
    fingerprint=digest(json.dumps(source,ensure_ascii=False,sort_keys=True).encode())
    return {'id':i,'title':title,'category':str(r.get('type') or ''),'publishedAt':ts,'offlineAt':int(r.get('offlineTime') or 0),'url':url,'image':image,'bodyHtml':body_html,'excerpt':re.sub(r'\s+',' ',' '.join(c.text)).strip()[:180],'sourceSha256':fingerprint,'imageUrls':list(dict.fromkeys(([image] if image else [])+c.images)),'unsupported':sorted(c.unsupported)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',default='web/data');p.add_argument('--pages',type=int,default=2);p.add_argument('--page-size',type=int,default=20);p.add_argument('--backfill',action='store_true');p.add_argument('--input');p.add_argument('--download-images',action='store_true');p.add_argument('--image-budget-mib',type=int,default=150);args=p.parse_args()
    if not 1<=args.pages<=100 or not 1<=args.page_size<=50 or not 1<=args.image_budget_mib<=1024:p.error('Invalid request limit')
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    index_path=out/'index.json';old=json.loads(index_path.read_text()) if index_path.exists() else {};items={int(x['id']):x for x in old.get('articles',[])}
    run={'startedAt':now(),'mode':'backfill' if args.backfill else 'recent','pages':0,'officialCount':None,'seenIds':[],'updated':[],'errors':[],'imageMode':'mirror' if args.download_images else 'official-links','downloadedBytes':0,'completeBackfill':False}
    started=time.time();seen=set();changed=0
    try:
        for page in range(1,args.pages+1):
            if args.input:
                if page>1:break
                payload=json.loads(Path(args.input).read_text())
            else:
                raw,_=fetch(API+'?'+U.urlencode({'index':page,'size':args.page_size}),MAX_JSON);payload=json.loads(raw)
            d=validate(payload);run['pages']+=1;run['officialCount']=d['count']
            ids=[r.get('id') for r in d['rows']]
            if any(i in seen for i in ids):raise ValueError('Repeated article/page detected; pagination not trusted')
            for r in d['rows']:
                a=transform(r);i=a['id'];seen.add(i);run['seenIds'].append(i)
                # Save raw response independently, never render it directly.
                save(out/'raw'/f'{i}.json',r)
                old_entry=items.get(i);local_path=out/'articles'/f'{i}.json'
                previous=json.loads(local_path.read_text()) if local_path.exists() else None
                stable=bool(previous and old_entry and old_entry.get('sourceSha256')==a['sourceSha256'])
                if stable and (not args.download_images or previous.get('imagesMirrored')):
                    continue
                a['imageFiles']=[];a['imagesMirrored']=False
                if args.download_images:
                    for u in a['imageUrls']:
                        try:
                            if run['downloadedBytes']>=args.image_budget_mib*1024**2:raise ValueError('Image run budget exhausted')
                            b,mime=fetch(u,min(MAX_IMAGE,args.image_budget_mib*1024**2-run['downloadedBytes']));run['downloadedBytes']+=len(b)
                            ext=image_type(b);sha=digest(b);rel='images/'+sha+ext;atomic(out/rel,b)
                            a['imageFiles'].append({'source':u,'path':rel,'sha256':sha,'bytes':len(b),'mime':mime})
                        except Exception as e:
                            run['errors'].append({'id':i,'stage':'image','url':u,'error':str(e)[:200]})
                    a['imagesMirrored']=len(a['imageFiles'])==len(a['imageUrls'])
                    if not a['imagesMirrored']:
                        # Never replace the last complete article with a partly downloaded update.
                        continue
                a['checkedAt']=now();a['firstSeenAt']=previous.get('firstSeenAt',now()) if previous else now()
                save(local_path,a)
                items[i]={k:a[k] for k in ('id','title','category','publishedAt','offlineAt','url','image','excerpt','sourceSha256','checkedAt','imagesMirrored')}
                items[i]['path']=f'articles/{i}.json'
                items[i]['imagePath']=next((f['path'] for f in a['imageFiles'] if f['source']==a['image']),None)
                changed+=1;run['updated'].append(i)
            if not args.input and (len(seen)>=d['count'] or not d['rows']):
                run['completeBackfill']=True;break
            if not args.backfill or args.input:
                if page==args.pages or len(d['rows'])<args.page_size:break
            time.sleep(0.4)
        if not seen:raise ValueError('No articles returned; refusing empty replacement')
        if args.backfill and not run['completeBackfill'] and not args.input:run['errors'].append({'stage':'coverage','error':'Backfill page limit reached before official count'})
        run['finishedAt']=now();run['status']='partial' if run['errors'] else 'ok'
        last=old.get('lastSuccessfulCheckAt') if run['errors'] else run['finishedAt']
        save(index_path,{'schemaVersion':1,'source':API,'lastAttemptAt':run['finishedAt'],'lastSuccessfulCheckAt':last,'lastFullScanAt':run['finishedAt'] if run['completeBackfill'] and not run['errors'] else old.get('lastFullScanAt'),'officialCount':run['officialCount'],'imageMode':run['imageMode'],'articles':sorted(items.values(),key=lambda a:(a['publishedAt'],a['id']),reverse=True)})
        # No deletion from index merely because an article was absent in recent pages.
        save(out/'status.json',run)
        print(json.dumps({'status':run['status'],'seen':len(seen),'changed':changed,'errors':len(run['errors']),'downloadedBytes':run['downloadedBytes'],'completeBackfill':run['completeBackfill']}))
        return 1 if run['errors'] else 0
    except Exception as e:
        run.update(status='error',finishedAt=now());run['errors'].append({'stage':'fetch/validate','error':str(e)[:300]});save(out/'status.json',run)
        print('Sync failed; existing published index preserved:',str(e));return 1
if __name__=='__main__':raise SystemExit(main())
