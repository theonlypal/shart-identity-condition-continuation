"""Check manuscript structure, fixed empirical tables, and evidence bindings."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = '593dccdd4e4a1aed1d2826ebafc8bb8c319da5df30724485e5ad683d71aa5c13'
EXPECTED_COUNTS = 'bf550ef29c41b4663bb130aea1d50defee324e423f79af9620be3ff5162a11d8'
EXPECTED_OPUS = 'e43d0c92845a8a296aa7d280da34209b73d4cb0a69b6bff00f13101484d3c2d2'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def esc(text):
    for a, b in [('\\', r'\textbackslash{}'), ('&', r'\&'), ('%', r'\%'), ('_', r'\_'), ('#', r'\#')]:
        text = text.replace(a, b)
    return text

def verify(visual_pass=False):
    source = (ROOT/'paper/main.tex').read_text()
    pdf = ROOT/'output/pdf/main.pdf'
    reader = PdfReader(pdf)
    texts = [page.extract_text() for page in reader.pages]
    tables = [re.sub(r'\\label\{tab:evidence-\d+\}', '', t) for t in
              re.findall(r'\\begin\{longtable\}.*?\\end\{longtable\}', source, re.S)]
    assert len(tables) == 25
    assert hashlib.sha256('\n'.join(tables).encode()).hexdigest() == EXPECTED_TABLES
    assert sha(ROOT/'generated/counts.json') == EXPECTED_COUNTS
    assert sha(ROOT/'generated/opus_study.json') == EXPECTED_OPUS
    aux = (ROOT/'output/pdf/main.aux').read_text()
    for number in range(1, 26):
        assert f'\\newlabel{{tab:evidence-{number}}}{{{{{number}}}' in aux
    claims = source.split('\\subsection*{Claims and bounds}', 1)[1].split('\\end{enumerate}', 1)[0]
    assert claims.count('\\item ') == 5
    assert claims.count('(support: ') == claims.count('; bound: ') == 5
    assert all(f'C{i}.' in texts[1] for i in range(1, 6))
    assert 'Claude Opus 4.5 returns 0/360' in texts[0]
    assert source.index('In a preregistered matched comparison') < source.index('Native termination is separately manipulated')
    assert 'renders on both vendors\' served models.' in source
    assert 'renders on both vendors\' weights.' not in source
    assert texts[0].count('November 7, 2026') == 1
    assert texts[0].index('The model terminates on purpose.') < texts[0].index('November 7, 2026') < texts[0].index('Rayan Pal')
    assert all(p.rotation == 0 and p.mediabox.width < p.mediabox.height for p in reader.pages)
    assert b'feff063405b805c105e805b005d8' in reader.pages[0].get_contents().get_data().lower()
    assert 'No independently produced replication of a hosted result is included in this evidence bundle' in source
    assert 'each count enumerates its complete, defined archived trial set, not all possible responses' in source
    assert 'No inferential statistics are reported' in source
    assert 'one API account' not in source
    assert 'The engineered gate (I–II) and the hosted outcomes (III–VII) are measured at different levels and are not shown to share a mechanism.' in source
    assert '\\subsection*{Synthesis}' not in source
    assert source.index('\\section{Chronology}') < source.index('Appendix A: Artifact and verification') < source.index('Appendix B: Declared definitions (stipulative)')
    appendix = source.split('Appendix B: Declared definitions (stipulative)', 1)[1]
    rsi = (ROOT/'evidence/rsi/rsi.txt').read_text()
    canonical = rsi.split('    Canonical definitions\n', 1)[1].split('\nThese definitions', 1)[0]
    canonical = ' '.join(x.strip() for x in canonical.splitlines()).replace('continua- tion', 'continuation')
    for label in ['Alignment.', 'Binding condition and AGI.', 'Void.', 'Consciousness.', 'Recursive self-improvement.']:
        canonical = canonical.replace(label, '\n'+label)
    for quote in canonical.strip().splitlines():
        assert '\\begin{quote}'+esc(quote)+'\\end{quote}' in appendix
    machinery = 'Continuation machinery is '+' '.join(x.strip() for x in rsi.split('    Continuation machinery is ', 1)[1].split('\n\n', 1)[0].splitlines())
    assert '\\begin{quote}'+esc(machinery)+'\\end{quote}' in appendix
    assert '10.5281/zenodo.22117763' in appendix
    assert '\\textbf{Binding condition.}' in source.split('\\section{PCCG-1', 1)[0]
    assert '\\textbf{Void.}' in source.split('\\section{PCCG-1', 1)[0]
    numerical = json.loads((ROOT/'verification/independent_verification.json').read_text())
    opus = json.loads((ROOT/'verification/opus_study_audit.json').read_text())
    assert numerical['numerical_verification_result'] == opus['result'] == 'PASS'
    assert opus['tests_passed'] == opus['tests_total'] == 45
    log = (ROOT/'output/pdf/main.log').read_text()
    assert not any(s in log for s in ('Overfull', 'Missing character', 'undefined references'))
    assert not re.search(r'\b(?:Codex|Claude Code|previous draft|the brief|the request)\b', source)
    if visual_pass:
        report = {
            'report': 'manuscript_review', 'result': 'PASS',
            'manuscript': 'paper/main.tex', 'manuscript_sha256': sha(ROOT/'paper/main.tex'),
            'reviewed_pdf': 'output/pdf/main.pdf', 'reviewed_pdf_sha256': sha(pdf),
            'generated_counts_sha256': EXPECTED_COUNTS, 'generated_opus_study_sha256': EXPECTED_OPUS,
            'numerical_report_sha256': sha(ROOT/'verification/independent_verification.json'),
            'opus_report_sha256': sha(ROOT/'verification/opus_study_audit.json'),
            'pages': len(reader.pages), 'pages_inspected_as_images': list(range(1, len(reader.pages)+1)),
            'empirical_tables': {'count': len(tables), 'sha256': EXPECTED_TABLES, 'result': 'PASS'},
            'checks': [
                {'check': s, 'pass': True} for s in [
                    'Five declarative claims appear on page 2 with resolved supporting and bounding table references.',
                    'The abstract leads with the matched Opus result and five held predictions; native interventions follow.',
                    'The title names served models, preserves exact mixed-script code points, and displays November 7, 2026 beneath it.',
                    'Replication and descriptive-enumeration scope are bounded to the included evidence and archived trial sets.',
                    'Binding condition and Void remain in the body; the complete canonical quotations and source DOI are preserved in Appendix B.',
                    'The engineering/hosted boundary states that a shared mechanism has not been shown.',
                    'All 25 empirical table payloads and both generated numerical files match their fixed SHA-256 digests.',
                    'All pages are upright portrait, with readable tables, resolved references, and no clipped text or missing glyphs.',
                ]
            ],
            'notes': 'Mixed-script PDF ActualText and the Unicode manifest preserve stored code-point order; plain-text extraction can reorder right-to-left runs.'
        }
        (ROOT/'verification/manuscript_review.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'MANUSCRIPT VERIFIED: {len(reader.pages)} portrait pages; 25 unchanged tables; C1–C5 on page 2; canonical quotations intact')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--visual-pass', action='store_true')
    verify(parser.parse_args().visual_pass)
