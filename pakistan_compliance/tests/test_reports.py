# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Phase 6 coverage: the FBR return annexures and the WHT statement.

Structure tests always run. The reconciliation tests assert the invariant that a
report's tax total equals the matching GL balance for the same period; they run
against whatever company/data the site has, and skip if none is set up (so they
pass on a bare CI site and verify for real on a configured one)."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from pakistan_compliance.pakistan_compliance.report.pakistan_sales_tax_annexure_a import (
	pakistan_sales_tax_annexure_a as annexure_a,
)
from pakistan_compliance.pakistan_compliance.report.pakistan_sales_tax_annexure_c import (
	pakistan_sales_tax_annexure_c as annexure_c,
)
from pakistan_compliance.pakistan_compliance.report.pakistan_wht_statement_165 import (
	pakistan_wht_statement_165 as wht_statement,
)

PERIOD = {"from_date": "2020-01-01", "to_date": "2099-12-31"}


def _company_with_account(account_name):
	"""A company that has the given (leaf) tax account, or None."""
	row = frappe.db.get_value(
		"Account", {"account_name": account_name, "is_group": 0}, ["company", "name"], as_dict=True
	)
	return (row.company, row.name) if row else (None, None)


def _gl_balance(company, account, from_date, to_date):
	val = frappe.db.sql(
		"""select sum(credit - debit) from `tabGL Entry`
		   where company=%s and account=%s and is_cancelled=0 and posting_date between %s and %s""",
		(company, account, from_date, to_date),
	)[0][0]
	return flt(val)


def _seed_wht():
	"""WHT account + categories on the first company, inside the test transaction."""
	from unittest import mock

	from pakistan_compliance import wht_setup

	company = frappe.get_all("Company", pluck="name", limit=1)[0]
	with mock.patch.object(frappe.db, "commit"):
		wht_setup.setup_company_wht(company)
	return company


class TestReportStructure(IntegrationTestCase):
	def _run(self, mod):
		company = frappe.db.get_value("Company", {}, "name")
		cols, data = mod.execute({"company": company, **PERIOD})
		self.assertTrue(cols and isinstance(data, list))
		return {c["fieldname"] for c in cols}

	def test_annexure_c_columns(self):
		fields = self._run(annexure_c)
		self.assertLessEqual({"invoice", "value_excl_tax", "sales_tax", "further_tax", "total"}, fields)

	def test_annexure_a_columns(self):
		fields = self._run(annexure_a)
		self.assertLessEqual({"invoice", "value_excl_tax", "input_tax", "total"}, fields)

	def test_wht_statement_columns(self):
		_seed_wht()
		fields = self._run(wht_statement)
		self.assertLessEqual({"supplier", "section", "tax_withheld"}, fields)

	def test_requires_company_and_dates(self):
		with self.assertRaises(frappe.ValidationError):
			annexure_c.execute({"company": None, "from_date": None, "to_date": None})


class TestReportReconciliation(IntegrationTestCase):
	def test_annexure_c_matches_output_tax_gl(self):
		company, account = _company_with_account("Sales Tax Payable")
		if not company:
			self.skipTest("no Sales Tax Payable account seeded")
		_cols, data = annexure_c.execute({"company": company, **PERIOD})
		report_total = sum(flt(r["sales_tax"]) for r in data)
		self.assertAlmostEqual(report_total, _gl_balance(company, account, PERIOD["from_date"], PERIOD["to_date"]), places=2)

	def test_wht_statement_matches_wht_gl(self):
		company, account = _company_with_account("Withholding Tax Payable")
		if not company:
			self.skipTest("no Withholding Tax Payable account seeded")
		_cols, data = wht_statement.execute({"company": company, **PERIOD})
		report_total = sum(flt(r["tax_withheld"]) for r in data)
		self.assertAlmostEqual(report_total, _gl_balance(company, account, PERIOD["from_date"], PERIOD["to_date"]), places=2)
