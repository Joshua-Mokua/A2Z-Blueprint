from pathlib import Path

code = Path('pages/3_pipeline.py').read_text(encoding='utf-8')

# Fix: replace 'for d in pipe:' with 'for d in all_deals:'
if 'for d in pipe:' in code:
    code = code.replace('for d in pipe:', 'for d in all_deals:', 1)
    Path('pages/3_pipeline.py').write_text(code, encoding='utf-8')
    print('Fixed - pipe replaced with all_deals')
else:
    print('Not found')