#!/usr/bin/env python
# One-off: when OPENROUTER_API_KEY is the only configured AI key and
# OPENROUTER_AUTO_FALLBACK=true, OpenAI/Anthropic/Google model ids are sent
# to OpenRouter's chat/completions endpoint instead of raising a missing-key
# error. See backend/test_openrouter_auto_fallback.py.
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
script = ROOT / "backend" / "test_openrouter_auto_fallback.py"
proc = subprocess.run([sys.executable, str(script)], cwd=ROOT, text=True)
sys.exit(proc.returncode)
