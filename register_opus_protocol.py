"""Bind the preserved frozen protocol to its published revision and checksums."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
folder=ROOT/'evidence/opus_protocol'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
checked=0
for line in (folder/'SHA256SUMS').read_text().splitlines():
    digest,name=line.split(None,1)
    assert sha(folder/name.lstrip('*'))==digest,name
    checked+=1
manifest=json.loads((ROOT/'source-manifest.json').read_text())
results=ROOT/'evidence/opus'
for p in sorted(results.rglob('*')):
    if p.is_file():manifest['opus']['files'][str(p.relative_to(results))]={'sha256':sha(p),'bytes':p.stat().st_size}
manifest['opus_protocol']={
    'repository':'https://github.com/theonlypal/opus45-opus46-matched-prereg-final',
    'commit':'1d836fa4c34cd769ba8c9b0334e7ceffa95be0ee',
    'doi':'10.5281/zenodo.23744106','tag':'v1.0.0',
    'checks':[{'manifest':'SHA256SUMS','sha256':sha(folder/'SHA256SUMS'),'verified_files':checked}],
    'files':{str(p.relative_to(folder)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(folder.rglob('*')) if p.is_file()}}
(ROOT/'source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
chron=json.loads((ROOT/'generated/chronology.json').read_text())
for row in chron:
    if row['doi']==manifest['opus_protocol']['doi']:row['commit']=manifest['opus_protocol']['commit']
(ROOT/'generated/chronology.json').write_text(json.dumps(chron,ensure_ascii=False,indent=2)+'\n')
print('Frozen protocol manifest verified:',checked)
