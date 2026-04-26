# A2Z Page UX Standards
## Tab structure, labels, and navigation conventions for all pages

> **Status:** Active convention from v5.13 onwards
> **Owner:** A2Z Platform Engineering
> **Last review:** v5.13

---

## 1. The Core Rule

**Maximum 7 tabs in a single row.** This is the comfort ceiling on a 13" laptop screen at standard zoom. Beyond 7, users start scrolling horizontally and labels start truncating.

If a page needs more than 7 tabs of content, use **2-level navigation**: top-level sections, with sub-tabs inside each section.

---

## 2. When to Restructure to 2-Level Nav

| Tab count in single row | Action |
|-------------------------|--------|
| 1-5 tabs | Flat row — fine. No restructure needed. |
| 6-7 tabs | Flat row — review labels for clarity, ensure logical order. |
| 8 tabs | Borderline — restructure if there are clean logical groups, otherwise reorder. |
| 9+ tabs | Restructure — flat row will not work on smaller screens. |

The 6 pages restructured in v5.13 (1_perform, 2_people, 4_execute, 25_treasury, 26_legal, 28_ra) all had 8-10 tabs and were the worst offenders.

---

## 3. Section Naming Convention

Top-level sections are named for **user intent**, not technical category. The reader should understand "what would I be doing in this section?" from the label alone.

Good section names:
- `📊 Overview` — at-a-glance dashboards, no actions
- `📋 Operational` — day-to-day workflow (create, update, complete)
- `📊 Reporting` — read-only views, analytics
- `🔧 Admin` — settings, configuration
- `👥 Records` — master data management
- `📈 Insights` — analytics with derived intelligence
- `🎯 Personal` — content scoped to the logged-in user

Bad section names:
- ❌ `Tab 1`, `Misc`, `Other` — meaningless
- ❌ `Reports`, `Settings`, `Data` — too generic
- ❌ `Configuration & Settings & Admin` — too long, overlapping

---

## 4. Tab Label Standards

Every tab label follows the same format:

```
{emoji} {Name in Sentence Case}
```

**Rules:**
- Always include exactly one leading emoji (consistent across the system)
- Use sentence case (`Active matters`, not `Active Matters` or `ACTIVE MATTERS`)
- Maximum 4 words or 25 characters per label
- Labels should be unique within their tab call (no two tabs called "Overview" in the same row)

**Emoji conventions:**
| Domain | Recommended emoji | Examples |
|--------|-------------------|----------|
| Overview/Dashboard | 📊 | `📊 Overview`, `📊 Dashboard` |
| Records/Lists | 📋 | `📋 Active matters`, `📋 Initiatives` |
| Settings/Config | ⚙️ 🔧 | `⚙️ Thresholds`, `🔧 Admin` |
| Analytics/Insights | 📈 💡 | `📈 Trends`, `💡 Insights` |
| People | 👤 👥 | `👤 Users`, `👥 Records` |
| Time/Schedule | 📅 🏖️ | `📅 Calendar`, `🏖️ Leave` |
| Money | 💰 💵 | `💰 Revenue`, `💵 Pricing` |
| Risk/Alert | ⚠️ 🚨 🔴 | `⚠️ Warnings`, `🚨 Escalations` |
| Comparison | 🔢 🏆 | `🔢 Matrix`, `🏆 Rankings` |
| Personal | 🎯 ✨ | `🎯 My milestones`, `✨ My BSC` |

The emoji should match the **content type**, not be decorative. A "📊 Reports" tab and a "📋 Reports" tab signal different things — a chart-heavy view vs a list view.

---

## 5. Sub-Tab Structure

Inside a top-level section, sub-tabs are written using `sub` as the variable name:

```python
with sections[0]:                       # 📊 Overview section
    sub = st.tabs([
        "📊 Today",
        "📈 Trends",
        "🎯 KPIs",
    ])
    with sub[0]:
        # ...
```

Sub-tabs follow the same labeling rules as top-level sections. Maximum 5 sub-tabs per section is the comfort target. If a section needs 6+ sub-tabs, that section is doing too much — consider splitting it.

---

## 6. Tab Order Within a Group

The order of tabs is not arbitrary. It follows user reading order:

1. **First** — overview/at-a-glance (the page you arrive at)
2. **Second** — main operational view (what users do most)
3. **Third onwards** — supporting views (deeper detail, search, filter)
4. **Last** — admin/settings (rarely accessed)

A tab labeled "Settings" should never be in position [0]. A tab labeled "Overview" should never be in position [3].

---

## 7. Anti-Patterns

❌ **Don't add a 7th tab to an already-full row.** If the page has 7 tabs and you have new content, redesign to 2-level nav.

❌ **Don't mix emoji conventions within one page.** If you started with 📊 for analytics, don't switch to 📈 mid-way.

❌ **Don't use multi-word labels with `&`.** `📊 Risk & Compliance` is borderline; `📊 Risk & Compliance & Audit` is too long. Pick the strongest noun and let the section name carry the rest.

❌ **Don't put module-specific configs at the page level.** They go in Admin → Module Config Centre via the registry pattern (see `docs/ADMIN_CONVENTIONS.md`).

❌ **Don't restructure a page that has 5-7 tabs and works.** Restructuring has a cost (regression risk, code change). Only do it when justified.

---

## 8. Migration Status (v5.13)

These 6 pages have been restructured to 2-level navigation:

| Page | Before | After | Sections |
|------|--------|-------|----------|
| `1_perform.py` | 8 tabs flat | 3 sections × 8 sub-tabs | 👤 My BSC · 🏆 Org-wide · 📋 Admin/HR |
| `2_people.py` | 10 tabs flat | 4 sections × 10 sub-tabs | 📊 Insights · 👥 Records · 🏖️ Leave · 📋 Discipline & Dev |
| `4_execute.py` | 9 tabs flat | 4 sections × 9 sub-tabs | 📊 Discover · ➕ Create · 📈 Track · 🎯 Personal |
| `25_treasury.py` | 8 tabs flat | 3 sections × 7 sub-tabs | 📊 Overview · 💼 Products · ⚖️ Risk & Control |
| `26_legal.py` | 8 tabs flat | 3 sections × 8 sub-tabs | 📋 Operational · 📊 Reporting · 🔧 Admin |
| `28_ra.py` | 9 tabs flat | 4 sections × 8 sub-tabs | 🏛️ Executive · 📊 Performance · ⚙️ Operational · 💸 Sales |

Plus from v5.12: `7_admin.py` was the largest restructure (31 tabs → 6 sections × 21 sub-tabs).

---

## 9. Pages Reviewed and Left Alone

These pages have 7 tabs but the labels are well-organised and the workflow benefits from a flat row (no sub-categorisation justified):

- `13_sla.py` — 7 tabs, status-tracker style, flat works
- `18_cims.py` — 7 tabs, ticket lifecycle, flat works  
- `19_credit_monitoring.py` — 7 tabs, classification-based, flat works
- `32_ifrs9.py` — 7 tabs, accounting workflow, flat works
- `66_partnerships.py` — 7 tabs (but multi-call with sub-tabs already)
- `68_clearing.py`, `69_consent.py`, `74_cbk_returns.py` — 7 tabs each, regulatory workflow

If any of these grows to 8+ tabs, restructure them per the rules above.

---

## 10. How to Apply This Standard to a New Page

When creating a new module page:

1. **Plan the user journey first.** What's the FIRST thing they need to see? The SECOND? The LAST?
2. **Sketch tab labels.** If you have 5 or fewer, you're done — flat row.
3. **If 6-7, review for redundancy.** Can two tabs be merged?
4. **If 8+, group by user intent into 2-4 logical sections.** Each section should have a single-word or two-word label.
5. **Apply emoji conventions** from Section 4.
6. **Verify the FIRST tab is overview/dashboard**, the LAST is admin/rarely-used.

Test: imagine a new user opening the page for the first time. Can they find what they need within 3 seconds?

---

*Standards version 1.0 (v5.13). Update when patterns change.*
