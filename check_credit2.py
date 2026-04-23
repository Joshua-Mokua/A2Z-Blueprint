import json
from pathlib import Path

data = json.loads((Path('data') / 'credit_monitoring.json').read_text(encoding='utf-8'))
accounts = data if isinstance(data, list) else data.get('watchlist', data.get('accounts', []))

if accounts:
    print(f"Total accounts: {len(accounts)}")
    print(f"\nAll fields in first record:")
    for k, v in accounts[0].items():
        print(f"  {k:<30} {type(v).__name__:<10} {str(v)[:40]}")