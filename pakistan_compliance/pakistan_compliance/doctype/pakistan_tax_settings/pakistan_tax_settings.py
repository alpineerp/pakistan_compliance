# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class PakistanTaxSettings(Document):
	def onload(self):
		# Expose whether the (encrypted) FBR token is set, so the form can decide
		# whether to nudge the user to finish FBR setup.
		self.set_onload("has_fbr_token", bool(self.get_password("fbr_token", raise_exception=False)))

	def validate(self):
		if self.fbr_base_url:
			self.fbr_base_url = self.fbr_base_url.strip().rstrip("/")
