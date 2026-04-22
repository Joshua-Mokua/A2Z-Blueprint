from pathlib import Path

core = Path('utils/core.py').read_text(encoding='utf-8')
lines = core.split('\n')

# Show more context - find the bad except
for i, l in enumerate(lines[4795:4830], 4796):
    print(f"L{i}: {repr(l)}")