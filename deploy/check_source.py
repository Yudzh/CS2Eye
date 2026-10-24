"""Compare application sources with a release manifest; never inspect secrets."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
manifest = json.loads((root / "deploy/source-manifest.json").read_text())
changed = []
missing = []
for relative, expected in manifest.items():
    path = root / relative
    if not path.is_file():
        missing.append(relative)
    elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        changed.append(relative)
print(f"Checked {len(manifest)} source files")
print(f"Different: {len(changed)}; missing: {len(missing)}")
for relative in changed:
    print("DIFFERENT", relative)
for relative in missing:
    print("MISSING", relative)
print("Secrets, database, uploaded demos and generated files are excluded.")
raise SystemExit(bool(changed or missing))
