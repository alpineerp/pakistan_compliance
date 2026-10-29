# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""What a receipt needs to print about FBR: the number, the QR code and the notice."""

import io

import qrcode
import qrcode.image.svg

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
	image = qrcode.make(
		content,
		image_factory=qrcode.image.svg.SvgPathImage,
		box_size=4,
		border=1,
	)
	image.save(buffer)
	svg = buffer.getvalue().decode()
	# qrcode writes an XML declaration; drop it so the markup can be embedded in HTML.
	if svg.startswith("<?xml"):
		svg = svg.split("?>", 1)[-1].lstrip()
	return svg


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
