# Copyright (c) 2026, Sowaan and contributors
# For license information, please see license.txt

"""Install / migrate setup for Pakistan Compliance (Phase 1).

Adds the Pakistan tax master-data fields to the standard doctypes. Idempotent:
create_custom_fields skips fields that already exist, so this is safe to run on
every install and every migrate.
"""

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

# Pakistan's tax jurisdictions (province + the two federal territories treated as
# such for sales tax on services). Leading blank so the field is optional.
PROVINCES = (
	"\nPunjab\nSindh\nKhyber Pakhtunkhwa\nBalochistan\n"
	"Islamabad Capital Territory\nGilgit-Baltistan\nAzad Jammu and Kashmir"
)

# Filer status drives withholding-tax rates (non-filers pay more). Leading blank.
FILER_STATUS = "\nFiler\nNon-Filer"


# The Pakistan Tax section fields, in display order. The field_order property
# setter (see _place_party_section) positions this block inside the Tax tab.
PARTY_SECTION_FIELDS = [
	"custom_pk_tax_section",
	"custom_ntn",
	"custom_strn",
	"custom_pk_tax_column_break",
	"custom_cnic",
	"custom_filer_status",
]


def _company_tax_fields():
	"""NTN + STRN on Company (no Tax tab), placed after tax_id in the details section."""
	return [
		{
			"fieldname": "custom_ntn",
			"fieldtype": "Data",
			"label": "NTN (National Tax Number)",
			"insert_after": "tax_id",
			"translatable": 0,
		},
		{
			"fieldname": "custom_strn",
			"fieldtype": "Data",
			"label": "STRN (Sales Tax Registration Number)",
			"insert_after": "custom_ntn",
			"translatable": 0,
		},
	]


def _party_tax_fields():
	"""The 'Pakistan Tax' section for Customer / Supplier: a Section Break plus
	NTN/STRN in one column and CNIC/Filer Status in a second. These insert_after
	anchors only make the fields valid; their final position inside the Tax tab is
	set by the field_order property setter in _place_party_section (a custom Section
	Break can't be placed reliably by insert_after alone)."""
	return [
		{
			"fieldname": "custom_pk_tax_section",
			"fieldtype": "Section Break",
			"label": "Pakistan Tax",
			"insert_after": "tax_withholding_category",
		},
		{
			"fieldname": "custom_ntn",
			"fieldtype": "Data",
			"label": "NTN (National Tax Number)",
			"insert_after": "custom_pk_tax_section",
			"translatable": 0,
		},
		{
			"fieldname": "custom_strn",
			"fieldtype": "Data",
			"label": "STRN (Sales Tax Registration Number)",
			"insert_after": "custom_ntn",
			"translatable": 0,
		},
		{
			"fieldname": "custom_pk_tax_column_break",
			"fieldtype": "Column Break",
			"insert_after": "custom_strn",
		},
		{
			"fieldname": "custom_cnic",
			"fieldtype": "Data",
			"label": "CNIC",
			"insert_after": "custom_pk_tax_column_break",
			"translatable": 0,
			"description": "13-digit national ID, required on invoices to unregistered buyers above the FBR threshold.",
		},
		{
			"fieldname": "custom_filer_status",
			"fieldtype": "Select",
			"label": "Filer Status (ATL)",
			"options": FILER_STATUS,
			"insert_after": "custom_cnic",
			"description": "Active Taxpayer List status. Affects withholding-tax rates.",
		},
	]


CUSTOM_FIELDS = {
	"Company": _company_tax_fields(),
	"Customer": _party_tax_fields(),
	"Supplier": _party_tax_fields(),
	"Item": [
		{
			"fieldname": "custom_hs_code",
			"fieldtype": "Data",
			"label": "HS Code",
			"insert_after": "item_group",
			"translatable": 0,
			"description": "Harmonized System code, required on FBR sales tax invoices.",
		}
	],
	"Address": [
		{
			"fieldname": "custom_province",
			"fieldtype": "Select",
			"label": "Province",
			"options": PROVINCES,
			"insert_after": "state",
			"description": "Determines the sales-tax-on-services authority (SRB / PRA / KPRA / BRA / ICT).",
		}
	],
	"Sales Invoice": [
		{
			"fieldname": "custom_fbr_invoice_number",
			"fieldtype": "Data",
			"label": "FBR Invoice Number (IRN)",
			"insert_after": "customer_name",
			"read_only": 1,
			"no_copy": 1,
			"translatable": 0,
			"description": "Invoice Reference Number returned by FBR Digital Invoicing.",
		},
		{
			"fieldname": "custom_fbr_reported",
			"fieldtype": "Check",
			"label": "Reported to FBR",
			"insert_after": "custom_fbr_invoice_number",
			"read_only": 1,
			"no_copy": 1,
		},
	],
}


# FBR reporting of point-of-sale sales (POS Invoice support): see pos/fields.py
from pakistan_compliance.pos.fields import POS_CUSTOM_FIELDS  # noqa: E402

for _doctype, _fields in POS_CUSTOM_FIELDS.items():
	CUSTOM_FIELDS.setdefault(_doctype, []).extend(_fields)


def _place_party_section(doctype):
	"""Position the Pakistan Tax section right after `tax_withholding_category` via a
	DocType-level `field_order` property setter, so the labeled section renders
	inside the Tax tab. Regenerated from the live meta on every run, so it self-heals
	if ERPNext adds or removes fields (idempotent)."""
	if not frappe.db.exists("DocType", doctype):
		return
	meta = frappe.get_meta(doctype)
	order = [df.fieldname for df in meta.fields]
	group = [f for f in PARTY_SECTION_FIELDS if f in order]
	if "tax_withholding_category" not in order or len(group) != len(PARTY_SECTION_FIELDS):
		return  # fields not all present yet; nothing to place

	order = [f for f in order if f not in group]
	pos = order.index("tax_withholding_category") + 1
	order[pos:pos] = group
	value = json.dumps(order)

	existing = frappe.db.get_value(
		"Property Setter",
		{"doc_type": doctype, "property": "field_order", "doctype_or_field": "DocType"},
		"name",
	)
	if existing:
		frappe.db.set_value("Property Setter", existing, "value", value)
	else:
		make_property_setter(
			doctype, "", "field_order", value, "Text",
			for_doctype=True, validate_fields_for_doctype=False,
		)
	frappe.clear_cache(doctype=doctype)


def ensure_custom_fields():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
	for doctype in ("Customer", "Supplier"):
		_place_party_section(doctype)


# DocType -> the Pakistan print format that should be its default on install.
# (The Credit Note shares the Sales Invoice DocType with the invoice, which already
# owns that default, so it stays a manually selectable format.)
DEFAULT_PRINT_FORMATS = {
	"Sales Invoice": "FBR Sales Tax Invoice",
	"Sales Order": "Pakistan Sales Order",
	"Delivery Note": "Pakistan Delivery Challan",
	"Purchase Order": "Pakistan Purchase Order",
	"Quotation": "Pakistan Quotation",
	"Payment Entry": "Pakistan Payment Voucher",
	"Withholding Tax Certificate": "Pakistan Withholding Tax Certificate",
}


def ensure_default_print_formats(force=False):
	"""Make each Pakistan print format the default for its DocType, via a durable
	Property Setter.

	On install (force=True) we set our format as the default even if the DocType
	already has one, so a fresh install gets the Pakistan formats instead of the
	ERPNext framework defaults (e.g. 'Sales Order with Item Image'). On migrate
	(force=False) we only set a default when the DocType has none, so a customer who
	later picks their own default (or clears ours) is never overridden on upgrade."""
	for doctype, print_format in DEFAULT_PRINT_FORMATS.items():
		if not (frappe.db.exists("DocType", doctype) and frappe.db.exists("Print Format", print_format)):
			continue
		existing = frappe.db.get_value(
			"Property Setter",
			{"doc_type": doctype, "property": "default_print_format", "doctype_or_field": "DocType"},
			["name", "value"],
			as_dict=True,
		)
		if existing:
			if existing.value == print_format:
				continue
			if not force:
				continue  # migrate: respect whatever default is already set
			frappe.db.set_value("Property Setter", existing.name, "value", print_format)
		else:
			make_property_setter(
				doctype, "", "default_print_format", print_format, "Data",
				for_doctype=True, validate_fields_for_doctype=False,
			)


def ensure_settings_defaults():
	"""Seed one-time defaults on Pakistan Tax Settings without overwriting the
	customer's choices. A Single's field defaults only take effect once the doc is
	saved, and an unset Check reads back as 0, so we persist the intended default
	here. Only writes when the value has never been set (skip-if-exists)."""
	if not frappe.db.exists("DocType", "Pakistan Tax Settings"):
		return
	# Urdu amount-in-words: on by default. A field is only in the Singles dict once
	# it has been written, so "absent" means never set (vs. a stored 0, which is a
	# customer turning it off and must be left alone).
	stored = frappe.db.get_singles_dict("Pakistan Tax Settings")
	if "show_urdu_in_words" not in stored:
		frappe.db.set_single_value("Pakistan Tax Settings", "show_urdu_in_words", 1)


def ensure_pk_desktop_icon():
	"""On v16, make the desktop icon the Pakistan Compliance *workspace* (a "Link"
	Desktop Icon) with its `app` set, so it opens in the same tab and shows the
	pk_compliance logo (from the public/icons sprite) instead of a letter avatar.
	An "App"-type icon (e.g. a leftover from add_to_apps_screen) is removed.
	Mirrors the tarceel_erpnext approach. Idempotent; no-op on v15."""
	if not frappe.db.exists("DocType", "Desktop Icon"):
		return  # not v16

	from frappe.desk.doctype.desktop_icon.desktop_icon import create_desktop_icons

	current = frappe.db.get_value(
		"Desktop Icon", "Pakistan Compliance", ["icon_type", "app", "parent_icon", "icon"], as_dict=True
	)
	if current and current.icon_type == "App":
		frappe.delete_doc("Desktop Icon", "Pakistan Compliance", ignore_permissions=True, force=True)
		current = None

	if not current:
		create_desktop_icons()  # regenerates the workspace Link icon
		current = frappe.db.get_value(
			"Desktop Icon", "Pakistan Compliance", ["icon_type", "app", "parent_icon", "icon"], as_dict=True
		)

	# Frappe sets `app_name` (not `app`) on workspace icons, so the logo lookup
	# fails and it falls back to a letter avatar; fix `app` and detach from folders.
	if current:
		changes = {}
		if current.app != "pakistan_compliance":
			changes["app"] = "pakistan_compliance"
		if current.get("icon") != "pk-compliance":
			changes["icon"] = "pk-compliance"
		if current.parent_icon:
			changes["parent_icon"] = None
		if changes:
			frappe.db.set_value("Desktop Icon", "Pakistan Compliance", changes)
			frappe.cache.hdel("desktop_icons", "Administrator")


def boot_fix_desktop_icon(bootinfo=None):
	"""Fresh-install safety net (extend_bootinfo hook). Frappe creates the workspace
	Desktop Icon AFTER after_install runs, so ensure_pk_desktop_icon can't set its
	`app` there and the tile shows a letter avatar until the next migrate. Fix it
	lazily on boot; a cheap no-op once `app` is set."""
	try:
		if not frappe.db.exists("DocType", "Desktop Icon"):
			return
		di = frappe.db.get_value("Desktop Icon", "Pakistan Compliance", ["name", "app"], as_dict=True)
		if di and di.app != "pakistan_compliance":
			ensure_pk_desktop_icon()
	except Exception:
		pass


def after_install():
	ensure_custom_fields()
	ensure_default_print_formats(force=True)
	ensure_settings_defaults()
	ensure_pk_desktop_icon()


def after_migrate():
	ensure_custom_fields()
	ensure_default_print_formats(force=False)
	ensure_settings_defaults()
	ensure_pk_desktop_icon()
