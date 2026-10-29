// Copyright (c) 2026, AlpineERP and contributors
// For license information, please see license.txt

// Onboarding banner: nudge admins to run the Pakistan Compliance setup wizard
// until the tax data has been seeded. Dismissible per day.
$(document).on("app_ready", function () {
	const username = frappe.session.user;
	const roles = (frappe.boot && frappe.boot.user && frappe.boot.user.roles) || [];
	const eligible = username === "Administrator" || roles.includes("System Manager");
	if (!eligible) return;

	const dismiss_key = `pk_setup_banner_dismissed_${username}_${frappe.datetime.get_today()}`;
	if (localStorage.getItem(dismiss_key)) return;

	frappe
		.call({ method: "pakistan_compliance.setup_status.get_pending_pk_companies" })
		.then((r) => {
			const pending = (r && r.message) || [];
			if (pending.length) show_pk_setup_banner(pending, dismiss_key);
		})
		.catch(() => {});
});

function show_pk_setup_banner(companies, dismiss_key) {
	if (document.getElementById("pk-setup-banner")) return;
	const green = "#0b6e4f";
	const $banner = $(`
		<div id="pk-setup-banner" style="
			display:flex;align-items:center;gap:14px;
			background:linear-gradient(100deg, ${green} 0%, #08543b 100%);
			color:#fff;padding:11px 20px;border-radius:12px;margin:12px 16px;
			box-shadow:0 6px 20px rgba(11,110,79,.25);font-size:13.5px;">
			<img src="/assets/pakistan_compliance/images/pk_compliance_icon.svg"
				style="width:34px;height:34px;border-radius:9px;flex:0 0 34px;box-shadow:0 2px 6px rgba(0,0,0,.2);"/>
			<div style="flex:1;line-height:1.45;">
				<b>${__("Finish setting up Pakistan Compliance")}</b><br>
				<span style="opacity:.9;">${__("Configure your tax identity, sales tax, withholding tax and FBR e-invoicing in a quick guided wizard.")}</span>
			</div>
			<button class="btn btn-sm" id="pk-banner-setup"
				style="background:#fff;color:${green};font-weight:600;border:none;white-space:nowrap;">
				${__("Set up now")}</button>
			<button class="btn btn-sm" id="pk-banner-dismiss"
				style="background:rgba(255,255,255,.15);color:#fff;border:none;white-space:nowrap;">
				${__("Later")}</button>
		</div>`);

	// `.main-section` is a plain block scroll container (header, #body, footer
	// stacked in normal flow). Insert as a sibling right after <header> so the
	// banner stacks full-width below the desk navbar and pushes #body down.
	// (Prepending into `.layout-main-section-wrapper` put it inside the flex row
	// alongside the sidebar, so it rendered as a left column with content beside it.)
	const $header = $(".main-section > header");
	if ($header.length) $header.after($banner);
	else $("body").prepend($banner);

	$("#pk-banner-setup").on("click", () => {
		$banner.remove();
		frappe.set_route("pakistan-compliance-setup");
	});
	$("#pk-banner-dismiss").on("click", () => {
		localStorage.setItem(dismiss_key, "1");
		$banner.remove();
	});
}
