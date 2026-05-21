"""scripts/docgen/whitepaper_generator.py — Security + Compliance whitepapers (v8.13).

Per docs/A2Z_LIVING_DOCS_PLAN.md Part 4, produces:
    A2Z_MIS_360_Security_Whitepaper.pdf — for CISO
    A2Z_MIS_360_Compliance_Pack.pdf — for regulator

Both are PDF; share the magazine's layout style; use the security_architecture
+ integrations_roadmap sales-content JSONs as primary sources.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
)

from scripts.docgen._registry_loader import load_registry
from scripts.docgen._claim_validator import Claim, validate_claims
from scripts.docgen._honest_section import (
    collect_honest_scope_lines, standard_disclaimer_paragraph, section_title,
)
from scripts.docgen import _theme as theme


def _build_styles():
    base = getSampleStyleSheet()
    primary = HexColor("#" + theme.PRIMARY_HEX)
    accent = HexColor("#" + theme.ACCENT_HEX)
    charcoal = HexColor("#" + theme.CHARCOAL_HEX)
    return {
        "title": ParagraphStyle(
            "Title", parent=base["Title"],
            fontName=theme.FONT_HEADER, fontSize=32, leading=38,
            textColor=primary, alignment=TA_LEFT, spaceAfter=18),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"],
            fontName=theme.FONT_BODY, fontSize=14, leading=18,
            textColor=charcoal, alignment=TA_LEFT, spaceAfter=18),
        "h1": ParagraphStyle(
            "H1", parent=base["Heading1"],
            fontName=theme.FONT_HEADER, fontSize=20, leading=26,
            textColor=primary, alignment=TA_LEFT, spaceBefore=18, spaceAfter=10),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"],
            fontName=theme.FONT_HEADER, fontSize=14, leading=18,
            textColor=accent, alignment=TA_LEFT, spaceBefore=12, spaceAfter=8),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"],
            fontName=theme.FONT_BODY, fontSize=10, leading=14,
            textColor=charcoal, alignment=TA_JUSTIFY, spaceAfter=8),
        "callout": ParagraphStyle(
            "Callout", parent=base["Normal"],
            fontName=theme.FONT_BODY, fontSize=10, leading=14,
            textColor=charcoal, alignment=TA_LEFT, spaceAfter=4,
            leftIndent=12),
        "honest_intro": ParagraphStyle(
            "HonestIntro", parent=base["Normal"],
            fontName=theme.FONT_BODY, fontSize=10, leading=14,
            textColor=charcoal, alignment=TA_JUSTIFY, spaceAfter=10,
            backColor=HexColor("#FFF5E6"),
            borderPadding=10),
        "footer_caption": ParagraphStyle(
            "FooterCaption", parent=base["Normal"],
            fontName=theme.FONT_BODY, fontSize=8, leading=10,
            textColor=HexColor("#" + theme.MID_GREY_HEX), alignment=TA_LEFT),
    }


def _make_footer_callback(reg: Dict[str, Any], doc_label: str):
    """Footer with audit credentials + page no."""
    version = reg["platform"]["version"]
    audit_gates = reg["platform"]["audit_gates"]

    def _draw(canvas, doc):
        canvas.saveState()
        canvas.setFont(theme.FONT_BODY, 8)
        canvas.setFillColor(HexColor("#" + theme.MID_GREY_HEX))
        canvas.drawString(
            doc.leftMargin, 0.5 * inch,
            f"{theme.PRODUCT_NAME} · {doc_label} · {version} · {audit_gates} gates")
        canvas.drawRightString(
            doc.pagesize[0] - doc.rightMargin, 0.5 * inch,
            f"Page {canvas.getPageNumber()}")
        canvas.restoreState()
    return _draw


def _shipped_box(label: str, status: str, body: str, styles) -> List:
    """A status-tagged feature box."""
    marker = theme.status_marker(status)
    color = theme.status_color_hex(status)
    return [
        Paragraph(
            f"<font color='#{color}'><b>{marker}</b></font>  "
            f"<b>{label}</b>",
            styles["callout"]),
        Paragraph(body, styles["callout"]),
        Spacer(1, 0.05 * inch),
    ]


def _build_status_table(items: List[tuple], styles, title: str = "") -> List:
    """Build a multi-row status table from (name, status, notes) tuples."""
    flow: List = []
    if title:
        flow.append(Paragraph(title, styles["h2"]))

    data = [["Feature", "Status", "Notes"]]
    for name, status, notes in items:
        marker = theme.status_marker(status)
        data.append([name, marker, notes[:60] if len(notes) > 60 else notes])

    t = Table(data, colWidths=[2.0 * inch, 1.0 * inch, 3.5 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#" + theme.PRIMARY_HEX)),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), theme.FONT_HEADER),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [white, HexColor("#" + theme.LIGHT_GREY_HEX)]),
        ("GRID", (0, 0), (-1, -1), 0.25, HexColor("#" + theme.MID_GREY_HEX)),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    flow.append(t)
    flow.append(Spacer(1, 0.15 * inch))
    return flow


# ════════════════════════════════════════════════════════════════════
# Security whitepaper
# ════════════════════════════════════════════════════════════════════

def _build_security_whitepaper(reg: Dict[str, Any], styles) -> List:
    sec = reg["sales_content"].get("security_architecture", {})
    if "_error" in sec:
        return [Paragraph(f"Security content unavailable: {sec['_error']}",
                          styles["body"])]

    flow: List = []

    # Cover
    flow.append(Spacer(1, 0.3 * inch))
    flow.append(Paragraph(theme.PRODUCT_NAME, styles["title"]))
    flow.append(Paragraph("Security Architecture Whitepaper", styles["subtitle"]))
    flow.append(Spacer(1, 0.3 * inch))
    flow.append(Paragraph(
        f"Version {reg['platform']['version']} · "
        f"{reg['platform']['audit_gates']} audit gates · "
        f"For CISO + security review",
        styles["footer_caption"]))
    flow.append(PageBreak())

    flow.append(Paragraph("1. Authentication + Authorization", styles["h1"]))
    auth = sec.get("authentication", {})
    flow.extend(_shipped_box(
        f"Primary method: {auth.get('primary_method', 'unknown')}",
        auth.get("primary_status", "shipped"),
        f"Source: {auth.get('primary_source', 'unknown')}",
        styles))
    mfa = auth.get("mfa_support", {}).get("totp", {})
    flow.extend(_shipped_box(
        "TOTP MFA",
        mfa.get("status", "designed"),
        mfa.get("notes", ""),
        styles))
    sso = auth.get("sso", {})
    for ssotype in ("saml_2_0", "oidc"):
        d = sso.get(ssotype, {})
        flow.extend(_shipped_box(
            f"SSO {ssotype.upper().replace('_', ' ')}",
            d.get("status", "roadmap"),
            d.get("notes", ""),
            styles))

    rbac = sec.get("authorization", {}).get("rbac", {})
    flow.extend(_shipped_box(
        "RBAC (role-based access control)",
        rbac.get("status", "shipped"),
        f"Default roles: {rbac.get('default_roles_count', '?')}; "
        f"granularity: {rbac.get('granularity', 'unknown')}",
        styles))
    flow.append(PageBreak())

    flow.append(Paragraph("2. Encryption + Audit Trail", styles["h1"]))
    enc = sec.get("encryption", {})
    flow.extend(_shipped_box(
        f"At rest: {enc.get('at_rest', {}).get('method', 'unknown')}",
        enc.get("at_rest", {}).get("status", "designed"),
        enc.get("at_rest", {}).get("notes", ""),
        styles))
    flow.extend(_shipped_box(
        f"In transit: {enc.get('in_transit', {}).get('method', 'unknown')}",
        enc.get("in_transit", {}).get("status", "designed"),
        enc.get("in_transit", {}).get("notes", ""),
        styles))

    audit_trail = sec.get("audit_trail", {})
    flow.extend(_shipped_box(
        "Audit trail",
        audit_trail.get("status", "shipped"),
        f"{audit_trail.get('implementation', 'unknown')}; "
        f"retention: {audit_trail.get('retention_default', 'unknown')}",
        styles))
    flow.append(PageBreak())

    flow.append(Paragraph("3. Operations Resilience", styles["h1"]))
    flow.append(Paragraph(
        "Per CBK Operations Resilience Guidelines (2019). Locked by audit gate G108.",
        styles["body"]))
    ops = sec.get("operations_resilience", {})
    for key in ("retry", "circuit_breaker", "latency_telemetry"):
        d = ops.get(key, {})
        cfg = d.get("config", {})
        cfg_str = "; ".join(f"{k}: {v}" for k, v in cfg.items())[:80]
        flow.extend(_shipped_box(
            key.replace("_", " ").title(),
            d.get("status", "shipped"),
            f"Shipped {d.get('version_introduced', '?')}; {cfg_str}",
            styles))

    obs = ops.get("observability_triangle", {})
    flow.extend(_shipped_box(
        "Observability triangle (mode + circuit + latency)",
        obs.get("status", "shipped"),
        " | ".join(obs.get("operator_questions_answered", [])),
        styles))
    flow.append(PageBreak())

    flow.append(Paragraph("4. Compliance Posture", styles["h1"]))
    comp = sec.get("compliance", {})
    items: List[tuple] = []
    for key, val in comp.items():
        if isinstance(val, dict):
            label = key.replace("_", " ").upper()
            items.append((label, val.get("status", "designed"),
                          val.get("source", val.get("notes", ""))))
    flow.extend(_build_status_table(items, styles))

    cert = sec.get("certifications", {})
    items_cert: List[tuple] = []
    for key, val in cert.items():
        if key == "honest_disclaimer":
            continue
        if isinstance(val, dict):
            items_cert.append((key.replace("_", " ").upper(),
                                val.get("status", "roadmap"),
                                val.get("notes", "")))
    if items_cert:
        flow.extend(_build_status_table(items_cert, styles, title="Certifications"))

    if cert.get("honest_disclaimer"):
        flow.append(Paragraph(
            f"<i>{cert['honest_disclaimer']}</i>",
            styles["honest_intro"]))
    flow.append(PageBreak())

    flow.append(Paragraph(section_title(), styles["h1"]))
    flow.append(Paragraph(standard_disclaimer_paragraph(), styles["honest_intro"]))
    for line in sec.get("honest_scope", [])[:12]:
        flow.append(Paragraph(f"• {line}", styles["callout"]))

    return flow


# ════════════════════════════════════════════════════════════════════
# Compliance pack
# ════════════════════════════════════════════════════════════════════

def _build_compliance_pack(reg: Dict[str, Any], styles) -> List:
    flow: List = []

    # Cover
    flow.append(Spacer(1, 0.3 * inch))
    flow.append(Paragraph(theme.PRODUCT_NAME, styles["title"]))
    flow.append(Paragraph("Compliance Pack", styles["subtitle"]))
    flow.append(Spacer(1, 0.3 * inch))
    flow.append(Paragraph(
        f"Version {reg['platform']['version']} · "
        f"{reg['platform']['audit_gates']} audit gates · "
        f"For regulator + compliance review",
        styles["footer_caption"]))
    flow.append(PageBreak())

    flow.append(Paragraph("1. Regulatory Alignment", styles["h1"]))
    flow.append(Paragraph(
        "A2Z aligns with the following regulatory frames at the architecture / "
        "engine level. Per-bank deployment review is required for production "
        "certification.",
        styles["body"]))
    for item in reg.get("regulatory_alignment", []):
        flow.append(Paragraph(f"✓ {item}", styles["callout"]))
    flow.append(Spacer(1, 0.2 * inch))

    flow.append(Paragraph("2. Engine-to-Regulation Mapping", styles["h1"]))

    mapping = [
        ("Capital adequacy", "Basel III + CBK Prudential",
         "utils/capital_adequacy.py"),
        ("IFRS 9 staging", "IFRS 9 + CBK Loan Classification",
         "utils/ifrs9_engine.py"),
        ("IFRS 7 disclosures", "IFRS 7 (financial instruments)",
         "utils/ifrs7_engine.py"),
        ("KYC / AML risk scoring", "AMLCFT Act + CBK guidelines",
         "utils/kyc_aml_risk.py"),
        ("FLEXCUBE resilience", "CBK Operations Resilience Guidelines (2019)",
         "utils/flexcube_adapter.py — locked by G108"),
        ("Audit trail (tamper-evident)", "Banking Act + DPA 2019",
         "utils/core_audit.py"),
        ("Channel reliability alerts", "CBK Consumer Protection",
         "utils/channels_reliability.py + utils/smart_alerts.py"),
        ("PUBLISHED_LANGUAGE payload version", "Charter §7 (DDD pattern)",
         "Locked by audit gate G109"),
    ]
    flow.extend(_build_status_table(
        [(area, "shipped", f"{reg_str} → {src}")
         for area, reg_str, src in mapping],
        styles, title=""))
    flow.append(PageBreak())

    flow.append(Paragraph("3. Audit Perimeter — 6-Gate Defense-in-Depth", styles["h1"]))
    flow.append(Paragraph(
        "The platform's audit script verifies architectural invariants on every "
        "build. The following 6 gates form the defense-in-depth perimeter that "
        "locks v7.x → v8.x architecture as permanent invariants.",
        styles["body"]))

    gates = [
        ("G104", "Engine migration ratchet", "v7.0.1"),
        ("G105", "Strict invariant registry usage", "v7.1"),
        ("G106", "Loop round-trip-testability", "v7.15"),
        ("G107", "Stock data_source provenance", "v7.15"),
        ("G108", "FLEXCUBE resilience + observability", "v8.3"),
        ("G109", "PUBLISHED_LANGUAGE payload_version", "v8.7"),
    ]
    data = [["Gate", "What it locks", "Shipped"]]
    for g, what, ver in gates:
        data.append([g, what, ver])
    t = Table(data, colWidths=[0.8 * inch, 4.0 * inch, 1.0 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#" + theme.PRIMARY_HEX)),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), theme.FONT_HEADER),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [white, HexColor("#" + theme.LIGHT_GREY_HEX)]),
        ("GRID", (0, 0), (-1, -1), 0.25, HexColor("#" + theme.MID_GREY_HEX)),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    flow.append(t)
    flow.append(Spacer(1, 0.2 * inch))
    flow.append(Paragraph(
        "<b>Verification:</b> regulators can run "
        f"<font face='{theme.FONT_MONO}'>{reg['platform']['audit_command']}</font> "
        "on any version of the platform; any failure indicates a defect or "
        "regression that must be fixed before deployment.",
        styles["callout"]))
    flow.append(PageBreak())

    flow.append(Paragraph(section_title(), styles["h1"]))
    flow.append(Paragraph(standard_disclaimer_paragraph(), styles["honest_intro"]))

    flow.append(Paragraph(
        "<b>Honest scope</b> for this compliance pack:",
        styles["h2"]))
    items = [
        "Alignment is at architectural / engine level. Bank-specific deployment review is required for production certification.",
        "A2Z does not currently hold SOC 2 Type II or ISO 27001 certifications. References to readiness reflect architectural alignment with the standards' control families.",
        "Per-bank custom regulatory frames (e.g. Sharia compliance, sector-specific guidelines) are not pre-bundled; the audit gate pattern supports extension.",
        "Encryption at-rest and in-transit are deployment-specific patterns; A2Z relies on host infrastructure (cloud/on-prem) for actual implementation.",
        "External regulatory body integrations (CBK reporting portals, CRB submission interfaces) are roadmap; v8.x ships the data; submission integration is bank-specific.",
    ]
    for item in items:
        flow.append(Paragraph(f"• {item}", styles["callout"]))

    return flow


# ════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════

def _build_claims(reg: Dict[str, Any]) -> List[Claim]:
    return [
        Claim("audit gates", "platform.audit_gates",
              reg["platform"]["audit_gates"], "scripts/audit.py"),
        Claim("loops wired", "loops_wired_pct", 100.0, "utils/system_flows.py"),
    ]


def generate_security_whitepaper(output_path: Path) -> Dict[str, Any]:
    """Generate the security whitepaper PDF for CISO."""
    reg = load_registry()
    claims = _build_claims(reg)
    result = validate_claims(claims, reg, fail_fast=False)
    if result["failed"] > 0:
        return {"status": "ABORTED", "reason": "Claim validation failed",
                "failures": result["failures"]}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _build_styles()
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.85 * inch,
        title=f"{theme.PRODUCT_NAME} Security Whitepaper",
        author="A2Z Platform Engineering")
    footer = _make_footer_callback(reg, "Security Whitepaper")
    doc.build(_build_security_whitepaper(reg, styles),
              onFirstPage=footer, onLaterPages=footer)
    return {"status": "OK", "output_path": str(output_path),
            "claims_validated": result["passed"],
            "platform_version": reg["platform"]["version"]}


def generate_compliance_pack(output_path: Path) -> Dict[str, Any]:
    """Generate the compliance pack PDF for regulator."""
    reg = load_registry()
    claims = _build_claims(reg)
    result = validate_claims(claims, reg, fail_fast=False)
    if result["failed"] > 0:
        return {"status": "ABORTED", "reason": "Claim validation failed",
                "failures": result["failures"]}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _build_styles()
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.85 * inch,
        title=f"{theme.PRODUCT_NAME} Compliance Pack",
        author="A2Z Platform Engineering")
    footer = _make_footer_callback(reg, "Compliance Pack")
    doc.build(_build_compliance_pack(reg, styles),
              onFirstPage=footer, onLaterPages=footer)
    return {"status": "OK", "output_path": str(output_path),
            "claims_validated": result["passed"],
            "platform_version": reg["platform"]["version"]}


if __name__ == "__main__":
    import sys
    print("A2Z Whitepaper generator")

    out_sec = Path("/tmp/A2Z_MIS_360_Security_Whitepaper.pdf")
    r1 = generate_security_whitepaper(out_sec)
    print(f"  Security: {r1['status']}", end="")
    print(f" ({r1.get('output_path', 'failed')})")

    out_comp = Path("/tmp/A2Z_MIS_360_Compliance_Pack.pdf")
    r2 = generate_compliance_pack(out_comp)
    print(f"  Compliance: {r2['status']}", end="")
    print(f" ({r2.get('output_path', 'failed')})")

    if r1["status"] != "OK" or r2["status"] != "OK":
        sys.exit(1)
