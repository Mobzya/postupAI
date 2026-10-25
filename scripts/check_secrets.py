"""Scan tracked content; report paths only, never matched credential values."""
import re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PATTERNS=[rb'gh[pousr]_[A-Za-z0-9]{30,}',rb'github_pat_[A-Za-z0-9_]{40,}',rb'\b[0-9]{8,12}:[A-Za-z0-9_-]{30,}\b']


def main():
    paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).split(b'\0');bad=[]
    for raw in filter(None,paths):
        relative=raw.decode();p=ROOT/relative
        if not p.is_file():continue
        forbidden=(p.name.startswith('.dev.vars') and p.name!='.dev.vars.example') or (p.name.startswith('.env') and p.name!='.env.example')
        if forbidden or any(re.search(pattern,p.read_bytes()) for pattern in PATTERNS):bad.append(relative)
    if bad:
        print('Credential check failed (paths only):',', '.join(bad));return 1
    print('PASS tracked-file credential scan (limited known token formats).');return 0


if __name__=='__main__':sys.exit(main())
