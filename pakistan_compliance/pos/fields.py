# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Custom Fields for FBR reporting of point-of-sale sales (merged into install.CUSTOM_FIELDS).

POS Invoice gets the same IRN fields Sales Invoice already has, plus the queue state both need
for the FBR POS (IMS) channel. All read-only: only the reporting code writes them.
"""

_RO = {"read_only": 1, "no_copy": 1, "print_hide": 1, "translatable": 0}

_QUEUE_FIELDS = [
	{
		# Pending -> Sending -> Reported, or Failed (gave up, or FBR refused it)
		"fieldname": "custom_fbr_status",
		"fieldtype": "Select",
		"label": "FBR Status",
		"options": "\nPending\nSending\nReported\nFailed",
		"insert_after": "custom_fbr_reported",
		"in_standard_filter": 1,
		**_RO,
	},
	{
		"fieldname": "custom_fbr_pos_number",
		"fieldtype": "Data",
		"label": "FBR POS Invoice Number",
		"insert_after": "custom_fbr_status",
		"description": "Fiscal invoice number returned by the FBR POS (IMS) service.",
		**_RO,
	},
	{"fieldname": "custom_fbr_error", "fieldtype": "Small Text", "label": "FBR Message", "insert_after": "custom_fbr_pos_number", **_RO},
	{"fieldname": "custom_fbr_qr_payload", "fieldtype": "Small Text", "label": "FBR QR Content", "insert_after": "custom_fbr_error", **_RO},
	{"fieldname": "custom_fbr_attempts", "fieldtype": "Int", "label": "FBR Tries", "insert_after": "custom_fbr_qr_payload", "default": "0", **_RO},
	{"fieldname": "custom_fbr_next_attempt", "fieldtype": "Datetime", "label": "FBR Next Try", "insert_after": "custom_fbr_attempts", **_RO},
	{
		# comma list of channels still to report ("pos", "di"); empty when nothing is left
		"fieldname": "custom_fbr_channels",
		"fieldtype": "Data",
		"label": "FBR Channels Left",
		"insert_after": "custom_fbr_next_attempt",
		"hidden": 1,
		**_RO,
	},
]

POS_CUSTOM_FIELDS = {
	"POS Invoice": [
		{
			"fieldname": "custom_fbr_invoice_number",
			"fieldtype": "Data",
			"label": "FBR Invoice Number (IRN)",
			"insert_after": "customer_name",
			"description": "Invoice Reference Number returned by FBR Digital Invoicing.",
			**_RO,
		},
		{
			"fieldname": "custom_fbr_reported",
			"fieldtype": "Check",
			"label": "Reported to FBR",
			"insert_after": "custom_fbr_invoice_number",
			"read_only": 1,
			"no_copy": 1,
		},
		*_QUEUE_FIELDS,
	],
	"Sales Invoice": _QUEUE_FIELDS,
}
