# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Phase 3 coverage: the Pakistan print formats exist and the default-print-format
seeding behaves (force on install, respect edits on migrate)."""

import frappe
from frappe.tests import IntegrationTestCase

from pakistan_compliance.install import DEFAULT_PRINT_FORMATS, ensure_default_print_formats

# All shipped Pakistan print formats and the DocType each targets.
SHIPPED_FORMATS = {
	"FBR Sales Tax Invoice": "Sales Invoice",
	"FBR Sales Tax Credit Note": "Sales Invoice",
	"Pakistan Sales Order": "Sales Order",
	"Pakistan Delivery Challan": "Delivery Note",
	"Pakistan Purchase Order": "Purchase Order",
	"Pakistan Quotation": "Quotation",
	"Pakistan Payment Voucher": "Payment Entry",
}


def _default_ps(doctype):
	return frappe.db.get_value(
		"Property Setter",
		{"doc_type": doctype, "property": "default_print_format", "doctype_or_field": "DocType"},
		["name", "value"],
		as_dict=True,
	)


class TestPakistanPrintFormats(IntegrationTestCase):
	def test_all_formats_shipped(self):
		for name, doctype in SHIPPED_FORMATS.items():
			pf = frappe.db.get_value("Print Format", name, ["doc_type", "standard"], as_dict=True)
			self.assertTrue(pf, f"Print Format {name} is missing")
			self.assertEqual(pf.doc_type, doctype)
			self.assertEqual(pf.standard, "Yes")

	def test_install_forces_our_default(self):
		# Simulate ERPNext's framework default already present, then an install.
		make = frappe.db.get_value(
			"Property Setter",
			{"doc_type": "Sales Order", "property": "default_print_format", "doctype_or_field": "DocType"},
			"name",
		)
		saved = _default_ps("Sales Order")
		try:
			if make:
				frappe.db.set_value("Property Setter", make, "value", "Sales Order with Item Image")
			ensure_default_print_formats(force=True)
			self.assertEqual(_default_ps("Sales Order").value, "Pakistan Sales Order")
		finally:
			if saved:
				frappe.db.set_value("Property Setter", saved.name, "value", saved.value)

	def test_migrate_respects_customer_choice(self):
		saved = _default_ps("Quotation")
		try:
			frappe.db.set_value(
				"Property Setter",
				{"doc_type": "Quotation", "property": "default_print_format", "doctype_or_field": "DocType"},
				"value",
				"Standard",
			)
			ensure_default_print_formats(force=False)  # migrate path must not override
			self.assertEqual(_default_ps("Quotation").value, "Standard")
		finally:
			if saved:
				frappe.db.set_value("Property Setter", saved.name, "value", saved.value)

	def test_credit_note_not_defaulted(self):
		# The credit note shares the Sales Invoice DocType; the invoice owns that default.
		self.assertNotIn("FBR Sales Tax Credit Note", DEFAULT_PRINT_FORMATS.values())
