"""Collect immutable source files and verify original checksum manifests."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / 'sources'
SPECS = {
 'pccg1': ('PCCG-Qwen3-4B-continuation-control', 'd08b157ac9273974b75d7ada2a894a1afe86e3f2', '22681787'),
 'pccg2': ('pccg2', 'a3b952458a46b5547ba3cec7d03a37b395bed03a', '22730710'),
 'matrix': ('void-matrix-complete-analysis', '3fd330869c1a4a410047bc70b3f661f1a9d69aca', '21696066'),
 'ablation': ('alignment-is-a-system-property', '7fe765a059bdd9951c3d6f80ee7b6560299ff741', '23585146'),
 'ab': ('gpt35-gpt4-void-ab', 'd77b4a64b8a3fdff06a27d80c1514531143e382b', '22912683'),
 'reassign': ('gpt-5.4-shrt-prerequisite-reassignment-analysis', 'eb8e39e070c3f4e2b00c5288efe008e2d737b4c3', '22983298'),
 'replay': ('gpt4-0613-void-replay-results', 'ce347d80dba44f289e38f61214906b2f09180471', '23521616'),
 'cross': ('gpt-5.4-shrt-cross-script-evidence','76442445abc39d7b4224ad89d4ae5fa5dafc0e39','21799525'),
 'opus': ('opus45-opus46-matched-results','582d3a781510697916498f0189ed22f7d3e9e2b6','23751813'),
 'door': ('door-key-1-results','542fc5c5e5ab28122351a5cc4e46eddc0d57bfc4','24042127'),
 'door_protocol': ('door-key-1-preregistration','986e384775e22f8fbf7e5a1fe64f43519ea9e091','23968364'),
}

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def verify_manifest(root, path):
    checked = []
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith('#'): continue
        expected, name = line.split(None, 1)
        name = name.strip().lstrip('*')
        file = root / name
        if not file.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'Unsafe manifest path: {name}')
        actual = sha(file)
        if actual != expected: raise ValueError(f'Hash mismatch: {file}')
        checked.append(name)
    return {'manifest': str(path.relative_to(root)), 'sha256': sha(path), 'verified_files': len(checked)}

def main():
    manifest_path=ROOT/'source-manifest.json'
    inventory = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for key, (repo, commit, doi) in SPECS.items():
        if len(sys.argv)>1 and key not in sys.argv[1:]: continue
        root = SOURCES / repo
        actual = subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        assert actual == commit, (key,actual,commit)
        remote = subprocess.check_output(['git','-C',str(root),'remote','get-url','origin'],text=True).strip().removesuffix('.git')
        item = {'repository':remote, 'commit':commit, 'doi':'10.5281/zenodo.'+doi, 'checks':[], 'files':{}}
        for name in ('SHA256SUMS','SHA256SUMS.txt'):
            if (root/name).exists(): item['checks'].append(verify_manifest(root,root/name))
        if key == 'ablation': item['checks'].append(verify_manifest(root/'generated',root/'generated/SHA256SUMS'))
        if key == 'reassign':
            manifest = json.loads((root/'evidence/hash_manifest.json').read_text())
            for name, expected in manifest['files'].items(): assert sha(root/name)==expected, name
            item['checks'].append({'manifest':'evidence/hash_manifest.json','sha256':sha(root/'evidence/hash_manifest.json'),'verified_files':len(manifest['files'])})
        if key=='opus': item['checks'].append(verify_manifest(root,root/'opus45-opus46-matched-prereg-final-runs.SHA256SUMS'))
        if key == 'pccg1':
            keep = list(root.glob('results/confirmation-*.json')) + [root/p for p in ('protocol/data/causal-final.json','protocol/config.json','results/direction.json','results/intervention-frozen.json','METHOD.md','verify.py','SHA256SUMS')]
        elif key == 'pccg2':
            keep = list(root.glob('evidence/records/*.json')) + list(root.glob('evidence/witness/*/*.bin')) + [root/p for p in ('evidence/witness-2plus2.json','evidence/witness-non-eos-vector.sha256','evidence/bank.json','config.json','src/model.py','src/audit.py','src/verify.py','SHA256SUMS')]
        elif key == 'matrix':
            keep = [root/p for p in ('analysis/tables/trial_level.csv','protocol/prompts.py','protocol/prompts.md','analysis/reproduce_all.py','SHA256SUMS.txt')]
        elif key == 'ablation': keep = [root/p for p in ('tables.py','PROVENANCE.md','generated/populations.json','generated/prompt_hashes.json')]
        elif key in ('ab','replay'): keep = list(root.glob('records/**/*'))+[root/p for p in ('protocol.json','FREEZE.json','verify.py','run.py','events.jsonl','SHA256SUMS.txt')]
        elif key=='cross': keep=list(root.glob('evidence/study/run/attempts/*.json'))+[root/p for p in ('evidence/study/schedule.jsonl','linguistic_validation.md','SHA256SUMS')]
        elif key=='opus': keep=[f for exp in ('exp1','exp2','exp3') for f in root.glob(exp+'/attempts/**/*')]+[f for exp in ('exp1','exp2','exp3') for f in root.glob(exp+'/definitive/*.json')]+[root/p for p in ('opus45-opus46-matched-prereg-final-runs.SHA256SUMS','opus45-opus46-matched-prereg-final-runs.seal.json')]
        elif key in ('door','door_protocol'):
            keep=[root/name for name in subprocess.check_output(['git','-C',str(root),'ls-files'],text=True).splitlines()]
            if key=='door': item['checks'].append(verify_manifest(root/'run',root/'run/SHA256SUMS'))
        else: keep = list(root.glob('raw/attempts/**/*'))+list(root.glob('raw/definitive/*.json'))+[root/p for p in ('evidence/protocol.json','evidence/prompts.json','evidence/hash_manifest.json','independent_verifier.py')]
        for file in keep:
            if not file.is_file(): continue
            rel = file.relative_to(root)
            dest = ROOT/'evidence'/key/rel
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(file,dest)
            assert sha(dest)==sha(file)
            item['files'][str(rel)]={'sha256':sha(dest),'bytes':dest.stat().st_size}
        inventory[key]=item
        print(key, 'source checks',item['checks'], 'collected',len(item['files']),flush=True)
    (ROOT/'source-manifest.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__': main()
