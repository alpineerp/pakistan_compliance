# Copyright (c) 2026, Sowaan and contributors
# For license information, please see license.txt

"""FBR Digital Invoicing for point-of-sale sales.

A Sales Invoice goes through the existing `fbr_invoice.report_to_fbr`, untouched. A POS Invoice
(which that function cannot take) uses the same payload builder, client and response parser on
the POS Invoice itself: each sale is reported when it happens. The Sales Invoice that ERPNext
makes from POS Invoices at shift close is a summary of sales already reported, so it is not
reported again.
"""

import frappe
from frappe import _

from pakistan_compliance import fbr_client, fbr_invoice
from pakistan_compliance.pos import settings
from pakistan_compliance.pos.ims_client import FbrRejected, FbrTransient, mock_number


def post(doc):
	"""Report `doc` (POS Invoice or Sales Invoice). Returns (IRN, request, response)."""
	if settings.is_mock():
		irn = mock_number("MOCKDI", doc.name)
		return irn, None, {"invoiceNumber": irn, "validationResponse": {"statusCode": "00", "status": "Mock: not sent to FBR"}}

	if doc.doctype == "Sales Invoice":
		try:
			result = fbr_invoice.report_to_fbr(doc.name)
		except fbr_client.FBRError as error:
			raise FbrTransient(frappe.utils.strip_html(str(error))[:300]) from None
		if result.get("status") == "Reported" and result.get("irn"):
			return result["irn"], None, result
		raise FbrRejected(result.get("error") or _("FBR did not accept the invoice."))

	payload = fbr_invoice.build_invoice_payload(doc)
	environment = frappe.db.get_single_value("Pakistan Tax Settings", "fbr_environment") or "Sandbox"
	try:
		response = fbr_client.post_invoice(payload, environment=environment)
	except fbr_client.FBRError as error:
		raise FbrTransient(frappe.utils.strip_html(str(error))[:300]) from None
	irn, ok, error = fbr_invoice.parse_response(response)
	if not ok:
		raise FbrRejected(error)
	return irn, payload, response
