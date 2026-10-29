# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Phase 2: Pakistan tax setup automation.

Creates the tax Chart of Accounts entries and the Sales/Purchase Taxes and Charges
Templates for a chosen Company. Triggered from a button on Pakistan Tax Settings,
so it runs against a real Company (with its Chart of Accounts) that the admin picks.

Idempotent: every account/template is skipped if it already exists, so re-running
never duplicates and never overwrites a customer's edits.

Rates are the current defaults (verify against the latest Finance Act / SROs):
federal sales tax on goods 18%, further tax 3%, and sales tax on services by
province (Sindh 13%, Punjab 16%, KP 15%, Balochistan 15%, ICT 15%).
"""

import frappe
from frappe import _

# Output (payable) tax accounts, created under the company's Duties and Taxes group.
OUTPUT_SALES_TAX = "Sales Tax Payable"
FURTHER_TAX = "Further Tax Payable"
INPUT_SALES_TAX = "Input Sales Tax"

# Province -> (output account name, rate). Sales tax on services is provincial.
PROVINCIAL_SERVICES = {
	"Sindh Sales Tax on Services": ("Sindh Sales Tax Payable", 13),
	"Punjab Sales Tax on Services": ("Punjab Sales Tax Payable", 16),
	"KPK Sales Tax on Services": ("KPK Sales Tax Payable", 15),
	"Balochistan Sales Tax on Services": ("Balochistan Sales Tax Payable", 15),
	"ICT Sales Tax on Services": ("ICT Sales Tax Payable", 15),
}


def _abbr(company):
	return frappe.get_cached_value("Company", company, "abbr")


def _acc(company, account_name):
	"""Full account name as ERPNext stores it: '<name> - <abbr>'."""
	return f"{account_name} - {_abbr(company)}"


def _tax_parent(company):
	"""The company's 'Duties and Taxes' group account; create it if the chart
	does not have one."""
	grp = frappe.db.get_value(
		"Account", {"company": company, "account_name": "Duties and Taxes", "is_group": 1}, "name"
	)
	if grp:
		return grp

	parent = frappe.db.get_value(
		"Account", {"company": company, "account_name": "Current Liabilities", "is_group": 1}, "name"
	) or frappe.db.get_value(
		"Account", {"company": company, "is_group": 1, "root_type": "Liability", "parent_account": ""}, "name"
	)
	group = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": "Duties and Taxes",
			"company": company,
			"parent_account": parent,
			"is_group": 1,
			"account_type": "Tax",
		}
	)
	group.insert(ignore_permissions=True)
	return group.name


def _ensure_account(company, account_name, parent):
	"""Create a leaf Tax account under `parent` if missing. Returns (name, created)."""
	name = _acc(company, account_name)
	if frappe.db.exists("Account", name):
		return name, False
	frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": account_name,
			"company": company,
			"parent_account": parent,
			"is_group": 0,
			"account_type": "Tax",
		}
	).insert(ignore_permissions=True)
	return name, True


def _ensure_template(doctype, company, title, rows):
	"""Create a Sales/Purchase Taxes and Charges Template if one with this title does
	not already exist for the company. `rows` is a list of (account_name, rate).
	Returns True if created."""
	if frappe.db.exists(doctype, {"title": title, "company": company}):
		return False

	child = "Sales Taxes and Charges" if doctype == "Sales Taxes and Charges Template" else "Purchase Taxes and Charges"
	taxes = []
	for account_name, rate in rows:
		row = {
			"charge_type": "On Net Total",
			"account_head": _acc(company, account_name),
			"rate": rate,
			"description": title,
		}
		if child == "Purchase Taxes and Charges":
			row["category"] = "Total"
			row["add_deduct_tax"] = "Add"
		taxes.append(row)

	frappe.get_doc(
		{"doctype": doctype, "title": title, "company": company, "taxes": taxes}
	).insert(ignore_permissions=True)
	return True


def _sales_templates():
	"""(title, rows) for the Sales Taxes and Charges Templates."""
	templates = [
		("Pakistan Sales Tax 18%", [(OUTPUT_SALES_TAX, 18)]),
		("Pakistan Sales Tax 18% + Further Tax 3%", [(OUTPUT_SALES_TAX, 18), (FURTHER_TAX, 3)]),
	]
	for label, (account_name, rate) in PROVINCIAL_SERVICES.items():
		templates.append((f"{label} {rate}%", [(account_name, rate)]))
	templates.append(("Zero Rated 0%", [(OUTPUT_SALES_TAX, 0)]))
	templates.append(("Exempt", []))
	return templates


def _purchase_templates():
	"""(title, rows) for the Purchase Taxes and Charges Templates (input tax)."""
	templates = [("Pakistan Input Sales Tax 18%", [(INPUT_SALES_TAX, 18)])]
	for label, (_account, rate) in PROVINCIAL_SERVICES.items():
		templates.append((f"Input {label} {rate}%", [(INPUT_SALES_TAX, rate)]))
	return templates


@frappe.whitelist()
def setup_company_taxes(company):
	"""Create the Pakistan tax accounts and Sales/Purchase tax templates for
	`company`. Idempotent. Returns a summary of what was created."""
	frappe.only_for("System Manager")
	if not (company and frappe.db.exists("Company", company)):
		frappe.throw(_("Select a valid Company to set up Pakistan taxes for."))

	parent = _tax_parent(company)

	created = {"accounts": [], "sales_templates": [], "purchase_templates": []}

	account_names = [OUTPUT_SALES_TAX, FURTHER_TAX, INPUT_SALES_TAX] + [
		acct for acct, _rate in PROVINCIAL_SERVICES.values()
	]
	for account_name in account_names:
		_name, is_new = _ensure_account(company, account_name, parent)
		if is_new:
			created["accounts"].append(account_name)

	for title, rows in _sales_templates():
		if _ensure_template("Sales Taxes and Charges Template", company, title, rows):
			created["sales_templates"].append(title)

	for title, rows in _purchase_templates():
		if _ensure_template("Purchase Taxes and Charges Template", company, title, rows):
			created["purchase_templates"].append(title)

	frappe.db.set_single_value("Pakistan Tax Settings", "default_data_seeded", 1)
	frappe.db.commit()  # nosemgrep: intentional persist after a multi-step whitelisted action

	return created
