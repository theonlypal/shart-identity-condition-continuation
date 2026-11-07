"""Preserve archival metadata, embedded historical evidence, and definition sources."""
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((ROOT/'source-manifest.json').read_text())
for key,folder,doi,names in [
 ('origin','zenodo-23070524','23070524',['record.json','paper.pdf','attachments','evidence']),
 ('rsi','zenodo-22117763','22117763',['record.json','Recursive_Self_Improvement_and_the_Binding_Condition.pdf','rsi.txt']),
]:
    src=ROOT/'sources'/folder; item={'repository':'https://zenodo.org/records/'+doi,'doi':'10.5281/zenodo.'+doi,'commit':None,'files':{},'checks':[]}
    rec=json.loads((src/'record.json').read_text()); pdf=src/('paper.pdf' if key=='origin' else rec['files'][0]['key'])
    assert 'md5:'+hashlib.md5(pdf.read_bytes()).hexdigest()==rec['files'][0]['checksum']
    item['checks'].append({'archive_md5':rec['files'][0]['checksum'],'verified':True})
    for name in names:
        root=src/name
        for f in sorted(root.rglob('*')) if root.is_dir() else [root]:
            if not f.is_file() or '__pycache__' in f.parts:continue
            rel=f.relative_to(src); dst=ROOT/'evidence'/key/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dst)
            item['files'][str(rel)]={'sha256':sha(dst),'bytes':dst.stat().st_size}
    manifest[key]=item

dest=ROOT/'evidence/chronology';dest.mkdir(parents=True,exist_ok=True)
for name in ['zenodo_records.json','chapter_source_map.json']:
    shutil.copyfile(ROOT/'inventory'/name,dest/name)
for f in (ROOT/'inventory/zenodo_records').glob('*.json'):
    target=dest/'records'/f.name;target.parent.mkdir(exist_ok=True);shutil.copyfile(f,target)
records=json.loads((dest/'zenodo_records.json').read_text())
items=[]
for r in records:
    matches=[(k,s) for k,s in manifest.items() if s['doi']==r['doi']]
    item={'doi':r['doi'],'title':r['title'],'publication_date':r['publication_date'],'record_created_utc':r['created'],'commit':None,'commit_date':None,'tag':None}
    if matches and matches[0][1]['commit']:
        key,source=matches[0]; item['commit']=source['commit']
        repo=ROOT/'sources'/('pccg2' if key=='pccg2' else source['repository'].rsplit('/',1)[-1])
        item['commit_date']=subprocess.check_output(['git','-C',str(repo),'show','-s','--format=%cI',source['commit']],text=True).strip()
        item['tag']=subprocess.check_output(['git','-C',str(repo),'tag','--points-at',source['commit']],text=True).strip() or None
    items.append(item)
(ROOT/'generated/chronology.json').write_text(json.dumps(items,ensure_ascii=False,indent=2)+'\n')
item={'repository':'https://zenodo.org','doi':None,'commit':None,'files':{},'checks':[]}
for f in sorted(dest.rglob('*')):
    if f.is_file():item['files'][str(f.relative_to(dest))]={'sha256':sha(f),'bytes':f.stat().st_size}
manifest['chronology']=item
(ROOT/'source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print('Context sources sealed:',len(items),'chronology entries')
