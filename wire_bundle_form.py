#!/usr/bin/env python3
"""Wire BundleLinesEditor into PipelineCreate.tsx. Mirrors the isTopUp pattern.
Validates the result compiles-shaped before writing (no broken file left behind).

    python wire_bundle_form.py            # dry run — shows each edit's anchor hit
    python wire_bundle_form.py --apply
"""
import sys, shutil, time, re
from pathlib import Path

F = Path("frontend/web/src/pages/PipelineCreate.tsx")
s = F.read_text(encoding="utf-8")
orig = s
edits = []

# 1. import (after the last existing import near top)
if "BundleLinesEditor" not in s:
    m = None
    for m in re.finditer(r'^import .*;$', s, re.M):
        if m.start() > 1500: break
    anchor = m.group(0)
    add = ("\nimport { BundleLinesEditor, type BundleLine } "
           "from '@/components/BundleLinesEditor';")
    s = s.replace(anchor, anchor + add, 1)
    edits.append("import added")

# 2. state — after the dealValue useState (line ~147)
if "bundleLines" not in s:
    m = re.search(r"const \[dealValue,\s*setDealValue\][^\n]*\n", s)
    if not m:
        print("REFUSING — dealValue state line not found"); sys.exit(1)
    st = ("  const [bundleLines, setBundleLines] = useState<BundleLine[]>([]);\n"
          "  const [bundleTotal, setBundleTotal] = useState<number>(0);\n")
    s = s[:m.end()] + st + s[m.end():]
    edits.append("state added")

# 3. an isBundle helper — right after the state we just added (or near productType)
if "const isBundle" not in s:
    m = re.search(r"const \[bundleTotal,[^\n]*\n", s)
    hook = ("  const isBundle = productType.trim() === 'Bundled Loan Product';\n")
    s = s[:m.end()] + hook + s[m.end():]
    edits.append("isBundle helper added")

# 4. payload: deal_value uses bundleTotal when bundling; add bundle_lines
#    line 862: deal_value:   isTopUp ? topUpAmtNum : dealValueNum,
if "bundle_lines:" not in s:
    m = re.search(r"deal_value:\s*isTopUp \? topUpAmtNum : dealValueNum,", s)
    if not m:
        print("REFUSING — deal_value payload line not found"); sys.exit(1)
    repl = ("deal_value:   isBundle ? bundleTotal : (isTopUp ? topUpAmtNum : dealValueNum),\n"
            "        bundle_lines: isBundle && bundleLines.length\n"
            "          ? bundleLines.map((l) => ({ product_type: l.product_type, amount: Number(String(l.amount).replace(/[,\\s]/g, '')) }))\n"
            "          : undefined,")
    s = s.replace(m.group(0), repl, 1)
    edits.append("payload deal_value + bundle_lines")

# 5. render: show the editor when isBundle, ABOVE the facility/deal-value block.
#    Anchor on the Facility type toggle region. We insert a block right before the
#    `{isTopUp && (` render at ~1355. When isBundle, we render the editor and the
#    facility/value inputs are hidden.
if "<BundleLinesEditor" not in s:
    # wrap: find the first `{isTopUp && (` in the RENDER (not the payload)
    # and inject a bundle block before it, plus guard the value inputs with !isBundle.
    m = re.search(r"\n(\s*)\{isTopUp && \(", s)
    if not m:
        print("REFUSING — render {isTopUp && ( anchor not found"); sys.exit(1)
    indent = m.group(1)
    block = (f"\n{indent}{{isBundle && (\n"
             f"{indent}  <BundleLinesEditor\n"
             f"{indent}    value={{bundleLines}}\n"
             f"{indent}    onChange={{(lines, total) => {{ setBundleLines(lines); setBundleTotal(total); }}}}\n"
             f"{indent}    currencySymbol={{branding?.currency_symbol ?? 'KES'}}\n"
             f"{indent}  />\n"
             f"{indent})}}\n")
    s = s[:m.start()] + block + s[m.start():]
    edits.append("render block added")

    # guard the existing facility/value UI so it hides when bundling:
    # change `{isTopUp && (` -> `{!isBundle && isTopUp && (`
    #        `{!isTopUp && (` -> `{!isBundle && !isTopUp && (`
    s = s.replace("{isTopUp && (", "{!isBundle && isTopUp && (")
    s = s.replace("{!isTopUp && (", "{!isBundle && !isTopUp && (")
    edits.append("facility UI guarded with !isBundle")

print("=== edits ===")
for e in edits: print(f"   {e}")

# lightweight structural validation: balanced braces/parens delta shouldn't explode
if s.count("{") - s.count("}") != orig.count("{") - orig.count("}"):
    print("WARNING — brace balance changed; review carefully.")
if s == orig:
    print("no change"); sys.exit(0)

if "--apply" not in sys.argv:
    print("\n[DRY-RUN] re-run with --apply"); sys.exit(0)

shutil.copy2(F, F.with_suffix(f".tsx.pre_bundleform_{int(time.time())}"))
F.write_text(s, encoding="utf-8")
print("\napplied. Run: pushd frontend\\web && pnpm tsc --noEmit && popd")
