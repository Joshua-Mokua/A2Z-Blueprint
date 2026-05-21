"""
================================================================================
A2Z MIS 360 — Standards #357 + #358: Proposition Presentation + API & Integration
================================================================================

Risk classification: Cat C (channel-specific rendering + API exposure layer)

Combined module:
    #357: Proposition Presentation (Channel-Specific) — channel-optimized
          presentation: app card, web banner, RM script, SMS template,
          email template. Personalized per customer.
    #358: Proposition API & Integration — API to expose propositions to
          channels: app, web, RM desktop, branch terminals. Standard
          schema, real-time eligibility.

Standards consolidated: #357 produces channel templates; #358 exposes
those templates via a standard API surface to consuming channels. Both
are output-layer concerns operating on the same proposition + customer
+ eligibility + pricing inputs.

Public API (#357 presentation):
    register_template(template_data, actor, reason)
    render_for_channel(prop_id, channel, customer_attrs, eligibility, pricing)
        -> Dict (channel-specific payload)
    list_templates(prop_id=None, channel=None) -> List

Public API (#358 channel integration):
    expose_proposition(prop_id, channel, customer_attrs)
        -> {eligible, payload, decline_reason}
    bulk_expose(channel, customer_attrs_list, top_n=3) -> NBA-ranked list
    api_payload_schema(channel) -> documented expected fields

PRESENTATION_CHANNELS byte-for-byte:
    APP_CARD       -- mobile app card (image + headline + CTA)
    WEB_BANNER     -- web hero banner (large image + headline + CTA)
    RM_SCRIPT      -- RM talking script (intro + benefits + objection_handling)
    SMS            -- short text (max 160 chars per SMS)
    EMAIL          -- HTML email (subject + body + CTA)

Honesty rules:
    Rule 1: render returns reason="not_eligible" with empty payload
            rather than fabricating offers
    Rule 6: invalid channel rejected explicitly
    Rule 4: actor required on template registration

================================================================================
"""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.propositions_catalog import PropositionsCatalogEngine
from utils.propositions_eligibility import PropositionsEligibilityEngine
from utils.propositions_pricing import PropositionPricingEngine
from utils.propositions_orchestration import PropositionOrchestrationEngine


PRESENTATION_CHANNELS: Tuple[str, ...] = (
    "APP_CARD", "WEB_BANNER", "RM_SCRIPT", "SMS", "EMAIL",
)

SMS_MAX_CHARS: int = 160


class PropositionsPresentationEngine:
    """Channel-specific rendering + API exposure layer."""

    def __init__(
        self,
        catalog: Optional[PropositionsCatalogEngine] = None,
        eligibility: Optional[PropositionsEligibilityEngine] = None,
        pricing: Optional[PropositionPricingEngine] = None,
        orchestration: Optional[PropositionOrchestrationEngine] = None,
        templates_path: Optional[Path] = None,
    ):
        self.catalog = catalog or PropositionsCatalogEngine()
        self.eligibility = eligibility or PropositionsEligibilityEngine(
            catalog=self.catalog,
        )
        self.pricing = pricing or PropositionPricingEngine(catalog=self.catalog)
        self.orchestration = orchestration or PropositionOrchestrationEngine(
            catalog=self.catalog,
            eligibility=self.eligibility,
            pricing=self.pricing,
        )
        base = Path(__file__).parent.parent / "data"
        self.templates_path = templates_path or base / "presentation_templates.json"

    def _load(self, path: Path, table: str, idx: Tuple[str, ...]) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(path, table=table, index_cols=idx)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, path: Path, records: List[Dict[str, Any]],
                table: str, pk: str) -> bool:
        try:
            from utils.db import db as _db
            path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(path, data=records, table=table, pk_col=pk)
            return True
        except Exception:
            return False

    # ── #357 Templates ─────────────────────────────────────────────

    def register_template(
        self,
        template_data: Dict[str, Any],
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("template_id", "proposition_id", "channel"):
            if f not in template_data or not template_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if template_data["channel"] not in PRESENTATION_CHANNELS:
            return {
                "registered": False,
                "error": f"invalid_channel:{template_data['channel']}",
                "valid_channels": list(PRESENTATION_CHANNELS),
            }

        records = self._load(self.templates_path,
                                "presentation_templates", ("template_id",))
        if any(r.get("template_id") == template_data["template_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_template_id"}

        record = {
            "template_id": template_data["template_id"],
            "proposition_id": template_data["proposition_id"],
            "channel": template_data["channel"],
            "headline_template": template_data.get("headline_template", ""),
            "body_template": template_data.get("body_template", ""),
            "cta_text": template_data.get("cta_text", "Learn More"),
            "cta_url": template_data.get("cta_url", ""),
            "image_url": template_data.get("image_url", ""),
            "subject_template": template_data.get("subject_template", ""),
            "objection_handling": template_data.get("objection_handling", []),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.templates_path, records,
                          "presentation_templates", "template_id")
        return {"registered": ok, "template_id": template_data["template_id"]}

    def list_templates(
        self,
        prop_id: Optional[str] = None,
        channel: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        records = self._load(self.templates_path,
                                "presentation_templates", ("template_id",))
        out = []
        for r in records:
            if prop_id and r.get("proposition_id") != prop_id:
                continue
            if channel and r.get("channel") != channel:
                continue
            out.append(r)
        return out

    @staticmethod
    def _substitute(template: str, tokens: Dict[str, str]) -> str:
        """Simple token substitution: {customer_name} → 'Jane Doe'."""
        out = template
        for k, v in tokens.items():
            out = out.replace("{" + k + "}", str(v) if v is not None else "")
        return out

    def _build_tokens(
        self,
        prop: Dict[str, Any],
        customer_attrs: Dict[str, Any],
        pricing_result: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        tokens = {
            "proposition_name": prop.get("name", ""),
            "customer_name": customer_attrs.get("name", "Customer"),
            "customer_id": customer_attrs.get("customer_id", ""),
            "first_feature": (
                prop.get("features", [""])[0]
                if prop.get("features") else ""
            ),
            "benefit": ", ".join(prop.get("features", [])[:3]),
        }
        if pricing_result and pricing_result.get("price_kes"):
            tokens["price_kes"] = pricing_result["price_kes"]
        else:
            tokens["price_kes"] = "—"
        return tokens

    # ── #357 Channel rendering ─────────────────────────────────────

    def render_for_channel(
        self,
        prop_id: str,
        channel: str,
        customer_attrs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Render a proposition for a specific channel after eligibility +
        pricing checks."""
        if channel not in PRESENTATION_CHANNELS:
            return {
                "rendered": False,
                "error": f"invalid_channel:{channel}",
                "valid_channels": list(PRESENTATION_CHANNELS),
            }

        prop = self.catalog.get_proposition(prop_id)
        if prop is None:
            return {"rendered": False, "error": "proposition_not_found"}
        if prop.get("state") != "LIVE":
            return {
                "rendered": False,
                "error": f"proposition_not_live:{prop.get('state')}",
            }

        # Eligibility check
        elig = self.eligibility.check_eligibility(prop_id, customer_attrs)
        if not elig.get("eligible"):
            return {
                "rendered": False,
                "reason": "not_eligible",
                "eligibility_outcome": elig.get("outcome"),
                "eligibility_reasons": elig.get("reasons", []),
            }

        # Pricing
        pricing = self.pricing.compute_price(prop_id, customer_attrs)

        # Find template for this channel
        templates = self.list_templates(prop_id=prop_id, channel=channel)
        if not templates:
            return {
                "rendered": False,
                "reason": f"no_template_for_channel:{channel}",
            }
        template = templates[0]

        tokens = self._build_tokens(prop, customer_attrs, pricing)
        headline = self._substitute(template.get("headline_template", ""), tokens)
        body = self._substitute(template.get("body_template", ""), tokens)
        subject = self._substitute(template.get("subject_template", ""), tokens)

        # Channel-specific payload structure
        payload: Dict[str, Any] = {
            "rendered": True,
            "proposition_id": prop_id,
            "channel": channel,
            "customer_id": customer_attrs.get("customer_id"),
            "headline": headline,
            "body": body,
            "cta_text": template.get("cta_text", "Learn More"),
            "price_kes": pricing.get("price_kes"),
            "rendered_at": datetime.utcnow().isoformat(),
        }

        if channel == "APP_CARD":
            payload["card"] = {
                "image_url": template.get("image_url", ""),
                "title": headline,
                "subtitle": body[:120],  # cards have limited space
                "cta": template.get("cta_text", "Learn More"),
                "cta_url": template.get("cta_url", ""),
            }
        elif channel == "WEB_BANNER":
            payload["banner"] = {
                "image_url": template.get("image_url", ""),
                "headline": headline,
                "subheadline": body,
                "cta_text": template.get("cta_text", "Learn More"),
                "cta_url": template.get("cta_url", ""),
            }
        elif channel == "RM_SCRIPT":
            payload["script"] = {
                "intro": headline,
                "talking_points": body.split("\n") if body else [],
                "objection_handling": template.get("objection_handling", []),
                "next_step": template.get("cta_text", "Schedule meeting"),
            }
        elif channel == "SMS":
            sms_text = (headline + ": " + body)[:SMS_MAX_CHARS]
            payload["sms"] = {
                "text": sms_text,
                "char_count": len(sms_text),
                "max_chars": SMS_MAX_CHARS,
            }
        elif channel == "EMAIL":
            payload["email"] = {
                "subject": subject or headline,
                "body_html": f"<h1>{headline}</h1><p>{body}</p>",
                "cta_text": template.get("cta_text", "Learn More"),
                "cta_url": template.get("cta_url", ""),
            }

        return payload

    # ── #358 API exposure ─────────────────────────────────────────

    def expose_proposition(
        self,
        prop_id: str,
        channel: str,
        customer_attrs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Single proposition exposure for a channel.

        Channels (app, web, RM desktop, branch terminals) call this for
        a specific proposition and customer. Returns the rendered payload
        OR a structured rejection with reason codes.
        """
        return self.render_for_channel(prop_id, channel, customer_attrs)

    def bulk_expose(
        self,
        channel: str,
        customer_attrs: Dict[str, Any],
        top_n: int = 3,
    ) -> Dict[str, Any]:
        """Get top-N NBA propositions rendered for a channel.

        Channels call this when they want the system to pick the best
        propositions to show — not specifying a particular prop_id.
        """
        if channel not in PRESENTATION_CHANNELS:
            return {
                "exposed": False,
                "error": f"invalid_channel:{channel}",
            }

        nba = self.orchestration.next_best_propositions(
            customer_attrs, top_n=top_n,
        )
        if nba.get("reason"):
            return {
                "exposed": False,
                "reason": nba["reason"],
                "customer_id": customer_attrs.get("customer_id"),
            }

        rendered_list = []
        for entry in nba.get("propositions", []):
            r = self.render_for_channel(
                entry["proposition_id"], channel, customer_attrs,
            )
            if r.get("rendered"):
                rendered_list.append({**r, "score": entry.get("score")})

        return {
            "exposed": True,
            "channel": channel,
            "customer_id": customer_attrs.get("customer_id"),
            "items": rendered_list,
            "item_count": len(rendered_list),
        }

    def api_payload_schema(self, channel: str) -> Dict[str, Any]:
        """Document the expected payload schema for each channel."""
        if channel not in PRESENTATION_CHANNELS:
            return {"error": f"invalid_channel:{channel}",
                       "valid_channels": list(PRESENTATION_CHANNELS)}

        # Common
        base = {
            "rendered": "bool",
            "proposition_id": "str",
            "channel": "str (one of PRESENTATION_CHANNELS)",
            "customer_id": "str",
            "headline": "str (token-substituted)",
            "body": "str (token-substituted)",
            "cta_text": "str",
            "price_kes": "str (Decimal-formatted) or null",
        }
        channel_specific = {
            "APP_CARD": {
                "card.image_url": "str (URL)",
                "card.title": "str",
                "card.subtitle": "str (max 120 chars)",
                "card.cta": "str",
                "card.cta_url": "str (deep link)",
            },
            "WEB_BANNER": {
                "banner.image_url": "str (URL)",
                "banner.headline": "str",
                "banner.subheadline": "str",
                "banner.cta_text": "str",
                "banner.cta_url": "str",
            },
            "RM_SCRIPT": {
                "script.intro": "str",
                "script.talking_points": "List[str]",
                "script.objection_handling": "List[Dict]",
                "script.next_step": "str",
            },
            "SMS": {
                "sms.text": f"str (max {SMS_MAX_CHARS} chars)",
                "sms.char_count": "int",
                "sms.max_chars": f"int ({SMS_MAX_CHARS})",
            },
            "EMAIL": {
                "email.subject": "str",
                "email.body_html": "str (HTML)",
                "email.cta_text": "str",
                "email.cta_url": "str",
            },
        }
        return {
            "channel": channel,
            "base_payload": base,
            "channel_payload": channel_specific[channel],
            "rejection_response": {
                "rendered": "false",
                "reason": "str (e.g. 'not_eligible', 'no_template_for_channel')",
                "eligibility_outcome": "str (only when reason='not_eligible')",
                "eligibility_reasons": "List[str]",
            },
        }


def _self_test() -> None:
    import tempfile
    from utils.propositions_catalog import APPROVAL_LEVELS

    assert "APP_CARD" in PRESENTATION_CHANNELS
    assert "EMAIL" in PRESENTATION_CHANNELS

    with tempfile.TemporaryDirectory() as tmpdir:
        catalog = PropositionsCatalogEngine(
            propositions_path=Path(tmpdir) / "p.json",
            approvals_path=Path(tmpdir) / "a.json",
            reviews_path=Path(tmpdir) / "r.json",
        )
        engine = PropositionsPresentationEngine(
            catalog=catalog,
            templates_path=Path(tmpdir) / "tpl.json",
        )

        # Setup: register + activate proposition
        catalog.register_proposition(
            {"proposition_id": "PROP-DIASP",
             "name": "Diaspora Wealth Account",
             "owner_role": "head",
             "channels": ["MOBILE_APP", "BRANCH"],
             "target_segments": ["DIASPORA"],
             "features": ["multi_currency", "preferential_fx",
                              "free_swift"]},
            actor="x",
        )
        catalog.submit_for_review("PROP-DIASP", actor="x", reason="r")
        catalog.submit_for_approval("PROP-DIASP", actor="x", reason="r")
        for level in APPROVAL_LEVELS:
            catalog.record_approval(
                "PROP-DIASP", level, "APPROVED", actor="x", reason="r",
            )
        catalog.activate_proposition(
            "PROP-DIASP", actor="md", reason="launch",
        )
        # Activate pricing
        engine.pricing.register_pricing_strategy(
            "PROP-DIASP",
            {"strategy_id": "STR-DIASP",
             "strategy_type": "FLAT",
             "base_price_kes": "5000"},
            actor="finance", reason="initial",
        )
        engine.pricing.transition_strategy_state(
            "STR-DIASP", "ACTIVE", actor="finance", reason="go",
        )

        # Test 1: register templates
        for ch in ("APP_CARD", "WEB_BANNER", "RM_SCRIPT", "SMS", "EMAIL"):
            r = engine.register_template(
                {"template_id": f"TPL-DIASP-{ch}",
                 "proposition_id": "PROP-DIASP",
                 "channel": ch,
                 "headline_template": "Welcome {customer_name} to {proposition_name}",
                 "body_template": "Get {benefit} for just {price_kes} KES annually",
                 "cta_text": "Apply Now",
                 "subject_template": "Exclusive: {proposition_name}"},
                actor="marketing", reason=f"template for {ch}",
            )
            assert r["registered"], (ch, r)

        # Test 2: invalid channel
        r = engine.register_template(
            {"template_id": "TPL-X", "proposition_id": "PROP-DIASP",
             "channel": "INVALID"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Test 3: render APP_CARD for eligible customer
        attrs = {
            "customer_id": "CUST-DIASP-001",
            "name": "Jane Mwangi",
            "kyc_status": "COMPLETE",
            "segment": "DIASPORA",
            "age": 35,
            "aml_status": "CLEARED",
            "balance_kes": "200000",
            "preferred_channel": "MOBILE_APP",
            "risk_appetite": "MODERATE",
        }
        r = engine.render_for_channel("PROP-DIASP", "APP_CARD", attrs)
        assert r["rendered"]
        assert "Jane Mwangi" in r["headline"]
        assert "Diaspora Wealth Account" in r["headline"]
        assert "5000" in r["price_kes"]
        assert "card" in r

        # Test 4: render SMS — char-bounded
        r = engine.render_for_channel("PROP-DIASP", "SMS", attrs)
        assert r["rendered"]
        assert r["sms"]["char_count"] <= SMS_MAX_CHARS

        # Test 5: render EMAIL
        r = engine.render_for_channel("PROP-DIASP", "EMAIL", attrs)
        assert r["rendered"]
        assert "<h1>" in r["email"]["body_html"]
        assert "Diaspora Wealth Account" in r["email"]["subject"]

        # Test 6: render RM_SCRIPT
        r = engine.render_for_channel("PROP-DIASP", "RM_SCRIPT", attrs)
        assert r["rendered"]
        assert "intro" in r["script"]

        # Test 7: ineligible customer — render rejected
        ineligible_attrs = {
            "customer_id": "CUST-YOUTH",
            "kyc_status": "COMPLETE",
            "segment": "YOUTH",
            "age": 22,
            "aml_status": "CLEARED",
            "balance_kes": "5000",
            "preferred_channel": "MOBILE_APP",
            "risk_appetite": "MODERATE",
        }
        r = engine.render_for_channel("PROP-DIASP", "APP_CARD", ineligible_attrs)
        assert not r["rendered"]
        assert r["reason"] == "not_eligible"

        # Test 8: invalid channel
        r = engine.render_for_channel("PROP-DIASP", "INVALID", attrs)
        assert not r["rendered"]
        assert "invalid_channel" in r["error"]

        # Test 9: non-LIVE proposition
        catalog.register_proposition(
            {"proposition_id": "PROP-DRAFT", "name": "Y", "owner_role": "h"},
            actor="x",
        )
        r = engine.render_for_channel("PROP-DRAFT", "APP_CARD", attrs)
        assert not r["rendered"]
        assert "not_live" in r["error"]

        # Test 10: no template for channel
        catalog.register_proposition(
            {"proposition_id": "PROP-NOTPL", "name": "Z", "owner_role": "h",
             "channels": ["MOBILE_APP"], "target_segments": []},
            actor="x",
        )
        catalog.submit_for_review("PROP-NOTPL", actor="x", reason="r")
        catalog.submit_for_approval("PROP-NOTPL", actor="x", reason="r")
        for level in APPROVAL_LEVELS:
            catalog.record_approval(
                "PROP-NOTPL", level, "APPROVED", actor="x", reason="r",
            )
        catalog.activate_proposition(
            "PROP-NOTPL", actor="x", reason="launch",
        )
        r = engine.render_for_channel("PROP-NOTPL", "APP_CARD", attrs)
        assert not r["rendered"]
        assert "no_template_for_channel" in r["reason"]

        # Test 11: bulk_expose
        r = engine.bulk_expose("APP_CARD", attrs, top_n=2)
        # Should expose PROP-DIASP at minimum
        assert r["exposed"]
        # Items may be 0 if PROP-NOTPL has no template — only PROP-DIASP works
        assert len(r["items"]) >= 1

        # Test 12: api_payload_schema
        s = engine.api_payload_schema("APP_CARD")
        assert "card.image_url" in s["channel_payload"]

        s = engine.api_payload_schema("INVALID")
        assert "invalid_channel" in s["error"]

        # Test 13: expose_proposition (alias for render)
        r = engine.expose_proposition("PROP-DIASP", "APP_CARD", attrs)
        assert r["rendered"]

    print("  ✅ propositions_presentation self-test PASS")


if __name__ == "__main__":
    _self_test()
