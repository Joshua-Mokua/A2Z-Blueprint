# A2Z MIS 360 — v10.194 Changelog

## FATCA/CRS XML GENERATION — closes the v6/v7 deferral

**Release date:** 2026-05-06
**Audit score:** 159/159 gates = 100.0% PASS (unchanged from v10.193)

---

## Summary

This release closes the **FATCA/CRS XML generation** deferral that
has been carried forward since v6. The `utils/fatca_crs.py` engine
(ENH-060) now produces well-formed XML payloads conforming to the
OECD CRS XSD v2.0 and IRS FATCA XSD v2.4 schemas, replacing the
v6-era `build_payload_skeleton()` that returned only a Python dict
envelope.

Same shape as v10.193 (CBK returns extension): one engine module,
new frozen dataclasses, new methods, new self-tests, no new audit
gate. Diagnostic only per Rule 7 — the engine produces XML strings;
the caller signs, validates against XSDs, encrypts, and transmits.

The v6 module's `SPEC_DEVIATION_NOTE` recorded the deferral
explicitly:

> "Full FATCA Form 8966 XML and OECD CRS XML generation is deferred
> to v7; v6 ships deterministic classification, balance aggregation,
> and skeleton envelope"

That note is now updated to reflect the XML-implemented state.

---

## What shipped

### 2 new dataclasses

**`XmlReportSenderInfo`** — message envelope metadata required by
both schemas:

- Sender identity (`sender_in` GIIN/IN, `sender_name`)
- Routing (`transmitting_country` ISO-3166-1 alpha-2,
  `receiving_country`, `message_ref_id`)
- Period (`reporting_period` ISO date YYYY-12-31, `timestamp_iso`
  ISO-8601)
- Reporting Financial Institution block (`fi_in`, `fi_name`,
  `fi_address_country`, `fi_address_free`, `contact`)

`__post_init__` validates non-empty fields and ISO-3166-1 alpha-2
length constraint on country codes.

**`XmlReportableRecord`** — enriched per-account record combining a
classification-stage `ReportableSnapshot` with the additional
metadata required for XML emission (account holder name, address,
TIN, birth date for individuals, doc_type for corrected/deleted
records, currency code). Validates `account_holder_type`,
`address_country_code`, `doc_type` (OECD1/OECD2/OECD3), and
`currency_code` (ISO-4217 alpha-3).

### 2 new XML emitters on `FatcaCrsReportingEngine`

**`build_crs_xml(records, sender) -> str`** — produces OECD CRS
XML v2.0 payload as a UTF-8 string with XML declaration. Filters
records to include only `REPORTABLE_CRS` and `REPORTABLE_BOTH`
statuses (US-only persons resident only in the US don't go in CRS
reports). Generates:

- Root `<CRS_OECD version="2.0">` with the four required namespace
  declarations (`urn:oecd:ties:crs:v2`, `urn:oecd:ties:crsstf:v5`,
  `urn:oecd:ties:isocrstypes:v1`, `xsi`)
- `<MessageSpec>` with all 10 required elements (SendingCompanyIN,
  TransmittingCountry, ReceivingCountry, MessageType="CRS",
  Warning, Contact, MessageRefId, MessageTypeIndic="CRS701",
  ReportingPeriod, Timestamp)
- `<CrsBody>` containing `<ReportingFI>` (the bank's identity, with
  GIIN/TIN type discrimination and AddressFree under
  legalAddressType="OECD303" for registered office) and a single
  `<ReportingGroup>` wrapping all `<AccountReport>` elements
- Per `<AccountReport>`: DocSpec with deterministic DocRefId
  (sender_in.period.customer_id), AccountNumber with
  AcctNumberType="OECD605", AccountHolder split into Individual or
  Organisation by record's account_holder_type, AccountBalance
  with currCode attribute

**`build_fatca_xml(records, sender) -> str`** — produces IRS FATCA
XML v2.4 payload. Same filtering logic in reverse — only
`REPORTABLE_FATCA` and `REPORTABLE_BOTH` are included (CRS-only
non-US tax residents don't go in FATCA reports). Same structural
template but with FATCA namespaces (`urn:oecd:ties:fatca:v2.4`,
`urn:oecd:ties:fatcastf:v2`), MessageType="FATCA", and
MessageTypeIndic="FATCA701".

### Helper methods (private)

- `_build_message_spec()` — shared envelope builder used by both
  CRS and FATCA paths
- `_build_reporting_fi()` — bank's own RFI block
- `_build_account_holder()` — Individual or Organisation switch with
  per-regime ResCountryCode logic (FATCA forces "US"; CRS uses
  first listed jurisdiction)
- `_build_account_report()` — single AccountReport composer
- `_make_doc_ref_id()` — deterministic DocRefId generator
- `_indent_tree()` — pretty-print indentation (in-place)
- `_ce()` — child-element-with-text helper (keeps builder bodies
  readable)

### Module-level constants added

```python
CRS_NAMESPACE = "urn:oecd:ties:crs:v2"
CRS_STF_NAMESPACE = "urn:oecd:ties:crsstf:v5"
FATCA_NAMESPACE = "urn:oecd:ties:fatca:v2.4"
FATCA_STF_NAMESPACE = "urn:oecd:ties:fatcastf:v2"
ISO_NAMESPACE = "urn:oecd:ties:isocrstypes:v1"
```

### Tests

9 new self-tests added to the module's existing 16 (25 total now):

- `_test_crs_xml_well_formed` — emitted XML round-trips through
  ElementTree.fromstring, root tag is CRS_OECD with correct
  namespace
- `_test_crs_xml_filters_us_only` — REPORTABLE_FATCA records do not
  appear in CRS XML output
- `_test_fatca_xml_well_formed` — root tag FATCA_OECD with v2.4
  namespace
- `_test_fatca_xml_filters_non_us` — REPORTABLE_CRS records do not
  appear in FATCA XML output
- `_test_xml_includes_message_spec` — both formats include
  MessageSpec with sender's MessageRefId, ReportingPeriod, and
  Timestamp
- `_test_xml_includes_reporting_fi` — both formats declare the
  ReportingFI block with bank's IN, name, and address
- `_test_xml_balance_currency_attr` — AccountBalance carries
  currCode attribute
- `_test_xml_validates_sender_info` — XmlReportSenderInfo rejects
  empty sender_in and 3-character country codes
- `_test_xml_validates_reportable_record` — XmlReportableRecord
  rejects bad doc_type and 4-character currency codes

```
$ python utils/fatca_crs.py
============================================================
FATCA/CRS Reporting Engine — Self-Tests (#60)
============================================================
  ALL 25 TESTS PASSED
```

### Audit gate update

Audit gate **G61 `transaction_monitoring_fatca_crs_correct`** was
checking that `SPEC_DEVIATION_NOTE` matched the v6-era deferral
text byte-for-byte. Updated to expect the v10.194 text instead. The
gate's other invariants (Rule 1 strict-greater-than threshold, Rule
6 UNDOCUMENTED on missing self-cert, etc.) are preserved.

---

## Sample output

CRS XML for a Tier-2 Kenya bank reporting one GB-resident customer
and one US-and-DE dual-status customer (the US-only customer is
excluded from CRS):

```xml
<?xml version='1.0' encoding='utf-8'?>
<CRS_OECD version="2.0" xmlns="urn:oecd:ties:crs:v2"
          xmlns:stf="urn:oecd:ties:crsstf:v5"
          xmlns:iso="urn:oecd:ties:isocrstypes:v1"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <MessageSpec>
    <SendingCompanyIN>9X5Y3T.99999.SL.404</SendingCompanyIN>
    <TransmittingCountry>KE</TransmittingCountry>
    <ReceivingCountry>US</ReceivingCountry>
    <MessageType>CRS</MessageType>
    <Warning />
    <Contact>aml.team@ecobank.com</Contact>
    <MessageRefId>KE2025ECOBANK0001</MessageRefId>
    <MessageTypeIndic>CRS701</MessageTypeIndic>
    <ReportingPeriod>2025-12-31</ReportingPeriod>
    <Timestamp>2026-01-15T10:00:00Z</Timestamp>
  </MessageSpec>
  <CrsBody>
    <ReportingFI>...</ReportingFI>
    <ReportingGroup>
      <AccountReport>...</AccountReport>  <!-- C200 GB resident -->
      <AccountReport>...</AccountReport>  <!-- C300 DE+US dual -->
    </ReportingGroup>
  </CrsBody>
</CRS_OECD>
```

The FATCA XML output for the same input has the inverse account
list (US-only and dual-status; the GB-only customer is excluded).

---

## Files changed

```
utils/fatca_crs.py          (ENH-060 extended: +2 dataclasses, +2 emitters,
                             +6 helpers, +5 namespace constants, +9 tests,
                             SPEC_DEVIATION_NOTE updated)
scripts/audit.py            (G61 expected SPEC_DEVIATION_NOTE updated)
CHANGELOG_v10.194.md        (this file)
```

Three files changed. No page changes, no API changes, no nav
changes, no new audit gate.

---

## Audit ratchet

```
v10.193 (entering this release): 159/159 = 100% PASS
v10.194 (this release):           159/159 = 100% PASS
                                  no new gates
```

---

## How to apply

```bash
unzip -o a2z_v10.194_fatca_crs_xml.zip
python utils/fatca_crs.py        # → ALL 25 TESTS PASSED
python scripts/audit.py          # → 159/159 PASS
```

---

## Honest scope statement

This release is a **diagnostic-engine extension** of the same
character as v10.193. It does not:

- **Sign the XML.** The OECD recommends XMLDSig (XML Digital
  Signatures) for transmission; the engine does not embed a
  `<Signature>` block, and does not handle the signing private
  key. The bank's filing process owns key management.
- **Validate against external XSD files.** The engine produces
  XML matching the OECD CRS v2.0 and IRS FATCA v2.4 element
  hierarchies, but does not load `.xsd` files at runtime to
  validate against. A future release could add lxml-based
  validation; doing so would add a third-party dependency the
  module currently avoids.
- **Encrypt for transmission.** OECD requires PGP encryption
  before submission to most receiving authorities; that's
  downstream of XML generation.
- **Submit to KRA / IRS portals.** Per Rule 7, the engine
  generates content; transmission is operational.
- **Cover all schema optional elements.** The engine emits the
  mandatory + commonly-required elements (MessageSpec, ReportingFI,
  AccountReport with AccountHolder, AccountBalance). It does NOT
  emit `<Payment>` blocks (interest/dividend/gross-proceeds
  payments tracked per CRS501-CRS504 codes), `<ControllingPerson>`
  blocks for passive NFE entity holders, or PoolReport
  optimisation blocks for nil reports. These are tractable
  additions in future batches if specific filing scenarios need
  them; current code is honest about what it generates.
- **Validate TIN format per jurisdiction.** Each country has its
  own TIN format rules (US: SSN/EIN/ITIN; UK: NINO/UTR; DE:
  Steueridentifikationsnummer; etc.); the engine takes whatever
  string the caller supplies and emits it. Pre-submission TIN
  format validation is the bank's responsibility.
- **Track filing history or acknowledgements.** That belongs
  elsewhere (the existing `tax.reporting_submission` schema
  tracks submission state; this engine just generates content).
- **Ship a Streamlit page surface.** No UI work in this batch —
  pure engine extension. A future batch could add a tab on
  `pages/55_aml.py` or build a dedicated `pages/76_fatca_crs.py`
  that lets compliance officers preview generated XML, but the
  scope here is the engine.

---

## What's next (open candidates, not committed)

Of the original four platform-level deferrals:

- ~~CBK reports: 5/8~~ → **8/8** ✓ (closed by v10.193)
- ~~FATCA/CRS XML~~ → **implemented** ✓ (closed by v10.194)
- PG migration: 19/52 tables — still open
- React SPA / React Native — still open

Two of the four named deferrals are now closed. The remaining two
are larger commitments that don't fit single-batch closure. PG
migration is incremental work (5-10 tables per batch); React SPA
is a separate frontend project.

A natural next direction would be to either start a PG migration
batch (cleanest path: pick 5 tables that share a domain, migrate
their writers, run the audit), or pivot back to platform-level
work that surfaced in the v10.192 runtime fixes (additional
operator-driven testing, more bug surface to clear after Joshua
extracts and runs each release).

No commitment is made by this release.
