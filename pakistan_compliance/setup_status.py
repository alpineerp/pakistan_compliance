# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Backend for the Pakistan Compliance setup wizard and its onboarding banner.

The wizard reads the current state via `get_setup_state` and saves each step with
the small helpers below; the heavy lifting (tax accounts/templates, WHT categories)
reuses tax_setup / wht_setup. Credentials are never echoed back: the FBR token is
reported only as a boolean `has_token` (guardrail #3)."""

import frappe
from frappe import _


def _guard():
	frappe.only_for(("System Manager", "Accounts Manager"))


def _is_admin():
	return frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles()


def _provinces():
	options = frappe.get_meta("Pakistan Tax Settings").get_field("default_province").options or ""
	return [p for p in options.split("\n") if p]


@frappe.whitelist()
def get_setup_state(company=None):
	"""Everything the wizard needs to render: the company list, current identity,
	what's already seeded, FBR config (token as a boolean), and preferences."""
	_guard()
	settings = frappe.get_cached_doc("Pakistan Tax Settings")
	company = (
		company
		or frappe.defaults.get_global_default("company")
		or frappe.db.get_value("Company", {}, "name")
	)

	identity = {"ntn": "", "strn": ""}
	if company:
		ntn, strn = frappe.db.get_value("Company", company, ["custom_ntn", "custom_strn"]) or ("", "")
		identity = {"ntn": ntn or "", "strn": strn or ""}

	wht_count = frappe.db.count(
		"Tax Withholding Category", {"category_name": ["like", "Pakistan WHT %"]}
	)

	return {
		"company": company,
		"companies": frappe.get_all("Company", pluck="name"),
		"provinces": _provinces(),
		"default_province": settings.get("default_province") or "",
		"identity": identity,
		"tax_seeded": bool(settings.get("default_data_seeded")),
		"wht_categories": wht_count,
		"fbr": {
			"environment": settings.get("fbr_environment") or "Sandbox",
			"base_url": settings.get("fbr_base_url") or "",
			"scenario_id": settings.get("fbr_scenario_id") or "",
			"has_token": bool(settings.get_password("fbr_token", raise_exception=False)),
		},
		"show_urdu": bool(get_setup_state_show_urdu()),
		"workspace_route": "/app/pakistan-compliance",
	}


def get_setup_state_show_urdu():
	value = frappe.db.get_single_value("Pakistan Tax Settings", "show_urdu_in_words")
	return value is None or bool(value)


@frappe.whitelist()
def save_company_identity(company, ntn=None, strn=None, default_province=None):
	"""Step 2: write the company's NTN/STRN and the default province."""
	_guard()
	if not (company and frappe.db.exists("Company", company)):
		frappe.throw(_("Select a valid Company."))
	frappe.db.set_value("Company", company, {"custom_ntn": (ntn or "").strip(), "custom_strn": (strn or "").strip()})
	if default_province is not None:
		frappe.db.set_single_value("Pakistan Tax Settings", "default_province", default_province)
	frappe.db.commit()  # nosemgrep: intentional persist after a multi-step whitelisted action
	return True


@frappe.whitelist()
def save_fbr_settings(environment=None, base_url=None, token=None, scenario_id=None):
	"""Step 5: FBR Digital Invoicing config. The token is set only when provided,
	so re-saving without re-typing it never wipes the stored credential."""
	_guard()
	settings = frappe.get_doc("Pakistan Tax Settings")
	if environment:
		settings.fbr_environment = environment
	settings.fbr_base_url = (base_url or "").strip()
	settings.fbr_scenario_id = (scenario_id or "").strip()
	if token:
		settings.fbr_token = token
	settings.save(ignore_permissions=True)
	frappe.db.commit()  # nosemgrep: intentional persist after a multi-step whitelisted action
	return True


@frappe.whitelist()
def save_preferences(show_urdu=None):
	"""Step 6: preferences (currently the Urdu amount-in-words toggle)."""
	_guard()
	if show_urdu is not None:
		frappe.db.set_single_value(
			"Pakistan Tax Settings", "show_urdu_in_words", 1 if int(show_urdu) else 0
		)
	frappe.db.commit()  # nosemgrep: intentional persist after a multi-step whitelisted action
	return True


@frappe.whitelist()
def get_pending_pk_companies():
	"""For the onboarding banner: if the tax data has never been seeded, prompt with
	the companies still missing an NTN. Empty (no banner) once setup has run."""
	if not _is_admin():
		return []
	if frappe.db.get_single_value("Pakistan Tax Settings", "default_data_seeded"):
		return []
	return frappe.get_all("Company", filters={"custom_ntn": ["in", ["", None]]}, pluck="name")
