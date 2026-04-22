from pathlib import Path

code = Path('pages/39_ews.py').read_text(encoding='utf-8')

if 'from collections import defaultdict' not in code:
    code = 'from collections import defaultdict\n' + code
    Path('pages/39_ews.py').write_text(code, encoding='utf-8')
    print('Fixed - defaultdict import added')
else:
    print('Import already there - checking issue')