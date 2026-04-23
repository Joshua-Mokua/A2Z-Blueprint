from pathlib import Path
import re

code = Path('pages/19_credit_monitoring.py').read_text(encoding='utf-8')

# Find all column references in the page
cols = re.findall(r'df\["(\w+)"\]|df\[\'(\w+)\'\]|\["(\w+)".*?not in index', code)
all_cols = sorted(set(c for group in cols for c in group if c))
print("Columns used in credit_monitoring page:")
for c in all_cols:
    print(f"  {c}")