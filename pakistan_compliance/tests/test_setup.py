# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Phase 1 coverage: the Pakistan Tax Settings single and the master-data fields.

Offline: no network. Confirms the settings doctype and every custom field exist,
and that credentials save into the encrypted Password field.
"""

import frappe
from frappe.tests import IntegrationTestCase

from pakistan_compliance.install import CUSTOM_FIELDS, ensure_custom_fields


class TestPakistanSetup(IntegrationTestCase):
	def test_settings_is_single(self):
		self.assertTrue(frappe.db.exists("DocType", "Pakistan Tax Settings"))
		self.assertTrue(frappe.get_meta("Pakistan Tax Settings").issingle)

	def test_custom_fields_present(self):
		# ensure_custom_fields is idempotent, so running it here is harmless and also
		# covers a fresh-install path.
		ensure_custom_fields()
		for doctype, fields in CUSTOM_FIELDS.items():
			meta = frappe.get_meta(doctype)
			for field in fields:
				fieldname = field["fieldname"]
				self.assertTrue(meta.get_field(fieldname), f"{doctype}.{fieldname} is missing")

	def test_province_options(self):
		options = frappe.get_meta("Address").get_field("custom_province").options or ""
		for province in ("Punjab", "Sindh", "Khyber Pakhtunkhwa", "Balochistan"):
			self.assertIn(province, options)

	def test_settings_saves_encrypted_token(self):
		settings = frappe.get_single("Pakistan Tax Settings")
		settings.enabled = 1
		settings.default_province = "Sindh"
		settings.fbr_environment = "Sandbox"
		settings.fbr_base_url = "https://gw.fbr.gov.pk/"  # trailing slash -> normalized away
		settings.fbr_token = "test_fbr_token"
		settings.save()

		frappe.clear_cache(doctype="Pakistan Tax Settings")
		reloaded = frappe.get_single("Pakistan Tax Settings")
		self.assertEqual(reloaded.fbr_base_url, "https://gw.fbr.gov.pk")
		self.assertEqual(reloaded.get_password("fbr_token"), "test_fbr_token")
