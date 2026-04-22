from pathlib import Path

core = Path('utils/core.py').read_text(encoding='utf-8')

# Remove the incorrectly inserted block if it exists
bad_block = '''    # ── PostgreSQL audit trail ─────────────────────────────────────
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

if bad_block in core:
    core = core.replace(bad_block, '', 1)
    Path('utils/core.py').write_text(core, encoding='utf-8')
    print('Removed bad block - file restored')
else:
    print('Block not found - file may already be clean')