from pathlib import Path

core = Path('utils/core.py').read_text(encoding='utf-8')
lines = core.split('\n')

# Show lines around 4811
start = max(0, 4805)
end   = min(len(lines), 4820)
for i, l in enumerate(lines[start:end], start+1):
    print(f"L{i}: {repr(l)}")