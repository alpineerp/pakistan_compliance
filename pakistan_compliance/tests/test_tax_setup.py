# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Phase 2 coverage: the Pakistan tax templates/rates the setup button seeds.

Data-level tests (no DB writes): confirm the default rates and the set of
templates. The end-to-end creation (accounts + templates for a real Company) is
verified against a live Company with a Chart of Accounts.
"""

from frappe.tests import IntegrationTestCase

from pakistan_compliance import tax_setup


class TestTaxSetup(IntegrationTestCase):
	def test_sales_templates_cover_defaults(self):
		titles = [title for title, _rows in tax_setup._sales_templates()]
		for expected in (
			"Pakistan Sales Tax 18%",
			"Pakistan Sales Tax 18% + Further Tax 3%",
			"Sindh Sales Tax on Services 13%",
			"Punjab Sales Tax on Services 16%",
			"KPK Sales Tax on Services 15%",
			"Balochistan Sales Tax on Services 15%",
			"ICT Sales Tax on Services 15%",
			"Zero Rated 0%",
			"Exempt",
		):
			self.assertIn(expected, titles)

	def test_standard_and_further_tax_rates(self):
		rows = dict(tax_setup._sales_templates())["Pakistan Sales Tax 18% + Further Tax 3%"]
		rates = {account: rate for account, rate in rows}
		self.assertEqual(rates[tax_setup.OUTPUT_SALES_TAX], 18)
		self.assertEqual(rates[tax_setup.FURTHER_TAX], 3)

	def test_exempt_has_no_tax_rows(self):
		self.assertEqual(dict(tax_setup._sales_templates())["Exempt"], [])

	def test_provincial_rates(self):
		self.assertEqual(tax_setup.PROVINCIAL_SERVICES["Sindh Sales Tax on Services"][1], 13)
		self.assertEqual(tax_setup.PROVINCIAL_SERVICES["Punjab Sales Tax on Services"][1], 16)
		self.assertEqual(tax_setup.PROVINCIAL_SERVICES["ICT Sales Tax on Services"][1], 15)

	def test_purchase_has_federal_input(self):
		titles = [title for title, _rows in tax_setup._purchase_templates()]
		self.assertIn("Pakistan Input Sales Tax 18%", titles)
