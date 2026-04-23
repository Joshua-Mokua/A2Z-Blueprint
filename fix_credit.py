from pathlib import Path
import re

code = Path('pages/19_credit_monitoring.py').read_text(encoding='utf-8')
lines = code.split('\n')

for i, l in enumerate(lines):
    if 'load_cm()' in l:
        print(f"L{i+1}: {l.rstrip()}")