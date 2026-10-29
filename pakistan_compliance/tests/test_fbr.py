# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Phase 5 coverage: FBR Digital Invoicing payload mapping and response parsing.

The buyer, item and company NTN the payload needs are created inside the test's
transaction, so a clean CI site with no demo data works. The live post is not
exercised here (it needs a real FBR sandbox token); report_to_fbr is verified
separately with a mocked client."""

import frappe
from frappe.tests import IntegrationTestCase

from pakistan_compliance.fbr_invoice import build_invoice_payload, parse_response

OK_RESPONSE = {
	"invoiceNumber": "7000007DI1234567890",
	"dated": "2026-09-21 12:00:00",
	"validationResponse": {"statusCode": "00", "status": "Valid", "error": "", "invoiceStatuses": []},
}
FAIL_RESPONSE = {
	"invoiceNumber": "",
	"validationResponse": {
		"statusCode": "01",
		"status": "Invalid",
		"error": "",
		"invoiceStatuses": [{"itemSNo": "1", "statusCode": "0053", "status": "Invalid", "error": "Invalid registration type"}],
	},
}


def _demo_company():
	"""First company on the site, with an NTN set (the payload maps it to sellerNTNCNIC)."""
	company = frappe.get_all("Company", pluck="name", limit=1)[0]
	if not frappe.db.get_value("Company", company, "custom_ntn"):
		frappe.db.set_value("Company", company, "custom_ntn", "1234567-8")
	return company


def _demo_customer(name="PK Test Customer", ntn="1234567-8"):
	"""Create the buyer (or fill in its NTN) so the test does not depend on site fixtures."""
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
				"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
				"custom_ntn": ntn,
			}
		).insert(ignore_permissions=True)
	elif ntn and not frappe.db.get_value("Customer", name, "custom_ntn"):
		frappe.db.set_value("Customer", name, "custom_ntn", ntn)
	return name


def _demo_item(code="PK-TEST-ITEM", hs_code="6907.2100"):
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": "Ceramic Tiles",
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": "Nos",
				"custom_hs_code": hs_code,
			}
		).insert(ignore_permissions=True)
	return code


def _demo_invoice():
	company = _demo_company()
	customer = _demo_customer()
	item = _demo_item()
	doc = frappe.new_doc("Sales Invoice")
	doc.company = company
	doc.customer = customer
	doc.customer_name = customer
	doc.posting_date = "2026-09-21"
	doc.currency = "PKR"
	doc.append("items", {"item_code": item, "item_name": "Ceramic Tiles", "qty": 10, "uom": "Nos", "rate": 1000, "net_amount": 10000, "net_rate": 1000})
	doc.net_total = 10000
	doc.append("taxes", {"charge_type": "On Net Total", "description": "Sales Tax @ 18%", "rate": 18, "tax_amount": 1800, "account_head": f"Sales Tax Payable - {frappe.db.get_value('Company', company, 'abbr')}"})
	doc.grand_total = 11800
	return doc


class TestFbrPayload(IntegrationTestCase):
	def test_seller_and_buyer_identity(self):
		p = build_invoice_payload(_demo_invoice())
		self.assertEqual(p["sellerBusinessName"], _demo_company())
		self.assertTrue(p["sellerNTNCNIC"])  # company NTN seeded by the helper
		self.assertEqual(p["buyerBusinessName"], "PK Test Customer")
		self.assertEqual(p["buyerRegistrationType"], "Registered")  # customer has an NTN
		self.assertEqual(p["invoiceType"], "Sale Invoice")

	def test_item_mapping(self):
		p = build_invoice_payload(_demo_invoice())
		self.assertEqual(len(p["items"]), 1)
		item = p["items"][0]
		self.assertEqual(item["hsCode"], "6907.2100")
		self.assertEqual(item["rate"], "18%")
		self.assertEqual(item["valueSalesExcludingST"], 10000)
		self.assertEqual(item["salesTaxApplicable"], 1800)
		self.assertEqual(item["totalValues"], 11800)

	def test_unregistered_buyer(self):
		doc = _demo_invoice()
		# A walk-in customer with no NTN/STRN should map to Unregistered.
		doc.customer = "PK Walkin"
		doc.customer_name = "PK Walkin"
		if not frappe.db.exists("Customer", "PK Walkin"):
			frappe.get_doc({"doctype": "Customer", "customer_name": "PK Walkin", "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"), "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name")}).insert(ignore_permissions=True)
		p = build_invoice_payload(doc)
		self.assertEqual(p["buyerRegistrationType"], "Unregistered")


class TestFbrResponseParse(IntegrationTestCase):
	def test_success(self):
		irn, ok, error = parse_response(OK_RESPONSE)
		self.assertTrue(ok)
		self.assertEqual(irn, "7000007DI1234567890")
		self.assertEqual(error, "")

	def test_failure_aggregates_item_errors(self):
		irn, ok, error = parse_response(FAIL_RESPONSE)
		self.assertFalse(ok)
		self.assertFalse(irn)
		self.assertIn("Invalid registration type", error)

	def test_empty_response(self):
		irn, ok, error = parse_response({})
		self.assertFalse(ok)
		self.assertTrue(error)
