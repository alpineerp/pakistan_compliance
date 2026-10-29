# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Reporting POS sales to FBR without ever holding up a sale.

A submitted sale is marked Pending and reported by a background job right after it is
committed. Whatever goes wrong (FBR down, server offline, bad token) only moves the sale to a
later retry: a scheduled job tries due ones again with growing waits, and after `max_attempts`
the sale is marked Failed so a manager can fix the cause and retry it.
"""

import json

import frappe
from frappe.utils import add_to_date, cint, now_datetime

from pakistan_compliance.pos import digital, ims_client, settings
from pakistan_compliance.pos.ims_client import FbrRejected, FbrTransient

# seconds to wait before the next try, by number of tries so far (the last value repeats)
BACKOFF = (30, 60, 120, 300, 600, 1200, 1800, 3600)
CLAIM_TIMEOUT_MINUTES = 15  # a job that died while Sending is picked up again after this
BATCH = 50
DOCTYPES = ("POS Invoice", "Sales Invoice")


def wait_seconds(tries):
	return BACKOFF[min(max(tries, 1) - 1, len(BACKOFF) - 1)]


def enqueue(doctype, name, mode):
	"""Queue a submitted sale for the FBR systems `mode` asks for. Returns the channels."""
	if doctype not in DOCTYPES:
		frappe.throw(f"FBR reporting handles {', '.join(DOCTYPES)}, not {doctype}.")
	channels = settings.channels_for(mode)
	if not channels:
		return []
	frappe.db.set_value(
		doctype,
		name,
		{
			"custom_fbr_status": "Pending",
			"custom_fbr_channels": ",".join(channels),
			"custom_fbr_attempts": 0,
			"custom_fbr_next_attempt": now_datetime(),
			"custom_fbr_error": "",
			"custom_fbr_pos_number": "",
			"custom_fbr_qr_payload": "",
		},
		update_modified=False,
	)
	frappe.enqueue(
		"pakistan_compliance.pos.queue.process",
		queue="short",
		enqueue_after_commit=True,
		doctype=doctype,
		name=name,
	)
	return channels


def requeue(doctype, name):
	"""A manager's Retry: back to Pending with a fresh count."""
	frappe.db.set_value(
		doctype,
		name,
		{
			"custom_fbr_status": "Pending",
			"custom_fbr_attempts": 0,
			"custom_fbr_next_attempt": now_datetime(),
			"custom_fbr_error": "",
		},
		update_modified=False,
	)
	frappe.enqueue(
		"pakistan_compliance.pos.queue.process", queue="short", enqueue_after_commit=True, doctype=doctype, name=name
	)


def process(doctype, name):
	"""Report one sale to the channels it still needs. Safe to call twice."""
	if doctype not in DOCTYPES:
		return
	previous = frappe.session.user
	frappe.set_user("Administrator")
	try:
		_process(doctype, name)
	finally:
		frappe.set_user(previous)


def _process(doctype, name):
	# claim the sale so two workers never report it at the same time
	state = frappe.db.get_value(
		doctype, name, ["custom_fbr_status", "docstatus", "custom_fbr_next_attempt"], as_dict=True, for_update=True
	)
	if not state or state.docstatus != 1 or state.custom_fbr_status not in ("Pending", "Sending"):
		return
	if state.custom_fbr_status == "Sending":
		# another worker has it, unless that worker died a while ago
		claimed = state.custom_fbr_next_attempt
		if claimed and claimed > add_to_date(now_datetime(), minutes=-CLAIM_TIMEOUT_MINUTES):
			return
	frappe.db.set_value(
		doctype, name, {"custom_fbr_status": "Sending", "custom_fbr_next_attempt": now_datetime()}, update_modified=False
	)
	frappe.db.commit()  # nosemgrep: release the row lock before the slow network call

	doc = frappe.get_doc(doctype, name)
	channels = [c for c in (doc.custom_fbr_channels or "").split(",") if c]
	tries = cint(doc.custom_fbr_attempts) + 1
	values = {}
	channel = channels[0] if channels else "pos"
	try:
		for channel in list(channels):
			if channel == "pos":
				number, request, response = ims_client.post(doc)
				values["custom_fbr_pos_number"] = number
				values["custom_fbr_qr_payload"] = number
			else:
				number, request, response = digital.post(doc)
				values.update(custom_fbr_invoice_number=number, custom_fbr_reported=1)
				values.setdefault("custom_fbr_qr_payload", doc.custom_fbr_qr_payload or number)
			channels.remove(channel)
			_log(doc, channel, "Reported", tries, number, request, response)
		values.update(custom_fbr_status="Reported", custom_fbr_error="")
	except FbrRejected as error:
		_log(doc, channel, "Failed", tries, error=str(error))
		values.update(custom_fbr_status="Failed", custom_fbr_error=str(error)[:500])
	except FbrTransient as error:
		if tries >= max(1, cint(settings.get().max_attempts)):
			_log(doc, channel, "Failed", tries, error=str(error))
			values.update(custom_fbr_status="Failed", custom_fbr_error=str(error)[:500])
		else:
			_log(doc, channel, "Retrying", tries, error=str(error))
			values.update(
				custom_fbr_status="Pending",
				custom_fbr_next_attempt=add_to_date(now_datetime(), seconds=wait_seconds(tries)),
				custom_fbr_error=str(error)[:500],
			)
	except Exception:
		# a bug or a data problem: keep the sale, tell the manager, never raise into the till
		frappe.log_error(frappe.get_traceback(), "FBR POS reporting failed")
		values.update(custom_fbr_status="Failed", custom_fbr_error="Unexpected error, see the Error Log.")

	values["custom_fbr_attempts"] = tries
	values["custom_fbr_channels"] = ",".join(channels)
	frappe.db.set_value(doctype, name, values, update_modified=False)
	frappe.db.commit()  # nosemgrep: persist the outcome of the external call


def _log(doc, channel, status, tries, number="", request=None, response=None, error=""):
	"""One FBR POS Log row per try, for the audit trail. Never fails the reporting."""
	try:
		frappe.get_doc(
			{
				"doctype": "FBR POS Log",
				"document_type": doc.doctype,
				"document": doc.name,
				"channel": "FBR POS" if channel == "pos" else "Digital Invoicing",
				"status": status,
				"environment": settings.environment(),
				"attempt": tries,
				"fbr_invoice_number": number,
				"request_json": json.dumps(request, indent=2, default=str) if request else "",
				"response_json": json.dumps(response, indent=2, default=str) if response else "",
				"error": error,
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "FBR POS Log could not be written")


def retry_due():
	"""Scheduler (every minute): sales waiting for a retry, and ones stuck while Sending."""
	now = now_datetime()
	for doctype in DOCTYPES:
		rows = frappe.get_all(
			doctype,
			filters=[["docstatus", "=", 1], ["custom_fbr_status", "in", ["Pending", "Sending"]]],
			or_filters=[
				["custom_fbr_next_attempt", "<=", now],
				["custom_fbr_next_attempt", "is", "not set"],
				["custom_fbr_status", "=", "Sending"],
			],
			pluck="name",
			order_by="creation asc",
			limit=BATCH,
		)
		for name in rows:
			# process() itself skips a sale another worker is still sending
			process(doctype, name)
