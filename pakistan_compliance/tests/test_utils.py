# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Offline tests for the Urdu amount-in-words helper (Phase 3)."""

import unittest

import frappe

from pakistan_compliance.install import ensure_settings_defaults
from pakistan_compliance.utils import fmt_money_abs, money_in_words_urdu, show_urdu_in_words


class TestUrduInWords(unittest.TestCase):
	def test_whole_rupees(self):
		# 70180 -> seventy thousand one hundred eighty rupees only
		self.assertEqual(money_in_words_urdu(70180, "PKR"), "ستر ہزار ایک سو اسی روپے فقط")

	def test_lakh_crore_grouping(self):
		# South Asian grouping: 100000 is one lakh, not "hundred thousand"
		self.assertEqual(money_in_words_urdu(100000, "PKR"), "ایک لاکھ روپے فقط")
		self.assertIn("کروڑ", money_in_words_urdu(10000000, "PKR"))

	def test_paisa_subunit(self):
		words = money_in_words_urdu(1740.50, "PKR")
		self.assertIn("اور", words)  # joins rupees "and" paisa
		self.assertIn("پیسے", words)
		self.assertTrue(words.endswith("فقط"))

	def test_negative_is_absolute(self):
		# Credit / debit notes carry a negative grand_total; magnitude is spelled.
		self.assertEqual(money_in_words_urdu(-70180, "PKR"), money_in_words_urdu(70180, "PKR"))

	def test_zero(self):
		self.assertEqual(money_in_words_urdu(0, "PKR"), "صفر روپے فقط")

	def test_non_pkr_currency_named(self):
		words = money_in_words_urdu(100.25, "USD")
		self.assertIn("ڈالر", words)  # US dollar main unit
		self.assertIn("سینٹ", words)  # cent sub-unit

	def test_unknown_currency_falls_back_to_code(self):
		# Never mislabel: an unmapped code is used verbatim as the unit name.
		words = money_in_words_urdu(5, "XYZ")
		self.assertIn("XYZ", words)

	def test_rounding_to_next_whole_unit(self):
		# 9.999 rounds the paisa up to 100 -> carries into the whole unit, no "100 paise".
		words = money_in_words_urdu(9.999, "PKR")
		self.assertNotIn("پیسے", words)
		self.assertEqual(words, money_in_words_urdu(10, "PKR"))


class TestFmtMoneyAbs(unittest.TestCase):
	"""Magnitude formatting for returns / credit / debit notes (negative amounts)."""

	def test_negative_shows_positive_magnitude(self):
		self.assertEqual(fmt_money_abs(-11800, "PKR"), fmt_money_abs(11800, "PKR"))

	def test_no_minus_sign(self):
		self.assertNotIn("-", fmt_money_abs(-10000, "PKR"))


class TestUrduInWordsToggle(unittest.TestCase):
	"""The 'Show Urdu Amount in Words' toggle on Pakistan Tax Settings."""

	def setUp(self):
		self._saved = frappe.db.get_single_value("Pakistan Tax Settings", "show_urdu_in_words")

	def tearDown(self):
		frappe.db.set_single_value(
			"Pakistan Tax Settings", "show_urdu_in_words", self._saved or 0
		)

	def test_toggle_on_and_off(self):
		frappe.db.set_single_value("Pakistan Tax Settings", "show_urdu_in_words", 1)
		self.assertTrue(show_urdu_in_words())
		frappe.db.set_single_value("Pakistan Tax Settings", "show_urdu_in_words", 0)
		self.assertFalse(show_urdu_in_words())

	def test_seed_defaults_on_when_unset(self):
		frappe.db.delete(
			"Singles", {"doctype": "Pakistan Tax Settings", "field": "show_urdu_in_words"}
		)
		ensure_settings_defaults()
		self.assertTrue(show_urdu_in_words())

	def test_seed_does_not_override_customer_off(self):
		frappe.db.set_single_value("Pakistan Tax Settings", "show_urdu_in_words", 0)
		ensure_settings_defaults()  # must respect the explicit off
		self.assertFalse(show_urdu_in_words())


if __name__ == "__main__":
	unittest.main()
