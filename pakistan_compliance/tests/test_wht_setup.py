# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Phase 4 coverage: the Pakistan withholding-tax categories the setup button seeds.

Data-level tests (no DB writes): confirm the section list, the Filer/Non-Filer
naming, and that every non-filer rate is at least the filer rate. The end-to-end
creation (WHT account + Tax Withholding Categories for a real Company) is verified
against a live Company. Rate VALUES are intentionally not asserted here: they are
editable defaults that must be verified against the current Finance Act, so pinning
them in a test would give false confidence.
"""

import frappe
from frappe.tests import IntegrationTestCase

from pakistan_compliance import wht_setup
from pakistan_compliance.wht_setup import propagate_item_wht, sync_supplier_wht_category


def _seed_wht():
	"""Create the WHT account + Filer/Non-Filer categories on the first company.

	setup_company_wht() commits by design (it is a user action); patching the commit keeps
	this inside the test's transaction, so the clean CI site is left untouched."""
	from unittest import mock

	company = frappe.get_all("Company", pluck="name", limit=1)[0]
	with mock.patch.object(frappe.db, "commit"):
		wht_setup.setup_company_wht(company)
	return company


class TestWhtSetup(IntegrationTestCase):
	def test_core_sections_present(self):
		sections = [s["section"] for s in wht_setup.WHT_SECTIONS]
		for expected in ("153(1)(a)", "153(1)(b)", "153(1)(c)", "233", "155"):
			self.assertIn(expected, sections)

	def test_filer_and_nonfiler_variants(self):
		self.assertEqual(wht_setup.STATUSES, ("Filer", "Non-Filer"))
		name = wht_setup.category_name("153(1)(b)", "Services", "Non-Filer")
		self.assertEqual(name, "Pakistan WHT 153(1)(b) Services (Non-Filer)")

	def test_nonfiler_not_below_filer(self):
		# Non-filers never withhold less than filers; the exact multiple varies by
		# section, so we only assert the direction, not the value.
		for s in wht_setup.WHT_SECTIONS:
			self.assertGreaterEqual(s["non_filer"], s["filer"], s["section"])

	def test_rate_window_is_open_ended(self):
		# to_date is far future so a later invoice never silently computes zero WHT.
		self.assertGreater(wht_setup.WHT_RATES_TO, wht_setup.WHT_RATES_FROM)


class TestWhtPropagation(IntegrationTestCase):
	"""The v16 supplier -> item WHT propagation hook (no-op on v15)."""

	def _pi(self):
		pi = frappe.new_doc("Purchase Invoice")
		pi.apply_tds = 1
		pi.tax_withholding_category = "Pakistan WHT 153(1)(b) Services (Filer)"
		pi.append("items", {"item_code": "_WHT_TEST", "qty": 1, "rate": 1000})
		return pi

	def test_propagates_to_items_on_v16(self):
		pi = self._pi()
		item_has_field = pi.items[0].meta.has_field("tax_withholding_category")
		propagate_item_wht(pi)
		if item_has_field:  # v16
			self.assertEqual(pi.items[0].tax_withholding_category, pi.tax_withholding_category)
			self.assertTrue(pi.items[0].apply_tds)
		else:  # v15: item has no WHT field, hook is a no-op
			self.assertFalse(pi.items[0].get("tax_withholding_category"))

	def test_noop_when_apply_tds_off(self):
		pi = self._pi()
		pi.apply_tds = 0
		propagate_item_wht(pi)
		self.assertFalse(pi.items[0].get("tax_withholding_category"))


class TestSupplierWhtSync(IntegrationTestCase):
	"""Supplier Filer status -> WHT category variant sync (needs the seeded categories)."""

	def _supplier(self, status, category):
		s = frappe.new_doc("Supplier")
		s.supplier_name = "SYNC-TEST"
		s.custom_filer_status = status
		s.tax_withholding_category = category
		return s

	def test_switches_variant_to_match_status(self):
		_seed_wht()
		s = self._supplier("Non-Filer", "Pakistan WHT 153(1)(b) Services (Filer)")
		sync_supplier_wht_category(s)
		self.assertEqual(s.tax_withholding_category, "Pakistan WHT 153(1)(b) Services (Non-Filer)")

	def test_keeps_section_with_parentheses(self):
		# Section labels contain their own parens (155 ... (Company)); only the
		# trailing (Filer)/(Non-Filer) variant is swapped.
		_seed_wht()
		s = self._supplier("Filer", "Pakistan WHT 155 Rent of Immovable Property (Company) (Non-Filer)")
		sync_supplier_wht_category(s)
		self.assertEqual(
			s.tax_withholding_category, "Pakistan WHT 155 Rent of Immovable Property (Company) (Filer)"
		)

	def test_noop_when_already_matching(self):
		s = self._supplier("Filer", "Pakistan WHT 153(1)(b) Services (Filer)")
		sync_supplier_wht_category(s)
		self.assertEqual(s.tax_withholding_category, "Pakistan WHT 153(1)(b) Services (Filer)")

	def test_noop_for_non_pakistan_category(self):
		s = self._supplier("Non-Filer", "Some Other Category")
		sync_supplier_wht_category(s)
		self.assertEqual(s.tax_withholding_category, "Some Other Category")

	def test_noop_when_no_category(self):
		s = self._supplier("Non-Filer", None)
		sync_supplier_wht_category(s)  # must not raise
		self.assertFalse(s.tax_withholding_category)
