# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Withholding Tax Certificate (Phase 4).

A certificate issued by the company (withholding agent) to a supplier, listing the
income tax withheld from that supplier over a period, for the supplier's own tax
filing. Deductions are sourced from GL entries against the company's withholding
tax accounts, which works on both ERPNext v15 (WHT posted as a tax row) and v16
(WHT posted via a Tax Withholding Entry) because both credit the same account.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


def _wht_accounts(company):
	"""The company's withholding-tax accounts: every account referenced by a Tax
	Withholding Category for this company (covers whatever the customer configured),
	which for our seeded setup is 'Withholding Tax Payable'."""
	accounts = set(
		frappe.get_all(
			"Tax Withholding Account",
			filters={"company": company},
			pluck="account",
		)
	)
	return {a for a in accounts if a}


def _voucher_supplier(voucher_type, voucher_no):
	"""The supplier a WHT voucher belongs to. The WHT account's GL line carries no
	party (that sits on the payable line), so the certificate matches on the voucher's
	own supplier instead."""
	if voucher_type in ("Purchase Invoice", "Purchase Order"):
		return frappe.db.get_value(voucher_type, voucher_no, "supplier")
	if voucher_type == "Payment Entry":
		party_type, party = frappe.db.get_value(voucher_type, voucher_no, ["party_type", "party"])
		return party if party_type == "Supplier" else None
	return None


def _voucher_gross(voucher_type, voucher_no):
	"""Best-effort gross (pre-tax) amount the withholding was computed on."""
	field = {
		"Purchase Invoice": "base_net_total",
		"Purchase Order": "base_net_total",
		"Payment Entry": "base_paid_amount",
		"Journal Entry": "total_debit",
	}.get(voucher_type)
	if not field:
		return 0
	return flt(frappe.db.get_value(voucher_type, voucher_no, field))


def _section_from_category(category):
	"""'Pakistan WHT 153(1)(b) Services (Filer)' -> '153(1)(b)'."""
	if not category:
		return ""
	if not category.startswith("Pakistan WHT "):
		return category
	return category[len("Pakistan WHT "):].split(" ")[0]


def _voucher_section(voucher_type, voucher_no, supplier=None):
	"""Best-effort income-tax section for a WHT voucher. Tries, in order: the v16
	Tax Withholding Entry, the voucher's own WHT category, then the supplier's
	assigned category. Empty if none can be resolved."""
	if frappe.db.exists("DocType", "Tax Withholding Entry"):
		category = frappe.db.get_value(
			"Tax Withholding Entry",
			{"withholding_doctype": voucher_type, "withholding_name": voucher_no},
			"tax_withholding_category",
		)
		if category:
			return _section_from_category(category)

	meta = frappe.get_meta(voucher_type)
	if meta.get_field("tax_withholding_category"):
		category = frappe.db.get_value(voucher_type, voucher_no, "tax_withholding_category")
		if category:
			return _section_from_category(category)

	if supplier:
		return _section_from_category(
			frappe.db.get_value("Supplier", supplier, "tax_withholding_category")
		)
	return ""


class WithholdingTaxCertificate(Document):
	def validate(self):
		if self.from_date and self.to_date and self.from_date > self.to_date:
			frappe.throw(_("From Date cannot be after To Date."))
		self._compute_totals()

	def _compute_totals(self):
		self.total_gross = sum(flt(d.gross_amount) for d in self.deductions)
		self.total_tax = sum(flt(d.tax_amount) for d in self.deductions)

	@frappe.whitelist()
	def fetch_deductions(self):
		"""Populate the deductions table from GL entries against the company's WHT
		accounts for this supplier and period. Idempotent: replaces the table."""
		if not (self.company and self.supplier and self.from_date and self.to_date):
			frappe.throw(_("Set Company, Supplier, From Date and To Date first."))

		accounts = _wht_accounts(self.company)
		if not accounts:
			frappe.throw(
				_("No withholding tax accounts found for {0}. Run 'Set up Withholding Tax' on Pakistan Tax Settings first.").format(
					self.company
				)
			)

		# The WHT account's GL line carries no party, so we cannot filter by supplier
		# in the query; we fetch all WHT postings in the period and match each
		# voucher's own supplier below.
		gl_rows = frappe.get_all(
			"GL Entry",
			filters={
				"company": self.company,
				"account": ["in", list(accounts)],
				"posting_date": ["between", [self.from_date, self.to_date]],
				"is_cancelled": 0,
			},
			fields=["posting_date", "voucher_type", "voucher_no", "credit", "debit"],
			order_by="posting_date asc, voucher_no asc",
		)

		self.set("deductions", [])
		section_filter = (self.section_filter or "").strip()
		for r in gl_rows:
			tax = flt(r.credit) - flt(r.debit)  # net credit to the WHT account = withheld
			if tax <= 0:
				continue
			if _voucher_supplier(r.voucher_type, r.voucher_no) != self.supplier:
				continue
			section = _voucher_section(r.voucher_type, r.voucher_no, self.supplier)
			if section_filter and section_filter not in section:
				continue
			gross = _voucher_gross(r.voucher_type, r.voucher_no)
			self.append(
				"deductions",
				{
					"date": r.posting_date,
					"voucher_type": r.voucher_type,
					"voucher_no": r.voucher_no,
					"section": section,
					"gross_amount": gross,
					"rate": (tax / gross * 100) if gross else 0,
					"tax_amount": tax,
				},
			)

		self._compute_totals()
		return len(self.deductions)
