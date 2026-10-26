"""Reconstruct reviewed source at a fixed commit, verify SHA256, install into isolated venv."""
import sys,json,hashlib,subprocess
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
m=json.loads((ROOT/'reports/community_source_manifest.json').read_text())
dest=ROOT/'.research-vendor/aviasales-mcp';dest.mkdir(parents=True,exist_ok=True)
with httpx.Client(timeout=30,follow_redirects=False) as c:
 for name,digest in m['files'].items():
  path=dest/name
  if not path.resolve().is_relative_to(dest.resolve()):raise ValueError('Unsafe source path')
  if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==digest:continue
  r=c.get(f"https://raw.githubusercontent.com/{m['repository']}/{m['commit']}/{name}");r.raise_for_status()
  if hashlib.sha256(r.content).hexdigest()!=digest:raise ValueError('Source hash mismatch')
  path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(r.content)
subprocess.run([sys.executable,'-m','venv',str(ROOT/'.mcp-venv')],check=True)
exe=str(ROOT/'.mcp-venv/bin/python')
subprocess.run([exe,'-m','pip','install','-r',str(ROOT/'requirements.community.lock.txt')],check=True)
subprocess.run([exe,'-m','pip','install','--no-deps',str(dest)],check=True)
print('Reviewed community source installed at pinned commit')
