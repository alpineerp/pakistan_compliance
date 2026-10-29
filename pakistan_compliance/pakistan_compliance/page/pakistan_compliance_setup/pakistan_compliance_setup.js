// Copyright (c) 2026, AlpineERP and contributors
// For license information, please see license.txt

frappe.pages["pakistan-compliance-setup"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Pakistan Compliance Setup"),
		single_column: true,
	});
	inject_styles();
	document.body.classList.add("pk-wizard-fs");
	new PkSetupWizard(page).init();
};

// Full-screen wizard: hide the desk workspace sidebar while it's open (so it does
// not read as living "under" whatever workspace was last active), restore on exit.
frappe.pages["pakistan-compliance-setup"].on_page_show = function () {
	document.body.classList.add("pk-wizard-fs");
};
if (!frappe._pk_wizard_router_hook) {
	frappe._pk_wizard_router_hook = true;
	frappe.router.on("change", () => {
		if ((frappe.get_route() || [])[0] !== "pakistan-compliance-setup") {
			document.body.classList.remove("pk-wizard-fs");
		}
	});
}

const M = "pakistan_compliance";
const GREEN = "#0b6e4f";

// Inline lucide-style icons so nothing depends on a sprite being present.
const PATHS = {
	check: '<path d="M20 6 9 17l-5-5"/>',
	left: '<path d="m15 18-6-6 6-6"/>',
	right: '<path d="m9 18 6-6-6-6"/>',
	plus: '<path d="M5 12h14M12 5v14"/>',
	info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
	warn: '<path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3Z"/><path d="M12 9v4M12 17h.01"/>',
	sparkles: '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>',
	idcard: '<rect x="2" y="5" width="20" height="14" rx="2"/><circle cx="9" cy="11" r="2"/><path d="M6.2 15a3 3 0 0 1 5.6 0M16 10h2M16 14h2"/>',
	landmark: '<path d="M3 22h18M6 18v-7M10 18v-7M14 18v-7M18 18v-7M12 2 3 8h18Z"/>',
	percent: '<line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
	globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20Z"/>',
	sliders: '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
};
function ic(name, size = 16, cls = "") {
	return `<svg class="pk-ic ${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${PATHS[name] || ""}</svg>`;
}

const STEPS = [
	{ key: "welcome", title: __("Welcome"), sub: __("Choose a company"), icon: "sparkles" },
	{ key: "identity", title: __("Tax Identity"), sub: __("NTN, STRN & province"), icon: "idcard" },
	{ key: "taxes", title: __("Sales Tax Setup"), sub: __("Accounts & templates"), icon: "landmark" },
	{ key: "wht", title: __("Withholding Tax"), sub: __("Filer / Non-Filer"), icon: "percent" },
	{ key: "fbr", title: __("FBR Digital Invoicing"), sub: __("Real-time e-invoicing"), icon: "globe" },
	{ key: "prefs", title: __("Preferences"), sub: __("Print options"), icon: "sliders" },
	{ key: "finish", title: __("Finish"), sub: __("You're all set"), icon: "check" },
];

class PkSetupWizard {
	constructor(page) {
		this.page = page;
		this.i = 0;
		this.done = {};
		this.controls = {};
		this.state = {};
	}

	async init() {
		this.$body = $(this.page.main).addClass("pk-wiz-host");
		this.$body.html(`<div class="pk-wiz-loading"><span class="pk-spin"></span> ${__("Loading…")}</div>`);
		this.state = await this.call("setup_status.get_setup_state", {});
		this.done.taxes = !!this.state.tax_seeded;
		this.done.wht = !!this.state.wht_categories;
		this.render_shell();
		this.render_step();
	}

	call(method, args, freeze_message) {
		return frappe
			.call({ method: `${M}.${method}`, args, freeze: !!freeze_message, freeze_message })
			.then((r) => r.message);
	}

	render_shell() {
		const rail = STEPS.map(
			(s, idx) => `
			<div class="pk-step" data-idx="${idx}">
				<div class="pk-step-dot"><span class="pk-num">${idx + 1}</span><span class="pk-check">${ic("check", 15)}</span></div>
				<div class="pk-step-meta"><div class="pk-step-title">${s.title}</div><div class="pk-step-sub">${s.sub}</div></div>
			</div>`
		).join('<div class="pk-step-line"></div>');

		this.$body.html(`
			<div class="pk-wiz">
				<aside class="pk-rail">
					<div class="pk-brand">
						<img class="pk-brand-logo" src="/assets/pakistan_compliance/images/pk_compliance_icon.svg"/>
						<div><div class="pk-brand-title">${__("Pakistan Compliance")}</div>
						<div class="pk-brand-sub">${__("Guided setup")}</div></div>
					</div>
					<div class="pk-steps">${rail}</div>
					<div class="pk-rail-foot">${__("by AlpineERP")}</div>
				</aside>
				<section class="pk-panel">
					<div class="pk-progress"><div class="pk-progress-bar"></div></div>
					<div class="pk-content"></div>
					<footer class="pk-foot">
						<button class="btn pk-btn-ghost pk-back">${ic("left", 15)} ${__("Back")}</button>
						<div class="pk-count"></div>
						<button class="btn pk-btn-primary pk-next">${__("Next")} ${ic("right", 15)}</button>
					</footer>
				</section>
			</div>`);
		this.$content = this.$body.find(".pk-content");
		this.$body.find(".pk-back").on("click", () => this.go(this.i - 1));
		this.$body.find(".pk-next").on("click", () => this.next());
		this.$body.find(".pk-step").on("click", (e) => {
			const idx = +$(e.currentTarget).data("idx");
			if (idx < this.i) this.go(idx);
		});
	}

	update_rail() {
		this.$body.find(".pk-step").each((idx, el) => {
			const key = STEPS[idx].key;
			$(el).toggleClass("active", idx === this.i);
			$(el).toggleClass("done", Boolean(idx < this.i || (idx !== this.i && this.done[key])));
		});
		const pct = (this.i / (STEPS.length - 1)) * 100;
		this.$body.find(".pk-progress-bar").css("width", `${pct}%`);
		this.$body.find(".pk-count").text(__("Step {0} of {1}", [this.i + 1, STEPS.length]));
		const last = this.i === STEPS.length - 1;
		this.$body.find(".pk-back").prop("disabled", this.i === 0);
		this.$body.find(".pk-next").html(last ? __("Go to Workspace") : `${__("Next")} ${ic("right", 15)}`);
	}

	go(idx) {
		if (idx < 0 || idx >= STEPS.length) return;
		this.i = idx;
		this.render_step();
	}

	async next() {
		const step = STEPS[this.i];
		const ok = await this.save_step(step.key);
		if (ok === false) return;
		if (this.i === STEPS.length - 1) {
			window.location.href = this.state.workspace_route;
			return;
		}
		this.done[step.key] = true;
		this.go(this.i + 1);
	}

	render_step() {
		this.controls = {};
		this.$content.removeClass("pk-in").empty();
		const step = STEPS[this.i];
		const $c = $(`<div class="pk-step-body"></div>`).appendTo(this.$content);
		this[`step_${step.key}`]($c);
		this.update_rail();
		requestAnimationFrame(() => this.$content.addClass("pk-in"));
	}

	control(parent, df, value) {
		const $wrap = $('<div class="pk-field"></div>').appendTo(parent);
		const c = frappe.ui.form.make_control({ df, parent: $wrap.get(0), render_input: true });
		if (value !== undefined && value !== null) c.set_value(value);
		c.refresh();
		this.controls[df.fieldname] = c;
		return c;
	}

	head($c, icon, title, desc) {
		$c.append(`
			<div class="pk-head">
				<div class="pk-head-icon">${ic(icon, 22)}</div>
				<div><h2 class="pk-h">${title}</h2><p class="pk-desc">${desc}</p></div>
			</div>`);
	}

	note($c, text, muted) {
		$c.append(`<div class="pk-note ${muted ? "pk-note-muted" : ""}">${ic("info", 15)}<span>${text}</span></div>`);
	}

	step_welcome($c) {
		this.head($c, "sparkles", __("Welcome"),
			__("This wizard configures your Pakistan tax identity, sales-tax accounts, withholding tax, FBR e-invoicing and print options — one step at a time."));
		this.control($c, { fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company to configure"), reqd: 1 }, this.state.company);
		this.note($c, __("Everything here is safe to re-run; existing accounts and templates are never duplicated."));
	}

	step_identity($c) {
		this.head($c, "idcard", __("Tax Identity"),
			__("Your company's FBR registration. These print on the sales tax invoice."));
		const g = $('<div class="pk-grid"></div>').appendTo($c);
		this.control(g, { fieldtype: "Data", fieldname: "ntn", label: __("NTN (National Tax Number)") }, this.state.identity.ntn);
		this.control(g, { fieldtype: "Data", fieldname: "strn", label: __("STRN (Sales Tax Registration Number)") }, this.state.identity.strn);
		this.control($c, { fieldtype: "Select", fieldname: "default_province", label: __("Default Province"), options: ["", ...this.state.provinces].join("\n") }, this.state.default_province);
	}

	step_taxes($c) {
		this.head($c, "landmark", __("Sales Tax Setup"),
			__("Create the Chart-of-Accounts tax accounts and the Sales/Purchase Taxes and Charges Templates (federal 18%, further tax 3%, provincial services, zero-rated, exempt)."));
		this.action_step($c, {
			key: "taxes",
			button: __("Create Tax Accounts & Templates"),
			done_msg: __("Sales tax accounts and templates are ready."),
			run: () => this.call("tax_setup.setup_company_taxes", { company: this.company() }, __("Creating tax accounts & templates…")),
			summary: (r) => [
				__("Accounts created: {0}", [(r.accounts || []).length]),
				__("Sales tax templates: {0}", [(r.sales_templates || []).length]),
				__("Purchase tax templates: {0}", [(r.purchase_templates || []).length]),
			],
		});
	}

	step_wht($c) {
		this.head($c, "percent", __("Withholding Tax"),
			__("Create the WHT payable account and a Tax Withholding Category per income-tax section (153, 233, 155) in Filer and Non-Filer variants."));
		this.action_step($c, {
			key: "wht",
			button: __("Create Withholding Tax Categories"),
			done_msg: __("Withholding tax categories are ready."),
			run: () => this.call("wht_setup.setup_company_wht", { company: this.company() }, __("Creating withholding tax categories…")),
			summary: (r) => [
				__("Account: {0}", [r.account || __("already existed")]),
				__("Categories created: {0}", [(r.categories || []).length]),
			],
			warn: __("Seeded rates are the current FBR defaults — verify them against the latest Finance Act before filing."),
		});
	}

	step_fbr($c) {
		const fbr = this.state.fbr;
		this.head($c, "globe", __("FBR Digital Invoicing"),
			__("Optional. Real-time reporting to the FBR / PRAL Digital Invoicing API to get an Invoice Reference Number and QR. You can skip and set this up later."));
		this.control($c, { fieldtype: "Select", fieldname: "environment", label: __("Environment"), options: "Sandbox\nProduction" }, fbr.environment);
		const g = $('<div class="pk-grid"></div>').appendTo($c);
		this.control(g, { fieldtype: "Data", fieldname: "base_url", label: __("FBR Base URL"), description: __("Blank = https://gw.fbr.gov.pk") }, fbr.base_url);
		this.control(g, { fieldtype: "Data", fieldname: "scenario_id", label: __("Sandbox Scenario ID"), description: __("e.g. SN001 (Sandbox only)") }, fbr.scenario_id);
		this.control($c, {
			fieldtype: "Password",
			fieldname: "token",
			label: __("Integrator Token"),
			description: fbr.has_token ? __("A token is already saved. Leave blank to keep it.") : __("From the FBR IRIS portal. Stored encrypted."),
		});
		this.note($c, __("Not sure yet? Click Next to skip — nothing is required here."), true);
	}

	step_prefs($c) {
		this.head($c, "sliders", __("Preferences"), __("Fine-tune how the Pakistan print formats look."));
		const $sw = $(`
			<label class="pk-switch">
				<input type="checkbox" ${this.state.show_urdu ? "checked" : ""}/>
				<span class="pk-switch-track"><span class="pk-switch-thumb"></span></span>
				<span class="pk-switch-label"><b>${__("Show Urdu amount in words")}</b><small>${__("Print the invoice total spelled out in Urdu, under the English line.")}</small></span>
			</label>`).appendTo($c);
		this._show_urdu = () => $sw.find("input").is(":checked");
		this.note($c, __("The Pakistan print formats are already the default for invoices, orders, delivery notes, quotations and payments."));
	}

	step_finish($c) {
		const s = this.state;
		const rows = [
			[__("Company"), this.company()],
			[__("Tax identity"), s.identity.ntn ? __("NTN set") : __("Not set")],
			[__("Sales tax setup"), this.done.taxes ? __("Done") : __("Skipped")],
			[__("Withholding tax"), this.done.wht ? __("Done") : __("Skipped")],
			[__("FBR e-invoicing"), s.fbr.has_token ? __("Token saved") : __("Not configured")],
		];
		$c.append(`
			<div class="pk-finish">
				<div class="pk-finish-badge">${ic("check", 34)}</div>
				<h2 class="pk-h">${__("You're all set!")}</h2>
				<p class="pk-desc">${__("Pakistan Compliance is configured. Open the workspace to start invoicing, or fine-tune anything in Pakistan Tax Settings.")}</p>
				<div class="pk-summary">${rows.map((r) => `<div class="pk-summary-row"><span>${r[0]}</span><b>${frappe.utils.escape_html(String(r[1] || "—"))}</b></div>`).join("")}</div>
			</div>`);
	}

	action_step($c, opt) {
		const $box = $(`<div class="pk-action"></div>`).appendTo($c);
		const render_done = (lines, warn) => {
			$box.html(`
				<div class="pk-result">
					<div class="pk-result-icon">${ic("check", 20)}</div>
					<div><div class="pk-result-title">${opt.done_msg}</div>
					<ul class="pk-result-list">${(lines || []).map((l) => `<li>${l}</li>`).join("")}</ul></div>
				</div>
				${warn ? `<div class="pk-warn">${ic("warn", 15)}<span>${warn}</span></div>` : ""}
				<button class="btn pk-btn-soft pk-rerun">${__("Run again")}</button>`);
			$box.find(".pk-rerun").on("click", run);
			this.done[opt.key] = true;
			this.update_rail();
		};
		const run = async () => {
			try {
				const r = await opt.run();
				render_done(opt.summary ? opt.summary(r) : [], opt.warn);
			} catch (e) {
				/* frappe surfaces the error */
			}
		};
		if (this.done[opt.key]) {
			render_done([__("Already configured for this company.")], opt.warn);
		} else {
			$box.html(`<button class="btn pk-btn-primary pk-run">${ic("plus", 15)} ${opt.button}</button>
				<div class="pk-run-hint">${__("Required to continue.")}</div>`);
			$box.find(".pk-run").on("click", run);
		}
	}

	company() {
		return (this.controls.company && this.controls.company.get_value()) || this.state.company;
	}

	async save_step(key) {
		if (key === "welcome") {
			const c = this.company();
			if (!c) {
				frappe.throw(__("Please select a company."));
				return false;
			}
			if (c !== this.state.company) {
				this.state = await this.call("setup_status.get_setup_state", { company: c });
				this.done.taxes = !!this.state.tax_seeded;
				this.done.wht = !!this.state.wht_categories;
			}
			return true;
		}
		if (key === "identity") {
			await this.call("setup_status.save_company_identity", {
				company: this.company(),
				ntn: this.controls.ntn.get_value(),
				strn: this.controls.strn.get_value(),
				default_province: this.controls.default_province.get_value(),
			});
			this.state.identity.ntn = this.controls.ntn.get_value();
			return true;
		}
		if ((key === "taxes" || key === "wht") && !this.done[key]) {
			frappe.msgprint({
				title: __("One step to go"),
				message: __("Run the action above to continue, or use Back to revisit an earlier step."),
				indicator: "orange",
			});
			return false;
		}
		if (key === "fbr") {
			const token = this.controls.token.get_value();
			await this.call("setup_status.save_fbr_settings", {
				environment: this.controls.environment.get_value(),
				base_url: this.controls.base_url.get_value(),
				scenario_id: this.controls.scenario_id.get_value(),
				token: token || undefined,
			});
			this.state.fbr.has_token = this.state.fbr.has_token || !!token;
			return true;
		}
		if (key === "prefs") {
			await this.call("setup_status.save_preferences", { show_urdu: this._show_urdu() ? 1 : 0 });
			this.state.show_urdu = this._show_urdu();
			return true;
		}
		return true;
	}
}

function inject_styles() {
	if (document.getElementById("pk-wiz-styles")) return;
	const css = `
	body.pk-wizard-fs .body-sidebar-container { display: none !important; }
	.pk-wiz-host { background: var(--gray-100, #f4f5f6); padding: 24px 16px; min-height: calc(100vh - 120px); }
	.pk-wiz-loading { text-align:center; color: var(--text-muted); padding: 80px 0; }
	.pk-spin { display:inline-block; width:14px;height:14px;border:2px solid #d7dde0;border-top-color:${GREEN};border-radius:50%;animation:pkspin .7s linear infinite;vertical-align:middle;}
	@keyframes pkspin { to { transform: rotate(360deg); } }
	.pk-ic { display:inline-block; vertical-align:middle; }
	.pk-wiz { display:flex; max-width: 980px; margin: 0 auto; background:#fff; border-radius:18px; box-shadow: 0 12px 40px rgba(11,110,79,.10), 0 2px 8px rgba(0,0,0,.05); overflow:hidden; min-height: 560px; }
	.pk-rail { width: 290px; flex:0 0 290px; background: linear-gradient(165deg, ${GREEN} 0%, #08543b 100%); color:#eafaf3; padding: 26px 22px; display:flex; flex-direction:column; }
	.pk-brand { display:flex; align-items:center; gap:12px; margin-bottom: 24px; }
	.pk-brand-logo { width:42px; height:42px; border-radius:11px; box-shadow:0 3px 10px rgba(0,0,0,.2); }
	.pk-brand-title { font-weight:700; font-size:15px; color:#fff; }
	.pk-brand-sub { font-size:11.5px; opacity:.8; }
	.pk-steps { display:flex; flex-direction:column; flex:1; }
	.pk-step { display:flex; align-items:center; gap:13px; padding:6px 0; opacity:.7; transition:opacity .2s; }
	.pk-step.active, .pk-step.done { opacity:1; }
	.pk-step.done { cursor:pointer; }
	.pk-step-line { width:2px; height:11px; background:rgba(255,255,255,.22); margin-left:15px; }
	.pk-step-dot { position:relative; width:32px;height:32px;flex:0 0 32px; border-radius:50%; background:rgba(255,255,255,.13); border:2px solid rgba(255,255,255,.28); display:flex; align-items:center; justify-content:center; font-size:12.5px; font-weight:600; color:#fff; transition:all .2s; }
	.pk-step.active .pk-step-dot { background:#fff; color:${GREEN}; border-color:#fff; box-shadow:0 0 0 4px rgba(255,255,255,.16); }
	.pk-step.done .pk-step-dot { background:#eafaf3; border-color:#eafaf3; color:${GREEN}; }
	.pk-step .pk-check { display:none; }
	.pk-step.done .pk-num { display:none; }
	.pk-step.done .pk-check { display:inline-flex; }
	.pk-step-title { font-size:13.5px; font-weight:600; color:#fff; line-height:1.2; }
	.pk-step-sub { font-size:11px; opacity:.72; }
	.pk-rail-foot { font-size:11px; opacity:.55; padding-top:12px; }
	.pk-panel { flex:1; display:flex; flex-direction:column; }
	.pk-progress { height:4px; background:#eef1f2; }
	.pk-progress-bar { height:100%; width:0; background:${GREEN}; transition:width .35s cubic-bezier(.4,0,.2,1); }
	.pk-content { flex:1; padding: 34px 40px; overflow-y:auto; opacity:0; transform: translateY(8px); transition: opacity .28s, transform .28s; }
	.pk-content.pk-in { opacity:1; transform:none; }
	.pk-head { display:flex; gap:15px; align-items:flex-start; margin-bottom:22px; }
	.pk-head-icon { width:44px;height:44px;flex:0 0 44px; border-radius:12px; background:#eef6f2; color:${GREEN}; display:flex;align-items:center;justify-content:center; }
	.pk-h { font-size:20px; font-weight:700; margin:0 0 4px; color:#1f272e; }
	.pk-desc { color:#6b7680; font-size:13px; line-height:1.6; margin:0; }
	.pk-grid { display:grid; grid-template-columns:1fr 1fr; gap:0 18px; }
	.pk-field { margin-bottom:14px; }
	.pk-field .control-label { font-size:12px; color:#4a545c; }
	.pk-note { margin-top:18px; font-size:12.5px; color:#5a6a6c; background:#f5f8f7; border:1px solid #e6efeb; border-radius:9px; padding:11px 13px; display:flex; gap:9px; align-items:flex-start; line-height:1.5; }
	.pk-note .pk-ic { flex:0 0 15px; color:${GREEN}; margin-top:1px; }
	.pk-note-muted { background:#f7f8f9; border-color:#eef0f1; color:#7a848c; }
	.pk-note-muted .pk-ic { color:#9aa4ab; }
	.pk-action { margin-top:8px; }
	.pk-run-hint { font-size:11.5px; color:#9aa4ab; margin-top:9px; }
	.pk-result { display:flex; gap:13px; background:#f0f8f4; border:1px solid #cfe7db; border-radius:11px; padding:15px 16px; }
	.pk-result-icon { width:34px;height:34px;flex:0 0 34px; border-radius:50%; background:${GREEN}; color:#fff; display:flex;align-items:center;justify-content:center; }
	.pk-result-title { font-weight:600; color:#1f272e; margin-bottom:4px; }
	.pk-result-list { margin:0; padding-left:16px; color:#4a545c; font-size:12.5px; line-height:1.7; }
	.pk-warn { margin-top:12px; font-size:12px; color:#8a5a00; background:#fff7e8; border:1px solid #f3e2bf; border-radius:9px; padding:10px 12px; display:flex; gap:8px; align-items:flex-start; line-height:1.5; }
	.pk-warn .pk-ic { flex:0 0 15px; color:#c8890a; margin-top:1px; }
	.pk-rerun { margin-top:12px; }
	.pk-switch { display:flex; align-items:center; gap:14px; cursor:pointer; padding:14px 16px; border:1px solid #e6ebee; border-radius:12px; }
	.pk-switch input { display:none; }
	.pk-switch-track { width:44px;height:25px;flex:0 0 44px; background:#cdd5da; border-radius:20px; position:relative; transition:background .2s; }
	.pk-switch-thumb { position:absolute; top:3px; left:3px; width:19px;height:19px; background:#fff; border-radius:50%; transition:left .2s; box-shadow:0 1px 3px rgba(0,0,0,.25); }
	.pk-switch input:checked + .pk-switch-track { background:${GREEN}; }
	.pk-switch input:checked + .pk-switch-track .pk-switch-thumb { left:22px; }
	.pk-switch-label b { display:block; font-size:13.5px; color:#1f272e; }
	.pk-switch-label small { color:#7a848c; font-size:12px; }
	.pk-finish { text-align:center; padding-top:14px; }
	.pk-finish-badge { width:70px;height:70px; margin:0 auto 18px; border-radius:50%; background:${GREEN}; color:#fff; display:flex;align-items:center;justify-content:center; box-shadow:0 8px 24px rgba(11,110,79,.35); }
	.pk-summary { max-width:420px; margin:22px auto 0; text-align:left; border:1px solid #eef1f2; border-radius:12px; overflow:hidden; }
	.pk-summary-row { display:flex; justify-content:space-between; padding:11px 16px; font-size:13px; border-bottom:1px solid #f1f4f5; }
	.pk-summary-row:last-child { border-bottom:none; }
	.pk-summary-row span { color:#6b7680; }
	.pk-summary-row b { color:#1f272e; }
	.pk-foot { display:flex; align-items:center; justify-content:space-between; padding:15px 40px; border-top:1px solid #eef1f2; background:#fcfdfd; }
	.pk-count { font-size:12px; color:#9aa4ab; }
	.pk-btn-primary { background:${GREEN}; color:#fff; border:none; font-weight:600; padding:8px 20px; border-radius:9px; }
	.pk-btn-primary:hover { background:#095c41; color:#fff; }
	.pk-btn-ghost { background:transparent; color:#6b7680; border:none; font-weight:500; }
	.pk-btn-ghost:hover { color:#1f272e; }
	.pk-btn-ghost:disabled { opacity:.4; }
	.pk-btn-soft { background:#eef6f2; color:${GREEN}; border:none; font-weight:600; }
	.pk-btn-soft:hover { background:#e2efe9; color:#095c41; }
	@media (max-width: 720px) { .pk-rail { display:none; } .pk-content, .pk-foot { padding-left:22px; padding-right:22px; } .pk-grid { grid-template-columns:1fr; } }
	`;
	$("<style>", { id: "pk-wiz-styles", html: css }).appendTo(document.head);
}
