from pathlib import Path

core = Path('utils/core.py').read_text(encoding='utf-8')

# Remove the entire broken section and replace with clean version
BAD = '''    except: pass
    # ── Rolling JSON for UI (last 2000) ───────────────────────────────
    try:
        log_file = DATA_DIR / "audit_log.json"
        raw = log_file.read_text() if log_file.exists() else "[]"
        log = json.loads(raw) if raw.strip() else []
        if not isinstance(log, list): log = []
        log.append(entry)
        log_file.write_text(json.dumps(log[-2000:], indent=2))
    except: pass
except: pass
    # ── PostgreSQL audit trail ────────────────────────────────────────
    try:
        from utils.db import db as _db
        if _db.table_uses_db("audit_trail"):
            _db.execute(
                """INSERT INTO audit_trail
                   (username, action, detail, module, before_val, after_val)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (username, action, str(detail)[:500], module,
                 str(before)[:200] if before else "",
                 str(after)[:200]  if after  else "")
            )
    except: pass
    # ── Rolling JSON for UI (last 2000) ───────────────────────────────'''

GOOD = '''    except: pass
    # ── Rolling JSON for UI (last 2000) ───────────────────────────────
    try:
        log_file = DATA_DIR / "audit_log.json"
        raw = log_file.read_text() if log_file.exists() else "[]"
        log = json.loads(raw) if raw.strip() else []
        if not isinstance(log, list): log = []
        log.append(entry)
        log_file.write_text(json.dumps(log[-2000:], indent=2))
    except: pass
    # ── PostgreSQL audit trail ────────────────────────────────────────
    try:
        from utils.db import db as _db
        if _db.table_uses_db("audit_trail"):
            _db.execute(
                "INSERT INTO audit_trail (username, action, detail, module, before_val, after_val) VALUES (%s, %s, %s, %s, %s, %s)",
                (username, action, str(detail)[:500], module,
                 str(before)[:200] if before else "",
                 str(after)[:200]  if after  else "")
            )
    except: pass'''

if BAD in core:
    core = core.replace(BAD, GOOD, 1)
    Path('utils/core.py').write_text(core, encoding='utf-8')
    print('Fixed successfully')
else:
    print('Exact match not found - trying line replacement')
    lines = core.split('\n')
    # Remove line 4811 which is the bare 'except: pass'
    new_lines = []
    for i, line in enumerate(lines):
        if i == 4810 and line == 'except: pass':
            print(f'Removing bad line {i+1}: {repr(line)}')
            continue
        new_lines.append(line)
    core = '\n'.join(new_lines)
    Path('utils/core.py').write_text(core, encoding='utf-8')
    print('Removed bad line')