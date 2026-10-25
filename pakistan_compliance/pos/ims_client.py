# Copyright (c) 2026, Sowaan and contributors
# For license information, please see license.txt

"""FBR POS (IMS, Tier-1 retailers): each sale is posted to FBR, which answers with a fiscal
invoice number that is printed on the receipt.

TO CONFIRM AGAINST FBR'S DOCUMENTATION: the payload field names, the payment-mode and
invoice-type codes, the response fields and the success code below follow what is publicly
known about the FBR POS integration, but no real FBR POS credentials or sandbox were available
when this was written, so none of it has been checked against the live service. It is kept in
this one module so a correction is a change here and nowhere else. The service URL is
deliberately not defaulted: it comes from FBR POS Settings.
"""

import hashlib

import requests

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime

from pakistan_compliance.pos import settings


class FbrTransient(Exception):
	"""FBR could not be reached or was busy: try again later."""


class FbrRejected(Exception):
	"""FBR (or the setup) refused this invoice: retrying the same data will not help."""


# FBR POS payment mode codes (to confirm)
PAYMENT_MODES = {"Cash": 1, "Bank": 2, "Card": 2, "Gift": 3, "Loyalty": 4}
MIXED = 5
INVOICE_NEW, INVOICE_DEBIT, INVOICE_CREDIT = 1, 2, 3  # (to confirm)


def _tariff_code(item_code):
	"""HS / PCT code: the Pakistan HS Code field, else ERPNext's customs tariff number."""
	meta = frappe.get_meta("Item")
	for fieldname in ("custom_hs_code", "customs_tariff_number"):
		if meta.has_field(fieldname):
			value = frappe.db.get_value("Item", item_code, fieldname)
			if value:
				return value
	return ""


def _tax_rate(doc):
	"""Standard sales tax rate (%) of the sale: the first positive 'On Net Total' row."""
	for tax in doc.get("taxes") or []:
		if tax.charge_type == "On Net Total" and flt(tax.rate) > 0 and "further" not in (tax.description or "").lower():
			return flt(tax.rate)
	return 0.0


def _payment_mode(doc):
	modes = {row.mode_of_payment for row in doc.get("payments") or [] if flt(row.amount)}
	if len(modes) > 1:
		return MIXED
	if not modes:
		return PAYMENT_MODES["Cash"]
	mode_type = frappe.db.get_value("Mode of Payment", next(iter(modes)), "type") or "Cash"
	return PAYMENT_MODES.get(mode_type, PAYMENT_MODES["Cash"])


def build_payload(doc):
	"""The FBR POS request for a saved POS Invoice / Sales Invoice."""
	is_return = bool(doc.get("is_return"))
	rate = _tax_rate(doc)
	invoice_type = INVOICE_CREDIT if is_return else INVOICE_NEW
	items = []
	for row in doc.items:
		net = abs(flt(row.net_amount))
		tax = flt(net * rate / 100.0, 2)
		items.append(
			{
				"ItemCode": row.item_code,
				"ItemName": row.item_name or row.item_code,
				"Quantity": abs(flt(row.qty)),
				"PCTCode": _tariff_code(row.item_code),
				"TaxRate": rate,
				"SaleValue": net,
				"TotalAmount": flt(net + tax, 2),
				"TaxCharged": tax,
				"Discount": abs(flt(row.get("discount_amount"))),
				"FurtherTax": 0,
				"InvoiceType": invoice_type,
				"RefUSIN": doc.get("return_against") or None,
			}
		)
	buyer = frappe.db.get_value("Customer", doc.customer, ["customer_name", "mobile_no"], as_dict=True) or {}
	customer_meta = frappe.get_meta("Customer")
	buyer_ntn = frappe.db.get_value("Customer", doc.customer, "custom_ntn") if customer_meta.has_field("custom_ntn") else ""
	return {
		"InvoiceNumber": "",
		"POSID": settings.get().pos_id or "",
		"USIN": doc.name,
		"DateTime": get_datetime(f"{doc.posting_date} {doc.posting_time}").strftime("%Y-%m-%d %H:%M:%S"),
		"BuyerName": buyer.get("customer_name") or doc.customer,
		"BuyerNTN": buyer_ntn or "",
		"BuyerCNIC": "",
		"BuyerPhoneNumber": buyer.get("mobile_no") or "",
		"TotalBillAmount": abs(flt(doc.rounded_total or doc.grand_total)),
		"TotalQuantity": abs(flt(doc.total_qty)),
		"TotalSaleValue": abs(flt(doc.net_total)),
		"TotalTaxCharged": abs(flt(doc.total_taxes_and_charges)),
		"Discount": abs(flt(doc.get("discount_amount"))),
		"FurtherTax": 0,
		"PaymentMode": _payment_mode(doc),
		"RefUSIN": doc.get("return_against") or None,
		"InvoiceType": invoice_type,
		"Items": items,
	}


def parse_response(body):
	"""(fiscal invoice number, error). An invoice is only reported with a number from FBR."""
	body = body or {}
	number = str(body.get("InvoiceNumber") or "").strip()
	code = str(body.get("Code") if body.get("Code") is not None else "100")
	if number and code == "100":
		return number, ""
	return "", str(body.get("Response") or body.get("Message") or _("FBR did not accept the invoice."))[:500]


def mock_number(prefix, name):
	"""A made-up number, stable per invoice so a retry can never issue a second one."""
	return f"{prefix}-{hashlib.sha1(name.encode()).hexdigest()[:10].upper()}"


def post(doc):
	"""Report one invoice. Returns (fiscal number, request payload, response body);
	raises FbrTransient or FbrRejected."""
	s = settings.get()
	payload = build_payload(doc)

	if settings.is_mock():
		number = mock_number("MOCK", doc.name)
		return number, payload, {"InvoiceNumber": number, "Code": "100", "Response": "Mock: not sent to FBR"}

	if not (s.pos_base_url and s.pos_id):
		raise FbrRejected(_("Set the FBR POS Service URL and POS ID in FBR POS Settings."))
	token = s.get_password("pos_token", raise_exception=False)
	if not token:
		raise FbrRejected(_("Set the FBR POS Token in FBR POS Settings."))

	try:
		response = requests.post(
			s.pos_base_url,
			json=payload,
			headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
			timeout=cint(s.request_timeout) or 20,
		)
	except requests.RequestException as error:
		# built from the exception type only: the text can echo request headers (the token)
		raise FbrTransient(_("Could not reach FBR ({0}).").format(type(error).__name__)) from None

	if response.status_code in (401, 403):
		# the token is wrong or expired: an admin must fix it, so keep the sale queued
		raise FbrTransient(_("FBR refused the token ({0}).").format(response.status_code))
	if response.status_code == 429 or response.status_code >= 500:
		raise FbrTransient(_("FBR is busy or down ({0}).").format(response.status_code))
	try:
		body = response.json()
	except ValueError:
		raise FbrTransient(_("FBR answered with something that is not JSON ({0}).").format(response.status_code)) from None

	number, error = parse_response(body)
	if not number:
		raise FbrRejected(error)
	return number, payload, body
