from pathlib import Path

code = Path('pages/66_partnerships.py').read_text(encoding='utf-8')

# Remove the bad line entirely — beyond banking data comes from config, not random
OLD = '''    bb_rows = [{"Product":p["name"],"Icon":p["icon"],"Partner":p["partner"],
                 "Commission %":p["commission_pct"],
                 "Annual Target (KES M)":round(random.uniform(1,50),1) if True else 0}
                for p in bb_products]
    import random; random.seed(42)'''

NEW = '''    import random; random.seed(42)'''

if OLD in code:
    code = code.replace(OLD, NEW, 1)
    Path('pages/66_partnerships.py').write_text(code, encoding='utf-8')
    print('Fixed')
else:
    # Show line 440-446
    lines = code.split('\n')
    for i, l in enumerate(lines[438:448], 439):
        print(f"L{i}: {l.rstrip()}")