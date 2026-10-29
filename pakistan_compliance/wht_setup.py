# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Phase 4: Pakistan withholding-tax (WHT) setup automation.

Creates ERPNext's native **Tax Withholding Category** records for the Pakistani
income-tax sections most relevant to supplier payments, in Filer and Non-Filer
variants (filer = on the FBR Active Taxpayer List, non-filer = not). This reuses
ERPNext's built-in WHT engine (Purchase Invoice `apply_tds`, the supplier's
`tax_withholding_category`, dated rate rows and thresholds) rather than building a
parallel deduction engine, the same "extend the platform" approach used elsewhere
in this app.

Company-scoped like the Phase 2 tax setup: it creates a WHT payable account under
the company's Duties and Taxes group and adds it to each category's accounts table.
Idempotent: existing accounts / categories are skipped.

RATE POLICY (guardrails #1 and #4): the rates below are DEFAULTS that MUST be
verified against the current Finance Act / SROs (Income Tax Ordinance 2001, First
and Tenth Schedules) before production use. They are not baked in as truth: they
live in this editable table and in the created Tax Withholding Categories, both of
which a user can change without touching code. Non-filer rates are listed
explicitly per section (they are NOT uniformly double the filer rate). When a rate
is uncertain, confirm it; do not treat these defaults as authoritative.
"""

import frappe
from frappe import _

from pakistan_compliance.tax_setup import _acc, _ensure_account, _tax_parent

# WHT deducted by the buyer is a liability owed to FBR until deposited.
WHT_PAYABLE = "Withholding Tax Payable"

# Validity window for the seeded rate rows. WHT rates are set by the annual Finance
# Act; Pakistan's tax year runs 1 July to 30 June. from_date is the current tax
# year's start; to_date is left far in the future (not the tax-year end) so a later
# invoice never silently computes zero WHT. Review each rate when a new Finance Act
# or SRO changes it (edit the category's rate row, or add a new dated row).
WHT_RATES_FROM = "2025-07-01"
WHT_RATES_TO = "2099-12-31"

# ERPNext v15's WHT engine only starts withholding once a transaction reaches the
# single_threshold: its gate is `(single_threshold and net >= single_threshold)`, so
# a threshold of 0 short-circuits to "never withhold" (v15 was built around India's
# TDS, which always has a positive threshold). Most Pakistani sections (e.g. 153 for
# companies) have NO minimum, so we seed a nominal 1 to make v15 withhold on every
# transaction, on the FULL amount (tax_on_excess_amount is left off). Harmless on v16.
# Where a section has a real statutory exemption (e.g. 155 rent for individuals),
# raise this on that category. Keep it configurable; do not treat 1 as law.
WHT_SINGLE_THRESHOLD = 1.0

# Pakistan withholding income-tax sections most relevant to supplier payments.
# Rates are % from the official FBR Withholding Income Tax Rate Card for tax year
# 2026 (updated to 30 June 2025 per the Finance Act 2025), cross-checked against
# KPMG (Taseer Hadi), TAG & Co., A.F. Ferguson/PwC and Grant Thornton. Non-filer =
# filer rate uplifted 100% under the Tenth Schedule (a clean 2x for these sections).
# Where a section splits company vs individual/AOP, the COMPANY rate is used (ERP
# suppliers are usually companies); the non-company variants are noted below.
# Still verify against the live card before production; rates change every Finance Act.
#   Source: https://download1.fbr.gov.pk/Docs/20258181281745641WHT-RateCard.pdf
# Per-section caveats:
#   153(1)(a) goods:    5/10 company (5.5/11 individual-AOP). Was 4.5% pre-FA2025.
#   153(1)(b) services: 15/30 is the TY2026 GENERAL rate (FA2025 merged the old
#                       9%/11% company/non-company split). Reduced carve-outs exist:
#                       specified services (transport, courier, manpower, security,
#                       engineering) 6/12; IT & IT-enabled 4/8; media advertising
#                       1.5/3. Pick per supplier's service type. (Note: PwC's live
#                       page shows 7/14 because it has rolled forward to TY2027.)
#   153(1)(c) contracts: 7.5/15 company (8/16 individual-AOP; sportspersons 15/30).
#   233 commission:      12/24 general (advertising agents 10/20; life-insurance 8/16).
#   155 rent:            15/30 flat for a COMPANY payee. Individual/AOP landlords are
#                        SLAB-based (not a flat %), so they need separate handling and
#                        are intentionally not seeded as a flat category here.
WHT_SECTIONS = [
	{"section": "153(1)(a)", "label": "Sale of Goods", "filer": 5.0, "non_filer": 10.0},
	{"section": "153(1)(b)", "label": "Services", "filer": 15.0, "non_filer": 30.0},
	{"section": "153(1)(c)", "label": "Execution of Contracts", "filer": 7.5, "non_filer": 15.0},
	{"section": "233", "label": "Brokerage & Commission", "filer": 12.0, "non_filer": 24.0},
	{"section": "155", "label": "Rent of Immovable Property (Company)", "filer": 15.0, "non_filer": 30.0},
]

STATUSES = ("Filer", "Non-Filer")


def category_name(section, label, status):
	"""Stable, readable Tax Withholding Category name for a section + filer status."""
	return f"Pakistan WHT {section} {label} ({status})"


def _ensure_wht_category(title, rate, company, account):
	"""Create a Tax Withholding Category (native ERPNext) with one rate row and the
	company's WHT account, if a category by this name does not already exist.
	Returns True if created. Only common v15/v16 fields are set."""
	if frappe.db.exists("Tax Withholding Category", title):
		# Make sure the company's account row is present (a category may be shared
		# across companies), without touching the rate a customer may have edited.
		doc = frappe.get_doc("Tax Withholding Category", title)
		if not any(a.company == company for a in doc.accounts):
			doc.append("accounts", {"company": company, "account": account})
			doc.save(ignore_permissions=True)
		return False

	doc = frappe.get_doc(
		{
			"doctype": "Tax Withholding Category",
			"name": title,
			"category_name": title,
			"round_off_tax_amount": 1,
			"rates": [
				{
					"from_date": WHT_RATES_FROM,
					"to_date": WHT_RATES_TO,
					"tax_withholding_rate": rate,
					"single_threshold": WHT_SINGLE_THRESHOLD,
				}
			],
			"accounts": [{"company": company, "account": account}],
		}
	)
	doc.insert(ignore_permissions=True)
	return True


@frappe.whitelist()
def setup_company_wht(company):
	"""Create the Pakistan WHT payable account and the Tax Withholding Categories
	(Filer + Non-Filer per section) for `company`. Idempotent. Returns a summary."""
	frappe.only_for("System Manager")
	if not (company and frappe.db.exists("Company", company)):
		frappe.throw(_("Select a valid Company to set up withholding tax for."))

	parent = _tax_parent(company)
	account, _created = _ensure_account(company, WHT_PAYABLE, parent)

	created = {"account": WHT_PAYABLE if _created else None, "categories": []}
	for sec in WHT_SECTIONS:
		for status in STATUSES:
			rate = sec["filer"] if status == "Filer" else sec["non_filer"]
			title = category_name(sec["section"], sec["label"], status)
			if _ensure_wht_category(title, rate, company, account):
				created["categories"].append(title)

	frappe.db.commit()  # nosemgrep: intentional persist after a multi-step whitelisted action
	return created


def sync_supplier_wht_category(doc, method=None):
	"""Keep a supplier's WHT category variant in sync with its Filer status.

	When a supplier already has one of our seeded 'Pakistan WHT ... (Filer)' /
	'(Non-Filer)' categories (which fixes the income-tax *section*), and its Filer
	Status (ATL) says the other variant, switch to the matching variant of the SAME
	section so the correct rate applies. Does nothing if no Pakistan WHT category is
	set (we can't guess the section) or if it already matches. Supplier validate hook."""
	status = doc.get("custom_filer_status")  # "Filer" / "Non-Filer"
	category = doc.get("tax_withholding_category")
	if not (status and category and category.startswith("Pakistan WHT ")):
		return
	if not (category.endswith("(Filer)") or category.endswith("(Non-Filer)")):
		return

	desired_suffix = f"({status})"
	if category.endswith(desired_suffix):
		return  # already the right variant

	base = category.rsplit(" (", 1)[0]  # drop the trailing "(Filer)"/"(Non-Filer)"
	target = f"{base} ({status})"
	if frappe.db.exists("Tax Withholding Category", target):
		doc.tax_withholding_category = target
		frappe.msgprint(
			_("Withholding tax category switched to {0} to match the {1} status.").format(
				frappe.bold(target), frappe.bold(status)
			),
			alert=True,
			indicator="blue",
		)


def propagate_item_wht(doc, method=None):
	"""Make supplier-level WHT configuration work on ERPNext v16.

	v15 applies WHT from the document's `tax_withholding_category` (taken from the
	supplier) as a tax line at validation. v16 instead computes WHT from each item
	row's `tax_withholding_category` + `apply_tds`. So on v16 a category set only on
	the supplier would never deduct. This validate hook copies the document's WHT
	category (or, if unset, the supplier's) down to item rows that lack one, and turns
	on their `apply_tds`, so configuring WHT once on the supplier behaves the same on
	both versions. No-op on v15, where the item rows have no such fields."""
	if not doc.get("items"):
		return
	# v15 guard: if the item row has no WHT field, there is nothing to propagate.
	if not doc.get("items")[0].meta.has_field("tax_withholding_category"):
		return
	if not doc.get("apply_tds"):
		return

	category = doc.get("tax_withholding_category")
	if not category and doc.get("supplier"):
		category = frappe.db.get_value("Supplier", doc.supplier, "tax_withholding_category")
		if category:
			doc.tax_withholding_category = category
	if not category:
		return

	for item in doc.items:
		if not item.get("tax_withholding_category"):
			item.tax_withholding_category = category
		if item.meta.has_field("apply_tds") and not item.get("apply_tds"):
			item.apply_tds = 1
