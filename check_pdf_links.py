"""Check public HTTP targets encoded as PDF link annotations."""
import concurrent.futures,datetime,json,urllib.request
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parent
links=set()
for page in PdfReader(ROOT/'output/pdf/main.pdf').pages:
    for annotation in page.get('/Annots',[]):
        action=annotation.get_object().get('/A',{})
        url=action.get('/URI','')
        if url.startswith(('http://','https://')):links.add(str(url))
def check(url):
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 scholarly-artifact-link-check'},method='GET')
        with urllib.request.urlopen(req,timeout=40) as response:
            return {'url':url,'status':response.status,'resolved_url':response.url}
    except Exception as error:return {'url':url,'error':str(error)}
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:rows=list(pool.map(check,sorted(links)))
bad=[r for r in rows if r.get('status')!=200]
report={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'urls':rows,'passed':len(rows)-len(bad),'total':len(rows),'result':'PASS' if not bad else 'INCOMPLETE'}
(ROOT/'verification/link_check.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['result'],report['passed'],'/',report['total'])
for row in bad:print(row)
