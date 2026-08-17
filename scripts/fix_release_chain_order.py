import io, re
p='scripts/build_alex_release.py'
s=io.open(p,encoding='utf-8').read()

# The 14 new patchers, in the order proven against alex-dev.
ORDER = ["patch_cq1_committee_queue",
         "patch_cm1_committee_can_view",
         "patch_dq1_committee_queue_source",
         "patch_qf1_committee_queue_stage",
         "patch_vt1_member_voting",
         "patch_ch1_chair_mandatory",
         "patch_fn1_funnel_follows_selection",
         "patch_fp1_funnel_polish",
         "patch_hd1_cards_follow_selection",
         "patch_vu2_api_client_anchored",
         "patch_vu1_voting_panel",
         "patch_hk1_hooks_before_return",
         "patch_rt1_review_route",
         "patch_cv1_voting_bench"]

# Remove any of them already in CHAIN, so the order below is the only one.
for x in ORDER:
    s = re.sub(r'\n\s*"%s",' % re.escape(x), '', s)

m = re.search(r'\n(\s*)"patch_md1_deal_field_mapping",', s)
if not m:
    m = re.search(r'\n(\s*)"patch_br1_a2z_and_committee_tab",', s)
assert m, "no anchor to insert after"
ind = m.group(1)
block = "".join('\n%s"%s",' % (ind, x) for x in ORDER)
s = s[:m.end()] + block + s[m.end():]
io.open(p,'w',encoding='utf-8',newline='').write(s)
print("chain rebuilt with the proven order")
