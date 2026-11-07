"""Attach the reproducibility bundle and byte manifests to the manuscript PDF."""
import hashlib,json
from pathlib import Path
from pypdf import PdfReader,PdfWriter
ROOT=Path(__file__).resolve().parent
report=json.loads((ROOT/'verification/independent_verification.json').read_text())
assert report.get('numerical_verification_result')=='PASS'
review=json.loads((ROOT/'verification/manuscript_review.json').read_text())
assert review['result']=='PASS'
assert hashlib.sha256((ROOT/'paper/main.tex').read_bytes()).hexdigest()==review['manuscript_sha256']
src=ROOT/'output/pdf/main.pdf'; out=ROOT/'output/pdf/Void_Synthesis_Shart.pdf'
assert hashlib.sha256(src.read_bytes()).hexdigest()==review['reviewed_pdf_sha256']
writer=PdfWriter(clone_from=str(src))
title=json.loads((ROOT/'unicode-manifest.json').read_text())['Synthesis title']['text']
writer.add_metadata({'/Title':title,'/Author':'Rayan Pal','/Subject':'Hash-bound synthesis of continuation control, exact cross-script rendering, and hosted zero-byte responses'})
names=['prompt-manifest.json','source-manifest.json','unicode-manifest.json','evidence.zip','verify_evidence.py','derive.py']
for name in names:writer.add_attachment(name,(ROOT/name).read_bytes())
with out.open('wb') as f:writer.write(f)
reader=PdfReader(out)
for name in names:assert reader.attachments[name][0]==(ROOT/name).read_bytes(),name
assert len(reader.pages)==len(PdfReader(src).pages)
layout=PdfReader(src)
for before,after in zip(layout.pages,reader.pages):
    assert before.get_contents().get_data()==after.get_contents().get_data(),'Page content changed during attachment embedding'
    assert before.extract_text()==after.extract_text(),'Page text changed during attachment embedding'
package={'result':'PASS','pdf':str(out.relative_to(ROOT)),'pdf_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'reviewed_layout_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'pages':len(reader.pages),'page_content_preserved':True,'attachments':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}}
(ROOT/'verification/final_package.json').write_text(json.dumps(package,indent=2)+'\n')
print('PDF:',out,'pages:',len(reader.pages),'bytes:',out.stat().st_size,'sha256:',hashlib.sha256(out.read_bytes()).hexdigest())
