# Copyright (c) 2026, Sowaan and contributors
# For license information, please see license.txt

"""Reading FBR POS Settings. Secrets stay in this package: `public()` is all that leaves it."""

import frappe

DOCTYPE = "FBR POS Settings"
MODES = ("Digital Invoicing", "FBR POS", "Both")


def get():
	return frappe.get_cached_doc(DOCTYPE)


def environment():
	return get().environment or "Mock"


def is_mock():
	return environment() == "Mock"


def channels_for(mode):
	"""The FBR systems a sale goes to for a reporting mode: "pos" (FBR POS / IMS) and/or "di"."""
	return {"FBR POS": ["pos"], "Digital Invoicing": ["di"], "Both": ["pos", "di"]}.get(mode or "", [])


def public():
	"""What a till may show: never a token, URL or POS ID."""
	s = get()
	return {
		"environment": environment(),
		"test_mode": is_mock(),
		"notice": s.receipt_notice or "",
		"show_qr": int(bool(s.show_qr)),
		"logo": s.fbr_logo or "",
	}
