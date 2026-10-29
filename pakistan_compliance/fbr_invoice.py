# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Map a Sales Invoice to the FBR Digital Invoicing payload and report it.

The field mapping follows the FBR/PRAL DI spec, but several per-item fields
(saleType, sroScheduleNo, the exact rate string) are convention-based and MUST be
confirmed against the live sandbox before production (guardrail #2/#4); they are
marked below. Nothing here fabricates an FBR acceptance: an invoice is only marked
Reported when FBR returns a success status and an invoiceNumber (IRN).
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, getdate

from pakistan_compliance import fbr_client


def _province(address_name):
	"""Pakistan province for an Address (our custom_province field). Empty if none."""
	if not address_name:
		return ""
	return frappe.db.get_value("Address", address_name, "custom_province") or ""


def _invoice_sales_tax_rate(doc):
	"""Best-effort standard sales-tax rate (%) for the invoice: the first
	'On Net Total' tax row with a positive rate. 0 if none."""
	for t in doc.get("taxes", []):
		if t.charge_type == "On Net Total" and flt(t.rate) > 0 and "further" not in (t.description or "").lower():
			return flt(t.rate)
	return 0.0


def _registration_type(ntn, strn):
	return "Registered" if (ntn or strn) else "Unregistered"


def build_invoice_payload(doc):
	"""Build the FBR DI POST payload from a submitted Sales Invoice document."""
	company_ntn = frappe.db.get_value("Company", doc.company, "custom_ntn")
	cust_ntn = frappe.db.get_value("Customer", doc.customer, "custom_ntn")
	cust_strn = frappe.db.get_value("Customer", doc.customer, "custom_strn")
	cust_cnic = frappe.db.get_value("Customer", doc.customer, "custom_cnic")
	settings = frappe.get_cached_doc("Pakistan Tax Settings")

	st_rate = _invoice_sales_tax_rate(doc)

	items = []
	for item in doc.items:
		hs_code = frappe.db.get_value("Item", item.item_code, "custom_hs_code") or ""
		net = flt(item.net_amount)
		sales_tax = flt(net * st_rate / 100.0, 2)
		items.append(
			{
				"hsCode": hs_code,
				"productDescription": item.item_name or item.item_code,
				"rate": f"{st_rate:g}%",
				"uoM": item.uom,
				"quantity": flt(item.qty),
				"valueSalesExcludingST": net,
				"salesTaxApplicable": sales_tax,
				"totalValues": flt(net + sales_tax, 2),
				"salesTaxWithheldAtSource": 0,
				"extraTax": 0,
				"furtherTax": 0,
				"fedPayable": 0,
				"discount": flt(item.get("discount_amount")),
				# Convention-based; verify per item category against the sandbox.
				"saleType": "Goods at standard rate (default)",
				"sroScheduleNo": "",
				"sroItemSerialNo": "",
			}
		)

	payload = {
		"invoiceType": "Debit Note" if doc.get("is_return") else "Sale Invoice",
		"invoiceDate": getdate(doc.posting_date).strftime("%Y-%m-%d"),
		"sellerNTNCNIC": company_ntn or "",
		"sellerBusinessName": doc.company,
		"sellerProvince": _province(doc.get("company_address")),
		"sellerAddress": doc.get("company_address_display") or "",
		"buyerNTNCNIC": cust_ntn or cust_cnic or "",
		"buyerBusinessName": doc.customer_name,
		"buyerProvince": _province(doc.get("customer_address")),
		"buyerAddress": doc.get("address_display") or "",
		"buyerRegistrationType": _registration_type(cust_ntn, cust_strn),
		"invoiceRefNo": doc.get("return_against") or "",
		"items": items,
	}

	# scenarioId is a sandbox-only field selecting an FBR test scenario (SN001..SN028).
	if (settings.get("fbr_environment") or "Sandbox") == "Sandbox" and settings.get("fbr_scenario_id"):
		payload["scenarioId"] = settings.get("fbr_scenario_id")

	return payload


def parse_response(resp):
	"""Extract (irn, ok, error) from an FBR DI response. Success = validationResponse
	statusCode '00' with an invoiceNumber present."""
	vr = (resp or {}).get("validationResponse") or {}
	irn = (resp or {}).get("invoiceNumber") or ""
	ok = str(vr.get("statusCode")) == "00" and bool(irn)
	if ok:
		return irn, True, ""
	# Prefer the top-level error, else aggregate per-item errors.
	error = vr.get("error") or ""
	if not error:
		errs = [
			f"Item {s.get('itemSNo')}: {s.get('error')}"
			for s in (vr.get("invoiceStatuses") or [])
			if s.get("error")
		]
		error = "; ".join(errs)
	return irn, False, error or _("FBR did not accept the invoice.")


def _get_or_create_log(sales_invoice, company):
	name = frappe.db.get_value("FBR Invoice Log", {"sales_invoice": sales_invoice}, "name")
	if name:
		return frappe.get_doc("FBR Invoice Log", name)
	return frappe.get_doc(
		{"doctype": "FBR Invoice Log", "sales_invoice": sales_invoice, "company": company}
	)


@frappe.whitelist()
def report_to_fbr(sales_invoice):
	"""Report a submitted Sales Invoice to FBR Digital Invoicing. Idempotent-ish:
	reuses the invoice's log row. Returns {status, irn, error, log}."""
	frappe.only_for(("Accounts User", "Accounts Manager", "System Manager"))
	doc = frappe.get_doc("Sales Invoice", sales_invoice)
	if doc.docstatus != 1:
		frappe.throw(_("Submit the invoice before reporting it to FBR."))
	frappe.has_permission("Sales Invoice", doc=doc, throw=True)

	settings = frappe.get_cached_doc("Pakistan Tax Settings")
	payload = build_invoice_payload(doc)

	log = _get_or_create_log(doc.name, doc.company)
	log.environment = settings.get("fbr_environment") or "Sandbox"
	log.request_json = json.dumps(payload, indent=2, default=str)

	resp = fbr_client.post_invoice(payload, environment=log.environment)
	log.response_json = json.dumps(resp, indent=2, default=str)

	irn, ok, error = parse_response(resp)
	if ok:
		log.status = "Reported"
		log.fbr_invoice_number = irn
		log.qr_content = irn  # QR encodes the IRN (integrator convention; verify)
		log.reported_on = frappe.utils.now_datetime()
		log.error = ""
	else:
		log.status = "Failed"
		log.error = error

	log.save(ignore_permissions=True)

	if ok:
		# Stamp the invoice so the print format can show the IRN + QR.
		frappe.db.set_value(
			"Sales Invoice", doc.name,
			{"custom_fbr_invoice_number": irn, "custom_fbr_reported": 1},
			update_modified=False,
		)
	frappe.db.commit()  # nosemgrep: intentional persist after a multi-step whitelisted action

	return {"status": log.status, "irn": irn, "error": log.error, "log": log.name}
