// Copyright (c) 2026, AlpineERP and contributors
// For license information, please see license.txt

frappe.query_reports["FBR POS Queue"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_default("company"),
		},
		{
			fieldname: "status",
			label: __("FBR Status"),
			fieldtype: "Select",
			options: "\nFailed\nPending\nReported",
			default: "",
		},
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "retry" && data && data.retry) {
			return `<button class="btn btn-xs btn-default fbr-retry" data-doctype="${frappe.utils.escape_html(data.doctype)}" data-name="${frappe.utils.escape_html(data.name)}">${__("Retry")}</button>`;
		}
		return default_formatter(value, row, column, data);
	},
	onload(report) {
		// one handler for every Retry button of the table
		$(report.page.wrapper)
			.off("click.fbrretry")
			.on("click.fbrretry", ".fbr-retry", function () {
				const $btn = $(this).prop("disabled", true);
				frappe
					.xcall("pakistan_compliance.pos.api.retry", { doctype: $btn.data("doctype"), name: $btn.data("name") })
					.then(() => {
						frappe.show_alert({ message: __("Queued for FBR again"), indicator: "green" });
						report.refresh();
					})
					.catch(() => $btn.prop("disabled", false));
			});
		report.page.add_inner_button(__("Retry all Failed"), () => {
			frappe.confirm(__("Queue every Failed sale for FBR again?"), () =>
				frappe.xcall("pakistan_compliance.pos.api.retry_failed").then((count) => {
					frappe.show_alert({ message: __("{0} sale(s) queued", [count]), indicator: "green" });
					report.refresh();
				})
			);
		});
	},
};
