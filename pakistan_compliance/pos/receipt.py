# Copyright (c) 2026, Sowaan and contributors
# For license information, please see license.txt

"""What a receipt needs to print about FBR: the number, the QR code and the notice."""

import io

import pyqrcode

import frappe

from pakistan_compliance.pos import settings

FIELDS = (
	"custom_fbr_status",
	"custom_fbr_pos_number",
	"custom_fbr_invoice_number",
	"custom_fbr_qr_payload",
	"custom_fbr_error",
)


def qr_svg(content):
	"""The QR code as an inline SVG string, so a till needs no QR library and it prints offline."""
	if not content:
		return ""
	buffer = io.BytesIO()
	pyqrcode.create(content, error="M").svg(buffer, scale=4, xmldecl=False, svgns=True, quiet_zone=1)
	return buffer.getvalue().decode()


def status_of(doctype, name):
	row = frappe.db.get_value(doctype, name, list(FIELDS), as_dict=True)
	if not row:
		return None
	public = settings.public()
	return {
		"invoice": name,
		"status": row.custom_fbr_status or "",
		"number": row.custom_fbr_pos_number or row.custom_fbr_invoice_number or "",
		"di_number": row.custom_fbr_invoice_number or "",
		"qr_svg": qr_svg(row.custom_fbr_qr_payload) if row.custom_fbr_qr_payload and public["show_qr"] else "",
		"error": (row.custom_fbr_error or "")[:200],
		**{key: public[key] for key in ("test_mode", "notice", "logo")},
	}
