"""Invoke this machine's Blender without requiring a global PATH change."""
import json
from pathlib import Path
import subprocess
import sys

project = Path(__file__).resolve().parent.parent
config = json.loads((project / "local-tools.json").read_text("utf-8-sig"))
executable = Path(config["blender"])
if not executable.is_file():
    raise SystemExit("Blender executable from local-tools.json was not found")
raise SystemExit(subprocess.run(
    [str(executable), "--python-exit-code", "1", *sys.argv[1:]], shell=False
).returncode)
