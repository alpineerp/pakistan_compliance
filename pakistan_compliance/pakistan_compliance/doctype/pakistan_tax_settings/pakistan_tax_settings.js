// Copyright (c) 2026, AlpineERP and contributors
// For license information, please see license.txt

frappe.ui.form.on("Pakistan Tax Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Set up Pakistan Taxes"), () => setup_pakistan_taxes());
		frm.add_custom_button(__("Set up Withholding Tax"), () => setup_withholding_tax());
	},
});

function setup_withholding_tax() {
	frappe.prompt(
		[
			{
				fieldname: "company",
				fieldtype: "Link",
				options: "Company",
				label: __("Company"),
				reqd: 1,
				default: frappe.defaults.get_default("company"),
				description: __(
					"Withholding tax categories (Filer and Non-Filer per income-tax section) and a WHT payable account will be created for this company. Verify the seeded rates against the current Finance Act before use. Safe to re-run; existing ones are skipped."
				),
			},
		],
		(values) => {
			frappe.call({
				method: "pakistan_compliance.wht_setup.setup_company_wht",
				args: { company: values.company },
				freeze: true,
				freeze_message: __("Creating withholding tax categories…"),
				callback: (r) => {
					const res = r.message || {};
					const msg = [
						__("WHT account created: {0}", [res.account || __("already existed")]),
						__("Withholding tax categories created: {0}", [(res.categories || []).length]),
						__("Please verify each rate against the current Finance Act / SROs."),
					].join("<br>");
					frappe.msgprint({
						title: __("Withholding tax set up"),
						message: msg,
						indicator: "green",
					});
				},
			});
		},
		__("Set up Withholding Tax"),
		__("Create")
	);
}

function setup_pakistan_taxes() {
	frappe.prompt(
		[
			{
				fieldname: "company",
				fieldtype: "Link",
				options: "Company",
				label: __("Company"),
				reqd: 1,
				default: frappe.defaults.get_default("company"),
				description: __(
					"Tax accounts and templates will be created for this company. Safe to re-run; existing ones are skipped."
				),
			},
		],
		(values) => {
			frappe.call({
				method: "pakistan_compliance.tax_setup.setup_company_taxes",
				args: { company: values.company },
				freeze: true,
				freeze_message: __("Creating tax accounts and templates…"),
				callback: (r) => {
					const res = r.message || {};
					const count = (a) => (a || []).length;
					const msg = [
						__("Accounts created: {0}", [count(res.accounts)]),
						__("Sales tax templates created: {0}", [count(res.sales_templates)]),
						__("Purchase tax templates created: {0}", [count(res.purchase_templates)]),
					].join("<br>");
					frappe.msgprint({
						title: __("Pakistan taxes set up"),
						message: msg,
						indicator: "green",
					});
				},
			});
		},
		__("Set up Pakistan Taxes"),
		__("Create")
	);
}
