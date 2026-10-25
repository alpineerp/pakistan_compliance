app_name = "pakistan_compliance"
app_title = "Pakistan Compliance"
app_publisher = "Sowaan"
app_description = "Pakistan localization for ERPNext: FBR sales tax invoices, tax setup, withholding tax, print formats, and FBR digital invoicing."
app_email = "support@sowaan.com"
app_license = "mit"
source_link = "https://github.com/sowaan/pakistan_compliance"
# Small (128x128) icon for the navbar / app switcher; the full 500x500 is used for
# the marketplace listing.
app_logo_url = "/assets/pakistan_compliance/images/pk_compliance_icon.svg"
# Load our icon sprite into the desk so the workspace/desktop icon "pk-compliance"
# (symbol id "icon-pk-compliance") renders the logo instead of a letter avatar.
app_include_icons = ["/assets/pakistan_compliance/icons/pk_compliance-icons.svg"]

# Apps
# ------------------

# required_apps = []

# Note: we deliberately do NOT register `add_to_apps_screen`. On v16 that creates
# an "App"-type desktop icon whose route is an absolute URL (opens in a new tab)
# and which renders a letter avatar ("P") instead of the logo. Instead the desktop
# icon is the workspace itself (a "Link" icon) with its `app` set, configured in
# install.ensure_pk_desktop_icon; the logo comes from the custom icon sprite
# public/icons/pk_compliance-icons.svg (symbol id "icon-pk-compliance"), referenced
# by the workspace's `icon` field ("pk-compliance").

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/pakistan_compliance/css/pakistan_compliance.css"
app_include_js = "/assets/pakistan_compliance/js/pk_setup_banner.js"

# include js, css files in header of web template
# web_include_css = "/assets/pakistan_compliance/css/pakistan_compliance.css"
# web_include_js = "/assets/pakistan_compliance/js/pakistan_compliance.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "pakistan_compliance/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "pakistan_compliance/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment. Each path is registered under
# the function's own name, so print formats call money_in_words_urdu(...) directly.
jinja = {
	"methods": [
		"pakistan_compliance.utils.money_in_words_urdu",
		"pakistan_compliance.utils.show_urdu_in_words",
		"pakistan_compliance.utils.fmt_money_abs",
		"pakistan_compliance.utils.qr_png_data_uri",
	],
}

# Installation
# ------------

# before_install = "pakistan_compliance.install.before_install"
after_install = "pakistan_compliance.install.after_install"

# Re-assert the Pakistan tax master-data custom fields on every migrate (idempotent).
after_migrate = "pakistan_compliance.install.after_migrate"

# Uninstallation
# ------------

# before_uninstall = "pakistan_compliance.uninstall.before_uninstall"
# after_uninstall = "pakistan_compliance.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "pakistan_compliance.utils.before_app_install"
# after_app_install = "pakistan_compliance.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "pakistan_compliance.utils.before_app_uninstall"
# after_app_uninstall = "pakistan_compliance.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "pakistan_compliance.build.after_build"

# Desk Notifications
# ------------------
# Fresh-install safety net for the desktop icon logo (see install.boot_fix_desktop_icon).
extend_bootinfo = "pakistan_compliance.install.boot_fix_desktop_icon"

# See frappe.core.notifications.get_notification_config

# notification_config = "pakistan_compliance.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["pakistan_compliance.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Client scripts on standard doctypes
doctype_js = {"Sales Invoice": "public/js/sales_invoice_fbr.js"}

# Hook on document methods and events

# Propagate supplier-level withholding-tax config to item rows so it computes on
# ERPNext v16 (item-driven WHT). No-op on v15. See wht_setup.propagate_item_wht.
doc_events = {
	"Purchase Invoice": {
		"validate": "pakistan_compliance.wht_setup.propagate_item_wht",
	},
	"Purchase Order": {
		"validate": "pakistan_compliance.wht_setup.propagate_item_wht",
	},
	# Keep the supplier's WHT category variant in sync with its Filer/Non-Filer status.
	"Supplier": {
		"validate": "pakistan_compliance.wht_setup.sync_supplier_wht_category",
	},
}

# Scheduled Tasks
# ---------------

# Retry FBR reporting of POS sales that could not reach FBR (pakistan_compliance/pos/queue.py)
scheduler_events = {
	"cron": {
		"* * * * *": [
			"pakistan_compliance.pos.queue.retry_due",
		],
	},
}

# scheduler_events = {
# 	"all": [
# 		"pakistan_compliance.tasks.all"
# 	],
# 	"daily": [
# 		"pakistan_compliance.tasks.daily"
# 	],
# 	"hourly": [
# 		"pakistan_compliance.tasks.hourly"
# 	],
# 	"weekly": [
# 		"pakistan_compliance.tasks.weekly"
# 	],
# 	"monthly": [
# 		"pakistan_compliance.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "pakistan_compliance.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "pakistan_compliance.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "pakistan_compliance.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "pakistan_compliance.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["pakistan_compliance.utils.before_request"]
# after_request = ["pakistan_compliance.utils.after_request"]

# Job Events
# ----------
# before_job = ["pakistan_compliance.utils.before_job"]
# after_job = ["pakistan_compliance.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"pakistan_compliance.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

