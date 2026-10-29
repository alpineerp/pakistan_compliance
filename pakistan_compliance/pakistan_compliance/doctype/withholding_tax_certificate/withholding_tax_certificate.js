// Copyright (c) 2026, AlpineERP and contributors
// For license information, please see license.txt

frappe.ui.form.on("Withholding Tax Certificate", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Fetch Deductions"), () => fetch_deductions(frm));
		}
	},
});

function fetch_deductions(frm) {
	frm.call({
		doc: frm.doc,
		method: "fetch_deductions",
		freeze: true,
		freeze_message: __("Fetching withholding tax deductions…"),
		callback: (r) => {
			frm.refresh_field("deductions");
			frm.refresh_field("total_gross");
			frm.refresh_field("total_tax");
			frappe.show_alert({
				message: __("{0} deduction(s) found", [r.message || 0]),
				indicator: (r.message ? "green" : "orange"),
			});
			frm.dirty();
		},
	});
}
