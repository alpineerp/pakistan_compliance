// Copyright (c) 2026, AlpineERP and contributors
// For license information, please see license.txt

// "Report to FBR" action on a submitted Sales Invoice (FBR Digital Invoicing).
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) {
			return;
		}
		if (frm.doc.custom_fbr_reported && frm.doc.custom_fbr_invoice_number) {
			frm.dashboard.add_indicator(
				__("FBR IRN: {0}", [frm.doc.custom_fbr_invoice_number]),
				"green"
			);
		}
		const label = frm.doc.custom_fbr_reported ? __("Re-report to FBR") : __("Report to FBR");
		frm.add_custom_button(label, () => report_to_fbr(frm), __("FBR"));
	},
});

function report_to_fbr(frm) {
	frappe.call({
		method: "pakistan_compliance.fbr_invoice.report_to_fbr",
		args: { sales_invoice: frm.doc.name },
		freeze: true,
		freeze_message: __("Reporting to FBR Digital Invoicing…"),
		callback: (r) => {
			const res = r.message || {};
			if (res.status === "Reported") {
				frappe.show_alert({
					message: __("Reported to FBR. IRN: {0}", [res.irn]),
					indicator: "green",
				});
				frm.reload_doc();
			} else {
				frappe.msgprint({
					title: __("FBR did not accept the invoice"),
					message: frappe.utils.escape_html(res.error || __("Unknown error")),
					indicator: "red",
				});
			}
		},
	});
}
