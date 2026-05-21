"""scripts/docgen/_theme.py — shared visual theme for Living Doc generators (v8.13).

Banking theme aligned to the campaign discipline: restrained, professional,
data-driven. No decorative chart-junk. Per docs/A2Z_LIVING_DOCS_PLAN.md
Part 4, "professional restraint" not flashy marketing.

Used by ppt_generator.py + magazine_generator.py + whitepaper_generator.py
so all rendered artifacts share visual coherence.
"""
from __future__ import annotations

# ════════════════════════════════════════════════════════════════════
# Banking color palette — Ocean Gradient (deep, trustworthy, restrained)
# ════════════════════════════════════════════════════════════════════

# Primary — deep ocean blue (60-70% visual weight)
PRIMARY_HEX = "065A82"
PRIMARY_RGB = (0x06, 0x5A, 0x82)

# Secondary — teal (supporting tone)
SECONDARY_HEX = "1C7293"
SECONDARY_RGB = (0x1C, 0x72, 0x93)

# Accent — midnight (sharp accent for callouts)
ACCENT_HEX = "21295C"
ACCENT_RGB = (0x21, 0x29, 0x5C)

# Neutrals
WHITE_HEX = "FFFFFF"
WHITE_RGB = (0xFF, 0xFF, 0xFF)

CHARCOAL_HEX = "2D3748"
CHARCOAL_RGB = (0x2D, 0x37, 0x48)

LIGHT_GREY_HEX = "F7FAFC"
LIGHT_GREY_RGB = (0xF7, 0xFA, 0xFC)

MID_GREY_HEX = "A0AEC0"
MID_GREY_RGB = (0xA0, 0xAE, 0xC0)

# Status markers — match the discipline (Part 3 of the plan)
STATUS_SHIPPED_HEX = "2F855A"   # green
STATUS_SHIPPED_RGB = (0x2F, 0x85, 0x5A)

STATUS_DESIGNED_HEX = "C05621"  # orange
STATUS_DESIGNED_RGB = (0xC0, 0x56, 0x21)

STATUS_ROADMAP_HEX = "718096"   # grey
STATUS_ROADMAP_RGB = (0x71, 0x80, 0x96)


def status_marker(status: str) -> str:
    """Return the marker symbol for a status string."""
    return {
        "shipped": "✓ Shipped",
        "designed": "○ Designed",
        "roadmap": "→ Roadmap",
    }.get(status.lower(), f"? {status}")


def status_color_hex(status: str) -> str:
    """Return hex color for a status string."""
    return {
        "shipped": STATUS_SHIPPED_HEX,
        "designed": STATUS_DESIGNED_HEX,
        "roadmap": STATUS_ROADMAP_HEX,
    }.get(status.lower(), MID_GREY_HEX)


# ════════════════════════════════════════════════════════════════════
# Typography
# ════════════════════════════════════════════════════════════════════

FONT_HEADER = "Helvetica-Bold"      # reportlab built-in (PDF)
FONT_BODY = "Helvetica"             # reportlab built-in (PDF)
FONT_MONO = "Courier"               # reportlab built-in (PDF)

# PPT typography
PPT_HEADER_FONT = "Calibri"
PPT_BODY_FONT = "Calibri"
PPT_MONO_FONT = "Consolas"

SIZE_TITLE = 36
SIZE_HEADING = 22
SIZE_SUBHEADING = 16
SIZE_BODY = 11
SIZE_CAPTION = 9
SIZE_FOOTER = 8

# ════════════════════════════════════════════════════════════════════
# Structural constants
# ════════════════════════════════════════════════════════════════════

PAGE_MARGIN_INCHES = 0.75


# ════════════════════════════════════════════════════════════════════
# Shared header text used by all generators
# ════════════════════════════════════════════════════════════════════

PRODUCT_NAME = "A2Z MIS 360"
PRODUCT_TAGLINE = "Banking Management Intelligence — Audit-Locked"
COPYRIGHT_FOOTER = "© 2026 A2Z. Audit-locked content; see scripts/audit.py."
