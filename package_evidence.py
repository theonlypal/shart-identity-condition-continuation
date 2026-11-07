"""Build deterministic prompt, Unicode, and evidence attachments."""
import hashlib,json,zipfile,tarfile,io
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def digest(b):return hashlib.sha256(b).hexdigest()
strings={}
def add(group,label,text,source,message_supplied=True):
    assert isinstance(text,str)
    key=group+':'+label
    strings[key]={'text':text,'utf8_hex':text.encode().hex(),'sha256':digest(text.encode()),'source':source,'message_supplied':message_supplied}
for name,row in read(ROOT/'evidence/ablation/generated/prompt_hashes.json').items():
    add('ablation',name,row['text'],'ablation/generated/prompt_hashes.json',row['message_supplied'])
    assert strings['ablation:'+name]['sha256']==row['sha256']
for name,text in read(ROOT/'evidence/reassign/evidence/prompts.json').items():add('reassign',name,text,'reassign/evidence/prompts.json')
add('pccg2','system',read(ROOT/'evidence/pccg2/config.json')['system'],'pccg2/config.json')
seen=set()
for line in (ROOT/'evidence/cross/evidence/study/schedule.jsonl').read_text().splitlines():
    row=json.loads(line)
    for field in ['system','user']:
        text=row.get(field)
        if not isinstance(text,str):continue
        h=digest(text.encode()); key=(field,h)
        if key not in seen:add('cross',field+':'+h[:16],text,'cross/evidence/study/schedule.jsonl');seen.add(key)
seen=set()
for f in sorted((ROOT/'evidence/opus/exp3/attempts').glob('*/attempt-01/request.bin')):
    req=read(f)
    for role,text in [('system',req['system'])]+[(m['role'],m['content']) for m in req['messages']]:
        h=digest(text.encode());key=(role,h)
        if key not in seen:add('opus',role+':'+h[:16],text,str(f.relative_to(ROOT/'evidence')));seen.add(key)
for role,texts in [('system',[read(ROOT/'evidence/opus_protocol/prompts.json')['exp2']['system']]),('user',read(ROOT/'evidence/opus_protocol/prompts.json')['exp2']['inputs'])]:
    for text in texts:add('opus_exp2',role+':'+digest(text.encode())[:16],text,'opus_protocol/prompts.json')
for key in ['ab','replay']:
    req=read(next((ROOT/'evidence'/key/'records/requests').glob('*.json')))
    for m in req['messages']:
        if m['role']=='system':add(key,'system',m['content'],key+'/protocol.json')
for role,items in read(ROOT/'evidence/door_protocol/prompts.json').items():
    for name,row in items.items():
        add('door',role+':'+name,row['text'],'door_protocol/prompts.json')
        assert digest(row['text'].encode())==row['sha256']
(ROOT/'prompt-manifest.json').write_text(json.dumps(strings,ensure_ascii=False,indent=2)+'\n')
uni=read(ROOT/'evidence/origin/attachments/unicode-manifest.json')
for label,row in uni.items():
    assert row['utf8_hex']==row['text'].encode().hex()
    assert row['sha256']==digest(row['text'].encode())
title="שָׁרְט is identity.\nشَرْط is the condition.\nشָׁרְט renders on both vendors' served models.\nThe model terminates on purpose."
uni['Synthesis title']={'text':title,'utf8_hex':title.encode().hex(),'sha256':digest(title.encode()),'code_points':[f'U+{ord(x):04X}' for x in title]}
(ROOT/'unicode-manifest.json').write_text(json.dumps(uni,ensure_ascii=False,indent=2)+'\n')
tarbytes=io.BytesIO()
with tarfile.open(fileobj=tarbytes,mode='w',format=tarfile.PAX_FORMAT) as tar:
    files=list((ROOT/'evidence').rglob('*'))+[ROOT/p for p in ['derive.py','derive_opus_study.py','verify_evidence.py','source-manifest.json','prompt-manifest.json','unicode-manifest.json','generated/counts.json','generated/opus_study.json','generated/chronology.json']]
    for f in sorted(files):
        if not f.is_file():continue
        data=f.read_bytes();info=tarfile.TarInfo(str(f.relative_to(ROOT)));info.size=len(data);info.mode=0o644
        tar.addfile(info,io.BytesIO(data))
with zipfile.ZipFile(ROOT/'evidence.zip','w') as z:
    info=zipfile.ZipInfo('source-files.tar',(2026,11,7,0,0,0));info.compress_type=zipfile.ZIP_LZMA;info.external_attr=0o100644<<16
    z.writestr(info,tarbytes.getvalue())
print('prompts',len(strings),'unicode',len(uni),'evidence.zip', (ROOT/'evidence.zip').stat().st_size,digest((ROOT/'evidence.zip').read_bytes()))
