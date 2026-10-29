# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Annexure-C (Sales) of the FBR Sales Tax Return.

One row per submitted Sales Invoice in the period: buyer identity + registration
type, value excluding tax, output sales tax, further tax and the invoice total.
The column totals reconcile with the posted sales invoices for the period (the
Phase 6 acceptance)."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not (filters.company and filters.from_date and filters.to_date):
		frappe.throw(_("Company, From Date and To Date are required."))

	invoices = frappe.get_all(
		"Sales Invoice",
		filters={
			"docstatus": 1,
			"company": filters.company,
			"posting_date": ["between", [filters.from_date, filters.to_date]],
		},
		fields=[
			"name", "posting_date", "customer", "customer_name",
			"base_net_total", "base_grand_total", "is_return",
		],
		order_by="posting_date asc, name asc",
	)

	sales_tax, further_tax = _tax_split([d.name for d in invoices])
	buyers = _buyer_details({d.customer for d in invoices})

	data = []
	for inv in invoices:
		b = buyers.get(inv.customer, {})
		data.append(
			{
				"invoice": inv.name,
				"posting_date": inv.posting_date,
				"buyer_name": inv.customer_name,
				"buyer_ntn_cnic": b.get("ntn") or b.get("cnic") or "",
				"registration_type": "Registered" if (b.get("ntn") or b.get("strn")) else "Unregistered",
				"is_return": _("Yes") if inv.is_return else "",
				"value_excl_tax": flt(inv.base_net_total),
				"sales_tax": flt(sales_tax.get(inv.name)),
				"further_tax": flt(further_tax.get(inv.name)),
				"total": flt(inv.base_grand_total),
			}
		)

	return _columns(), data


def _tax_split(invoice_names):
	"""Return ({invoice: output sales tax}, {invoice: further tax}) from the tax rows."""
	sales_tax, further_tax = {}, {}
	if not invoice_names:
		return sales_tax, further_tax
	rows = frappe.get_all(
		"Sales Taxes and Charges",
		filters={"parenttype": "Sales Invoice", "parent": ["in", invoice_names]},
		fields=["parent", "description", "account_head", "base_tax_amount"],
	)
	for r in rows:
		text = f"{r.description or ''} {r.account_head or ''}".lower()
		if "withholding" in text:
			continue  # WHT is not part of the sales-tax annexure
		if "further" in text:
			further_tax[r.parent] = flt(further_tax.get(r.parent)) + flt(r.base_tax_amount)
		else:
			sales_tax[r.parent] = flt(sales_tax.get(r.parent)) + flt(r.base_tax_amount)
	return sales_tax, further_tax


def _buyer_details(customers):
	out = {}
	for c in customers:
		if not c:
			continue
		ntn, strn, cnic = frappe.db.get_value(
			"Customer", c, ["custom_ntn", "custom_strn", "custom_cnic"]
		) or (None, None, None)
		out[c] = {"ntn": ntn, "strn": strn, "cnic": cnic}
	return out


def _columns():
	return [
		{"label": _("Invoice"), "fieldname": "invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 160},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 90},
		{"label": _("Buyer"), "fieldname": "buyer_name", "fieldtype": "Data", "width": 200},
		{"label": _("NTN / CNIC"), "fieldname": "buyer_ntn_cnic", "fieldtype": "Data", "width": 120},
		{"label": _("Type"), "fieldname": "registration_type", "fieldtype": "Data", "width": 100},
		{"label": _("Return"), "fieldname": "is_return", "fieldtype": "Data", "width": 60},
		{"label": _("Value Excl. Tax"), "fieldname": "value_excl_tax", "fieldtype": "Currency", "width": 130},
		{"label": _("Sales Tax"), "fieldname": "sales_tax", "fieldtype": "Currency", "width": 120},
		{"label": _("Further Tax"), "fieldname": "further_tax", "fieldtype": "Currency", "width": 110},
		{"label": _("Total"), "fieldname": "total", "fieldtype": "Currency", "width": 130},
	]
