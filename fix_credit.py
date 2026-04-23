from pathlib import Path

code = Path('pages/19_credit_monitoring.py').read_text(encoding='utf-8')

OLD1 = '''    region_filt = fc3.selectbox("Region",
        ["All"] + sorted(df["region"].dropna().unique().tolist()), key="cm_reg")'''

NEW1 = '''    _regions = sorted(df["region"].dropna().unique().tolist()) if "region" in df.columns else []
    region_filt = fc3.selectbox("Region",
        ["All"] + _regions, key="cm_reg")'''

OLD2 = '    if region_filt!= "All": mask &= df["region"]==region_filt'
NEW2 = '    if region_filt!= "All" and "region" in df.columns: mask &= df["region"]==region_filt'

if OLD1 in code:
    code = code.replace(OLD1, NEW1, 1)
    print('Fixed region filter')
else:
    print('Region filter not found')

if OLD2 in code:
    code = code.replace(OLD2, NEW2, 1)
    print('Fixed region mask')
else:
    print('Region mask not found')

Path('pages/19_credit_monitoring.py').write_text(code, encoding='utf-8')
print('Done')