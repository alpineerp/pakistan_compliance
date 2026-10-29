# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Annexure-A (Purchases) of the FBR Sales Tax Return.

One row per submitted Purchase Invoice in the period: supplier identity, value
excluding tax, input sales tax and the invoice total. Withholding-tax rows are
excluded (they belong to the income-tax withholding statement, not the sales-tax
annexure). Column totals reconcile with the posted purchase invoices for the
period."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not (filters.company and filters.from_date and filters.to_date):
		frappe.throw(_("Company, From Date and To Date are required."))

	invoices = frappe.get_all(
		"Purchase Invoice",
		filters={
			"docstatus": 1,
			"company": filters.company,
			"posting_date": ["between", [filters.from_date, filters.to_date]],
		},
		fields=[
			"name", "posting_date", "supplier", "supplier_name", "bill_no",
			"base_net_total", "base_grand_total", "is_return",
		],
		order_by="posting_date asc, name asc",
	)

	input_tax, further_tax = _tax_split([d.name for d in invoices])
	suppliers = _supplier_details({d.supplier for d in invoices})

	data = []
	for inv in invoices:
		s = suppliers.get(inv.supplier, {})
		data.append(
			{
				"invoice": inv.name,
				"bill_no": inv.bill_no,
				"posting_date": inv.posting_date,
				"supplier_name": inv.supplier_name,
				"supplier_ntn_cnic": s.get("ntn") or s.get("cnic") or "",
				"registration_type": "Registered" if (s.get("ntn") or s.get("strn")) else "Unregistered",
				"is_return": _("Yes") if inv.is_return else "",
				"value_excl_tax": flt(inv.base_net_total),
				"input_tax": flt(input_tax.get(inv.name)),
				"further_tax": flt(further_tax.get(inv.name)),
				"total": flt(inv.base_grand_total),
			}
		)

	return _columns(), data


def _tax_split(invoice_names):
	"""({invoice: input sales tax}, {invoice: further tax}); excludes WHT (Deduct)."""
	input_tax, further_tax = {}, {}
	if not invoice_names:
		return input_tax, further_tax
	rows = frappe.get_all(
		"Purchase Taxes and Charges",
		filters={"parenttype": "Purchase Invoice", "parent": ["in", invoice_names]},
		fields=["parent", "description", "account_head", "base_tax_amount", "add_deduct_tax"],
	)
	for r in rows:
		text = f"{r.description or ''} {r.account_head or ''}".lower()
		if r.add_deduct_tax == "Deduct" or "withholding" in text:
			continue  # income-tax withholding, not sales-tax input
		if "further" in text:
			further_tax[r.parent] = flt(further_tax.get(r.parent)) + flt(r.base_tax_amount)
		else:
			input_tax[r.parent] = flt(input_tax.get(r.parent)) + flt(r.base_tax_amount)
	return input_tax, further_tax


def _supplier_details(suppliers):
	out = {}
	for s in suppliers:
		if not s:
			continue
		ntn, strn, cnic = frappe.db.get_value(
			"Supplier", s, ["custom_ntn", "custom_strn", "custom_cnic"]
		) or (None, None, None)
		out[s] = {"ntn": ntn, "strn": strn, "cnic": cnic}
	return out


def _columns():
	return [
		{"label": _("Invoice"), "fieldname": "invoice", "fieldtype": "Link", "options": "Purchase Invoice", "width": 160},
		{"label": _("Supplier Bill No"), "fieldname": "bill_no", "fieldtype": "Data", "width": 120},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 90},
		{"label": _("Supplier"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 200},
		{"label": _("NTN / CNIC"), "fieldname": "supplier_ntn_cnic", "fieldtype": "Data", "width": 120},
		{"label": _("Type"), "fieldname": "registration_type", "fieldtype": "Data", "width": 100},
		{"label": _("Return"), "fieldname": "is_return", "fieldtype": "Data", "width": 60},
		{"label": _("Value Excl. Tax"), "fieldname": "value_excl_tax", "fieldtype": "Currency", "width": 130},
		{"label": _("Input Sales Tax"), "fieldname": "input_tax", "fieldtype": "Currency", "width": 130},
		{"label": _("Further Tax"), "fieldname": "further_tax", "fieldtype": "Currency", "width": 110},
		{"label": _("Total"), "fieldname": "total", "fieldtype": "Currency", "width": 130},
	]
