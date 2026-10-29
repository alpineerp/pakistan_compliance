# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Coverage for the setup-wizard backend (setup_status)."""

import frappe
from frappe.tests import IntegrationTestCase

from pakistan_compliance import setup_status


class TestSetupStatus(IntegrationTestCase):
	def test_get_setup_state_shape(self):
		state = setup_status.get_setup_state()
		for key in ("company", "companies", "provinces", "identity", "tax_seeded", "fbr", "show_urdu"):
			self.assertIn(key, state)
		# the FBR token is never echoed back, only a boolean
		self.assertIn("has_token", state["fbr"])
		self.assertNotIn("token", state["fbr"])
		self.assertIsInstance(state["fbr"]["has_token"], bool)

	def test_provinces_listed(self):
		self.assertIn("Sindh", setup_status.get_setup_state()["provinces"])

	def test_pending_empty_once_seeded(self):
		# On a site where tax data has been seeded, the onboarding banner shows nothing.
		if frappe.db.get_single_value("Pakistan Tax Settings", "default_data_seeded"):
			self.assertEqual(setup_status.get_pending_pk_companies(), [])
