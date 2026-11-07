"""Offline verification of preserved bytes and independently derived synthesis tables."""
import hashlib,json,sys,zipfile,tarfile,io
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
from derive import derive
from derive_opus_study import derive_opus_study
def read(p):return json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def verify():
    manifest=read(ROOT/'source-manifest.json'); files=0
    for key,item in manifest.items():
        for rel,expected in item['files'].items():
            f=ROOT/'evidence'/key/rel
            assert f.resolve().is_relative_to((ROOT/'evidence').resolve()),rel
            assert f.stat().st_size==expected['bytes'],str(f)
            assert sha(f)==expected['sha256'],str(f)
            files+=1
    for name in ['prompt-manifest.json','unicode-manifest.json']:
        for k,row in read(ROOT/name).items():
            b=row['text'].encode('utf-8')
            assert b.hex()==row['utf8_hex'] and hashlib.sha256(b).hexdigest()==row['sha256'],k
            if 'code_points' in row:assert [f'U+{ord(x):04X}' for x in row['text']]==row['code_points'],k
    expected=read(ROOT/'generated/counts.json'); actual=derive()
    assert actual==expected,'Numerical derivation differs from generated/counts.json'
    assert derive_opus_study()==read(ROOT/'generated/opus_study.json'),'Opus prediction derivation differs'
    records={r['doi']:r for r in read(ROOT/'evidence/chronology/zenodo_records.json')}
    door=read(ROOT/'evidence/door_publication/door-zenodo-record.json')
    records[door['doi']]={'title':door['metadata']['title'],'publication_date':door['metadata']['publication_date'],'created':door['created']}
    chronology=read(ROOT/'generated/chronology.json')
    assert len(chronology)==len(records) and {r['doi'] for r in chronology}==set(records),'Chronology population differs'
    for row in chronology:
        source=records[row['doi']]
        assert (row['title'],row['publication_date'],row['record_created_utc'])==(source['title'],source['publication_date'],source['created']),row['doi']
        if row.get('commit'):
            assert any(s.get('doi')==row['doi'] and s.get('commit')==row['commit'] for s in manifest.values()),row['doi']
    if (ROOT/'evidence.zip').exists():
        with zipfile.ZipFile(ROOT/'evidence.zip') as z:
            paths={str(f.relative_to(ROOT)) for f in (ROOT/'evidence').rglob('*') if f.is_file()}|{'derive.py','derive_opus_study.py','verify_evidence.py','source-manifest.json','prompt-manifest.json','unicode-manifest.json','generated/counts.json','generated/opus_study.json','generated/chronology.json'}
            assert z.namelist()==['source-files.tar'],'Evidence archive envelope mismatch'
            with tarfile.open(fileobj=io.BytesIO(z.read('source-files.tar'))) as tar:
                assert {m.name for m in tar.getmembers()}==paths,'Evidence archive file set mismatch'
                for member in tar:
                    assert member.isfile() and hashlib.sha256(tar.extractfile(member).read()).hexdigest()==sha(ROOT/member.name),member.name
    if (ROOT/'SHA256SUMS').exists():
        for line in (ROOT/'SHA256SUMS').read_text().splitlines():
            h,p=line.split(None,1);f=ROOT/p.strip().lstrip('*')
            assert f.resolve().is_relative_to(ROOT.resolve())
            assert sha(f)==h,p
    if (ROOT/'verification/independent_verification.json').exists():
        report=read(ROOT/'verification/independent_verification.json')
        assert report.get('numerical_verification_result')=='PASS','Independent numerical verification has not passed'
        assert report['generated_counts_sha256']==sha(ROOT/'generated/counts.json'),'Independent count binding differs'
    if (ROOT/'verification/opus_study_audit.json').exists():
        opus_audit=read(ROOT/'verification/opus_study_audit.json')
        assert opus_audit['result']=='PASS' and opus_audit['tests_passed']==opus_audit['tests_total']
        assert opus_audit['provenance']['results_manifest']['missing']==0
        assert opus_audit['provenance']['results_manifest']['entries_bad']==0
    if (ROOT/'verification/manuscript_review.json').exists():
        review=read(ROOT/'verification/manuscript_review.json')
        assert review['result']=='PASS','Manuscript review has not passed'
        assert sha(ROOT/'paper/main.tex')==review['manuscript_sha256'],'Reviewed manuscript differs'
        assert review['generated_counts_sha256']==sha(ROOT/'generated/counts.json'),'Reviewed counts differ'
        assert review['numerical_report_sha256']==sha(ROOT/'verification/independent_verification.json'),'Reviewed numerical report differs'
        if 'opus_report_sha256' in review:
            assert review['opus_report_sha256']==sha(ROOT/'verification/opus_study_audit.json'),'Reviewed Opus report differs'
            assert review['generated_opus_study_sha256']==sha(ROOT/'generated/opus_study.json'),'Reviewed Opus derivation differs'
    if (ROOT/'verification/final_package.json').exists():
        package=read(ROOT/'verification/final_package.json')
        assert package['result']=='PASS' and package['page_content_preserved'] is True
        assert sha(ROOT/package['pdf'])==package['pdf_sha256'],'Sealed PDF differs'
        assert package['reviewed_layout_sha256']==review['reviewed_pdf_sha256'],'Sealed layout binding differs'
        assert package['pages']==review['pages'],'Sealed page count differs'
        for name,digest in package['attachments'].items():
            assert sha(ROOT/name)==digest,'Attachment source differs: '+name
    print(f'VERIFIED: {files} preserved source files; prompt and Unicode hashes; all numerical derivations; chronology; evidence archive')
    return files
if __name__=='__main__':verify()
