# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Point-of-sale sales waiting for, or refused by, FBR: what a supervisor looks at when a sale
shows "FBR number pending" for too long. Each Failed or Pending row has a Retry button (see the
.js file), which queues it again through pakistan_compliance.pos.api.retry."""

import frappe
from frappe import _
from frappe.utils import flt

DOCTYPES = ("POS Invoice", "Sales Invoice")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return columns(), data(filters)


def columns():
	return [
		{"label": _("Invoice"), "fieldname": "name", "fieldtype": "Dynamic Link", "options": "doctype", "width": 180},
		{"label": _("Type"), "fieldname": "doctype", "fieldtype": "Data", "width": 110},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Customer"), "fieldname": "customer_name", "fieldtype": "Data", "width": 160},
		{"label": _("Total"), "fieldname": "grand_total", "fieldtype": "Currency", "width": 110},
		{"label": _("FBR Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": _("Tries"), "fieldname": "attempts", "fieldtype": "Int", "width": 60},
		{"label": _("Next Try"), "fieldname": "next_attempt", "fieldtype": "Datetime", "width": 150},
		{"label": _("FBR Message"), "fieldname": "error", "fieldtype": "Data", "width": 320},
		{"label": _("Retry"), "fieldname": "retry", "fieldtype": "Data", "width": 80},
	]


def data(filters):
	wanted = {
		"Failed": ["Failed"],
		"Pending": ["Pending", "Sending"],
		"Reported": ["Reported"],
	}.get(filters.status) or ["Failed", "Pending", "Sending"]

	rows = []
	for doctype in DOCTYPES:
		meta = frappe.get_meta(doctype)
		if not meta.has_field("custom_fbr_status"):
			continue
		record_filters = {"docstatus": 1, "custom_fbr_status": ("in", wanted)}
		if filters.company:
			record_filters["company"] = filters.company
		if filters.from_date and filters.to_date:
			record_filters["posting_date"] = ("between", [filters.from_date, filters.to_date])
		if doctype == "Sales Invoice":
			# the shift's merged invoice repeats every sale in it; the sales themselves are listed
			record_filters["is_consolidated"] = 0
			record_filters["is_pos"] = 1
		for row in frappe.get_all(
			doctype,
			filters=record_filters,
			fields=[
				"name", "posting_date", "customer_name", "grand_total", "custom_fbr_status",
				"custom_fbr_attempts", "custom_fbr_next_attempt", "custom_fbr_error",
			],
			order_by="posting_date desc, creation desc",
			limit=1000,
		):
			rows.append(
				{
					"doctype": doctype,
					"name": row.name,
					"posting_date": row.posting_date,
					"customer_name": row.customer_name,
					"grand_total": flt(row.grand_total),
					"status": row.custom_fbr_status,
					"attempts": row.custom_fbr_attempts,
					"next_attempt": row.custom_fbr_next_attempt,
					"error": row.custom_fbr_error,
					"retry": row.custom_fbr_status if row.custom_fbr_status in ("Failed", "Pending") else "",
				}
			)
	rows.sort(key=lambda r: (str(r["posting_date"]), r["name"]), reverse=True)
	return rows
