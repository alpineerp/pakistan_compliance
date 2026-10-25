# Copyright (c) 2026, Sowaan and contributors
# For license information, please see license.txt

frappe.ui.form.on("FBR POS Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Check Settings"), () => {
			frappe.call({
				method: "pakistan_compliance.pos.api.check_settings",
				freeze: true,
				callback: (r) => frappe.msgprint(r.message),
			});
		});
		frm.add_custom_button(__("Retry Failed Invoices"), () => {
			frappe.call({
				method: "pakistan_compliance.pos.api.retry_failed",
				freeze: true,
				callback: (r) =>
					frappe.show_alert({ message: __("{0} invoices queued again", [r.message]), indicator: "green" }),
			});
		});
	},
});
