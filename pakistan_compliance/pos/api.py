# Copyright (c) 2026, Sowaan and contributors
# For license information, please see license.txt

"""Entry points for a point of sale (alpine_pos) and the FBR POS Settings form.

The caller owns the rules about who may sell and which sale is reported; these functions only
queue, read and retry. They are whitelisted for the form buttons, and callable as plain Python
from another app that has already checked its own user.
"""

import frappe
from frappe import _

from pakistan_compliance.pos import queue, receipt, settings

ROLES = ("Accounts User", "Accounts Manager", "System Manager")


@frappe.whitelist(methods=["POST"])
def enqueue_report(doctype, name, mode):
	"""Queue a submitted POS Invoice / Sales Invoice for FBR. `mode` is "Digital Invoicing",
	"FBR POS" or "Both". Returns the channels queued (empty when nothing applies)."""
	frappe.only_for(ROLES)
	if frappe.db.get_value(doctype, name, "docstatus") != 1:
		frappe.throw(_("Submit the invoice before reporting it to FBR."))
	return queue.enqueue(doctype, name, mode)


@frappe.whitelist()
def receipt_status(doctype, name):
	"""FBR number, QR (SVG) and state of one sale, for printing."""
	frappe.only_for(ROLES)
	return receipt.status_of(doctype, name)


@frappe.whitelist(methods=["POST"])
def retry(doctype, name):
	"""Report a Failed (or waiting) sale again."""
	frappe.only_for(ROLES)
	current = frappe.db.get_value(doctype, name, "custom_fbr_status")
	if current not in ("Failed", "Pending"):
		frappe.throw(_("{0} is {1} for FBR, nothing to retry.").format(name, current or _("not queued")))
	queue.requeue(doctype, name)
	return {"queued": 1}


@frappe.whitelist(methods=["POST"])
def retry_failed():
	"""Queue every Failed sale again (button on FBR POS Settings)."""
	frappe.only_for(("System Manager", "Accounts Manager"))
	count = 0
	for doctype in queue.DOCTYPES:
		for name in frappe.get_all(doctype, filters={"custom_fbr_status": "Failed", "docstatus": 1}, pluck="name", limit=500):
			queue.requeue(doctype, name)
			count += 1
	return count


@frappe.whitelist()
def public_settings():
	"""Non-secret settings for a till."""
	frappe.only_for(ROLES)
	return settings.public()


@frappe.whitelist()
def check_settings():
	"""Describe what reporting would do right now, without sending a sale (settings form button)."""
	frappe.only_for(("System Manager", "Accounts Manager"))
	s = settings.get()
	if settings.is_mock():
		return _("Mock mode: nothing is sent to FBR. Sales get numbers starting MOCK-.")
	problems = []
	if not s.pos_base_url:
		problems.append(_("FBR POS Service URL is empty."))
	if not s.pos_id:
		problems.append(_("POS ID is empty."))
	if not s.get_password("pos_token", raise_exception=False):
		problems.append(_("FBR POS Token is empty."))
	if not frappe.get_cached_doc("Pakistan Tax Settings").get_password("fbr_token", raise_exception=False):
		problems.append(_("Digital Invoicing: the integrator token on Pakistan Tax Settings is empty."))
	if problems:
		return "<br>".join(problems)
	return _("Settings are complete for {0}. Make one sale to see FBR's answer.").format(s.environment)
