# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class FBRPOSSettings(Document):
	def validate(self):
		if not 1 <= cint(self.max_attempts) <= 100:
			frappe.throw(_("Give Up After must be between 1 and 100 tries."))
		if not 3 <= cint(self.request_timeout) <= 120:
			frappe.throw(_("Wait For FBR must be between 3 and 120 seconds."))
		if self.pos_base_url and not self.pos_base_url.lower().startswith("https://"):
			frappe.throw(_("The FBR POS Service URL must start with https://"))
