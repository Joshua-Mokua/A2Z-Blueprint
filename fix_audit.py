from pathlib import Path

core = Path('utils/core.py').read_text(encoding='utf-8')

idx = core.find('Rolling JSON for UI')
if idx < 0:
    print('Could not find Rolling JSON for UI in core.py')
else:
    # Find the 'except: pass' just before it
    before_idx = core.rfind('except: pass', 0, idx)
    if before_idx < 0:
        print('Could not find except: pass before Rolling JSON')
    else:
        # Get the exact text between except: pass and Rolling JSON
        snippet = core[before_idx:idx]
        print('Found snippet:')
        print(repr(snippet))
        
        insert_point = before_idx + len('    except: pass\n')
        pg_block = '''    # ── PostgreSQL audit trail ─────────────────────────────────────
    try:
        from utils.db import db as _db
        if _db.table_uses_db("audit_trail"):
            _db.execute(
                "INSERT INTO audit_trail (username, action, detail, module, before_val, after_val) VALUES (%s, %s, %s, %s, %s, %s)",
                (username, action, str(detail)[:500], module,
                 str(before)[:200] if before else "",
                 str(after)[:200]  if after  else "")
            )
    except: pass
'''
        new_core = core[:insert_point] + pg_block + core[insert_point:]
        Path('utils/core.py').write_text(new_core, encoding='utf-8')
        print('Done - PostgreSQL audit trail block inserted successfully')