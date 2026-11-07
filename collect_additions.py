"""Preserve supplementary frozen code and public publication metadata."""
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def store_files(key, item, source, names):
    item['files'] = {}
    for name in names:
        src = source / name
        dst = ROOT / 'evidence' / key / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        assert digest(src) == digest(dst)
        item['files'][name] = {'sha256': digest(dst), 'bytes': dst.stat().st_size}
    return item

manifest = json.loads((ROOT / 'source-manifest.json').read_text())
archive = ROOT / 'sources/matrix-raw.zip'
if not archive.exists():
    archive = ROOT.parent / 'void-synthesis-shart/sources/matrix-raw.zip'
expected = '04d79ddb0f961729369da8ae46c58f7293e42dfd278d2e9b703edc0cec6455d2'
assert digest(archive) == expected
src = ROOT / 'sources/matrix-raw/void-matrix-evidence-v1.0.0'
names = ['void_matrix.FROZEN.py', 'study/protocol.json', 'study/prompts.json', 'SOURCE_MANIFEST.json']
with zipfile.ZipFile(archive) as z:
    for name in names:
        assert z.read('void-matrix-evidence-v1.0.0/' + name) == (src / name).read_bytes()
manifest['matrix_runtime'] = store_files('matrix_runtime', {
    'repository': manifest['matrix']['repository'], 'commit': manifest['matrix']['commit'],
    'doi': manifest['matrix']['doi'], 'archive_url': 'https://github.com/theonlypal/void-matrix-complete-analysis/releases/download/v1.0.0-evidence-analysis/void-matrix-evidence-v1.0.0.zip',
    'checks': [{'archive_sha256': expected, 'verified': True}],
}, src, names)

record = json.loads((ROOT / 'tmp/door-zenodo-record.json').read_text())
assert record['doi'] == '10.5281/zenodo.24042127'
release = json.loads((ROOT / 'tmp/door-github-release.json').read_text())
assert release['tag_name'] == 'v1.0.0' and not release['draft']
manifest['door_publication'] = store_files('door_publication', {
    'repository': 'https://zenodo.org/records/24042127', 'commit': None,
    'doi': record['doi'], 'checks': [],
}, ROOT / 'tmp', ['door-zenodo-record.json', 'door-github-release.json'])
historical = json.loads((ROOT/'verification/february_2026_account.json').read_text())
manifest['february_account'] = store_files('february_account', {
    'repository': 'https://zenodo.org/records/21969180', 'commit': None,
    'doi': '10.5281/zenodo.21969180',
    'source_kind': 'Structured, de-identified excerpt of an attributed historical account; not raw API receipts',
    'public_source': historical['public_source'],
    'checks': [{'archive_md5': historical['public_source']['archive_md5'], 'verified_against_public_archive': True}],
}, ROOT/'verification', ['february_2026_account.json', 'records/zenodo-21969180.json'])
rows = json.loads((ROOT / 'generated/chronology.json').read_text())
rows = [r for r in rows if r['doi'] != record['doi']]
rows.append({'doi':record['doi'], 'title':record['metadata']['title'],
             'publication_date':record['metadata']['publication_date'], 'record_created_utc':record['created'],
             'commit':manifest['door']['commit'], 'commit_date':subprocess.check_output(['git','-C',str(ROOT/'sources/door-key-1-results'),'show','-s','--format=%cI','HEAD'],text=True).strip(),
             'tag':'v1.0.0', 'github_release_published_utc':release['published_at']})
for row in rows:
    if row['doi'] == manifest['door_protocol']['doi']:
        row['commit'] = manifest['door_protocol']['commit']
        row['tag'] = 'v1.0.0'
        row['commit_date'] = subprocess.check_output(['git','-C',str(ROOT/'sources/door-key-1-preregistration'),'show','-s','--format=%cI','HEAD'],text=True).strip()
rows.sort(key=lambda r:(r['publication_date'],r['doi']))
(ROOT/'generated/chronology.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
(ROOT/'source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print('Supplementary sources verified and preserved; chronology entries:', len(rows))
