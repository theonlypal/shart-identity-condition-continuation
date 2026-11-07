"""Hash the complete non-ignored distribution, excluding the manifest itself."""
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
paths = subprocess.check_output(
    ['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
    cwd=ROOT,
).decode().split('\0')
lines = []
for name in sorted(set(paths) - {'', 'SHA256SUMS'}):
    path = ROOT / name
    assert path.is_file() and not path.is_symlink(), name
    assert '\n' not in name and '\r' not in name, name
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    lines.append(f'{digest}  {name}')
(ROOT / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')
print(f'SHA256SUMS: {len(lines)} files')
