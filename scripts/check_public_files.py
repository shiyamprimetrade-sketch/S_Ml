"""Fail if tracked runtime data or obvious credential assignments enter the repo.
Heuristic supplement, not a claim of comprehensive secret detection.
"""
import re
import subprocess
from pathlib import Path

paths = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
problems = []
for name in filter(None, paths):
    path = Path(name)
    if path.parts[0] in ('private', 'runtime') or path.suffix in ('.db', '.sqlite3', '.pem', '.key', '.pkl', '.joblib') or path.name.startswith('.env'):
        problems.append(name)
        continue
    try:
        text = path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError):
        continue
    if re.search(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)', text):
        problems.append(name)
    if re.search(r'(?i)(?:access_token|refresh_token|client_secret)\s*[:=]\s*[\"\x27][A-Za-z0-9_\-]{24,}', text):
        problems.append(name)
if problems:
    raise SystemExit('Review forbidden or sensitive tracked files: ' + ', '.join(problems))
print('Public-file guard passed; runtime/private data excluded')
