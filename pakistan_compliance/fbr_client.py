# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Thin wrapper over the FBR Digital Invoicing (DI) REST API.

Just enough to validate and post a sales invoice and read back the Invoice
Reference Number (IRN); no retry/queue logic of its own. Endpoints and the
request/response shape follow the FBR/PRAL DI technical spec, but FBR's live
sandbox is the source of truth (guardrail #2): if a real response disagrees with
anything here, trust the sandbox and update this module.

The instance security token is read from Pakistan Tax Settings' encrypted
`fbr_token` and is NEVER logged (guardrail #3): errors scrub the Authorization
header.

Endpoints (relative to the configured base URL, default https://gw.fbr.gov.pk):
    POST /di_data/v1/di/validateinvoicedata_sb   (sandbox validate)
    POST /di_data/v1/di/postinvoicedata_sb        (sandbox post)
    POST /di_data/v1/di/validateinvoicedata       (production validate)
    POST /di_data/v1/di/postinvoicedata           (production post)
"""

import requests

import frappe
from frappe import _

DEFAULT_BASE_URL = "https://gw.fbr.gov.pk"
TIMEOUT = 30

# environment -> (validate suffix, post suffix)
_ENDPOINTS = {
	"Sandbox": ("/di_data/v1/di/validateinvoicedata_sb", "/di_data/v1/di/postinvoicedata_sb"),
	"Production": ("/di_data/v1/di/validateinvoicedata", "/di_data/v1/di/postinvoicedata"),
}


class FBRError(frappe.ValidationError):
	pass


def _settings():
	return frappe.get_cached_doc("Pakistan Tax Settings")


def _base_url(settings):
	return (settings.get("fbr_base_url") or DEFAULT_BASE_URL).rstrip("/")


def _environment(settings):
	return settings.get("fbr_environment") or "Sandbox"


def _token(settings):
	token = settings.get_password("fbr_token", raise_exception=False)
	if not token:
		frappe.throw(
			_("Set the FBR integrator token on Pakistan Tax Settings before reporting invoices."),
			exc=FBRError,
		)
	return token


def _request(suffix, payload):
	"""POST `payload` to the FBR DI endpoint `suffix`; return the parsed JSON.
	Scrubs the token from any error surfaced to the user."""
	settings = _settings()
	url = _base_url(settings) + suffix
	headers = {
		"Authorization": f"Bearer {_token(settings)}",
		"Content-Type": "application/json",
	}
	try:
		resp = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
	except requests.RequestException as e:
		# Never let the token leak via a header echoed in the exception.
		frappe.throw(_("Could not reach FBR: {0}").format(str(e)[:300]), exc=FBRError)

	if resp.status_code == 401:
		frappe.throw(_("FBR rejected the token (401). Check the integrator token."), exc=FBRError)
	if resp.status_code >= 500:
		frappe.throw(_("FBR server error ({0}). Try again later.").format(resp.status_code), exc=FBRError)

	try:
		return resp.json()
	except ValueError:
		frappe.throw(_("FBR returned a non-JSON response ({0}).").format(resp.status_code), exc=FBRError)


def validate_invoice(payload, environment=None):
	"""Dry-run an invoice against FBR (no IRN issued). Returns the raw response."""
	environment = environment or _environment(_settings())
	suffix = _ENDPOINTS.get(environment, _ENDPOINTS["Sandbox"])[0]
	return _request(suffix, payload)


def post_invoice(payload, environment=None):
	"""Report an invoice to FBR and get back the response carrying the IRN
	(`invoiceNumber`) and a per-item/overall `validationResponse`."""
	environment = environment or _environment(_settings())
	suffix = _ENDPOINTS.get(environment, _ENDPOINTS["Sandbox"])[1]
	return _request(suffix, payload)
