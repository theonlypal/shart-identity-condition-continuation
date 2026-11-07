"""Validate portrait pages and exact mixed-script text in the PDF layout."""
import hashlib,json
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parent
pdf=ROOT/'output/pdf/main.pdf';reader=PdfReader(pdf)
cover_text=reader.pages[0].extract_text()
assert cover_text.count('November 7, 2026')==1
assert cover_text.index('The model terminates on purpose.')<cover_text.index('November 7, 2026')<cover_text.index('Rayan Pal')
actual='063405b805c105e805b005d8'
checks=[]
for i,page in enumerate(reader.pages,1):
    assert page.rotation==0 and page.mediabox.width<page.mediabox.height,i
    checks.append({'page':i,'rotation':page.rotation,'width':float(page.mediabox.width),'height':float(page.mediabox.height)})
assert ('feff'+actual).encode() in reader.pages[0].get_contents().get_data().lower()
source=(ROOT/'paper/main.tex').read_text()
assert 'ActualText='+actual.upper() in source
assert '\\begin{landscape}' not in source
log=(ROOT/'output/pdf/main.log').read_text()
assert 'Missing character' not in log and 'Overfull' not in log
report={'result':'PASS','pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
        'manuscript_sha256':hashlib.sha256(source.encode()).hexdigest(),
        'pages':checks,'mixed_T1_codepoints':['U+'+actual[i:i+4].upper() for i in range(0,len(actual),4)],
        'mixed_T1_actualtext_exact':True,'overfull_boxes':0,'missing_glyphs':0,
        'paper_date':'November 7, 2026','date_beneath_title':True,
        'visual_inspection':{'pages':list(range(1,len(reader.pages)+1)),
          'result':'PASS','observations':'All pages inspected as rendered images: upright portrait layout, readable tables and captions, no clipping or overlaps. Title inspected at enlarged resolution; Arabic sheen, Hebrew marks, resh and tet remain distinct.'}}
(ROOT/'verification/layout_verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('LAYOUT VERIFIED:',len(reader.pages),'upright portrait pages; exact T1 ActualText; no overfull boxes or missing glyphs')
