# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Withholding Tax Statement (Income Tax Ordinance 2001, section 165).

Income tax withheld from suppliers over a period (usually a quarter), sourced from
GL entries against the company's withholding-tax accounts, so it works on both
ERPNext v15 (WHT as a tax row) and v16 (WHT via Tax Withholding Entry) - both
credit the same account. One row per withholding voucher; the tax column totals to
the tax deposited for the period."""

import frappe
from frappe import _
from frappe.utils import flt

from pakistan_compliance.pakistan_compliance.doctype.withholding_tax_certificate.withholding_tax_certificate import (
	_voucher_gross,
	_voucher_section,
	_voucher_supplier,
	_wht_accounts,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not (filters.company and filters.from_date and filters.to_date):
		frappe.throw(_("Company, From Date and To Date are required."))

	accounts = _wht_accounts(filters.company)
	if not accounts:
		frappe.throw(
			_("No withholding tax accounts found for {0}. Run 'Set up Withholding Tax' first.").format(
				filters.company
			)
		)

	gl_rows = frappe.get_all(
		"GL Entry",
		filters={
			"company": filters.company,
			"account": ["in", list(accounts)],
			"posting_date": ["between", [filters.from_date, filters.to_date]],
			"is_cancelled": 0,
		},
		fields=["posting_date", "voucher_type", "voucher_no", "credit", "debit"],
		order_by="posting_date asc, voucher_no asc",
	)

	ntn_cache = {}
	data = []
	for r in gl_rows:
		tax = flt(r.credit) - flt(r.debit)
		if tax <= 0:
			continue
		supplier = _voucher_supplier(r.voucher_type, r.voucher_no)
		if not supplier or (filters.supplier and supplier != filters.supplier):
			continue
		if supplier not in ntn_cache:
			ntn_cache[supplier] = frappe.db.get_value(
				"Supplier", supplier, ["supplier_name", "custom_ntn", "custom_cnic"], as_dict=True
			) or frappe._dict()
		s = ntn_cache[supplier]
		data.append(
			{
				"supplier": supplier,
				"supplier_name": s.get("supplier_name") or supplier,
				"ntn_cnic": s.get("custom_ntn") or s.get("custom_cnic") or "",
				"section": _voucher_section(r.voucher_type, r.voucher_no, supplier),
				"posting_date": r.posting_date,
				"voucher_type": r.voucher_type,
				"voucher_no": r.voucher_no,
				"gross_amount": _voucher_gross(r.voucher_type, r.voucher_no),
				"tax_withheld": tax,
			}
		)

	data.sort(key=lambda d: (d["supplier_name"], d["posting_date"]))
	return _columns(), data


def _columns():
	return [
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
		{"label": _("Name"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 180},
		{"label": _("NTN / CNIC"), "fieldname": "ntn_cnic", "fieldtype": "Data", "width": 120},
		{"label": _("Section"), "fieldname": "section", "fieldtype": "Data", "width": 100},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 90},
		{"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 120},
		{"label": _("Voucher"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 150},
		{"label": _("Gross Amount"), "fieldname": "gross_amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Tax Withheld"), "fieldname": "tax_withheld", "fieldtype": "Currency", "width": 130},
	]
