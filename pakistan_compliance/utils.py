# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""Shared helpers for Pakistan Compliance.

`money_in_words_urdu` spells a money amount in Urdu, mirroring the KSA app's
Arabic amount-in-words but backed by `indic-numtowords` because `num2words` has
no Urdu (or Hindi) backend. It is exposed to Jinja (see the `jinja` hook in
hooks.py) so print formats can render it at print time without any stored field:

    {{ money_in_words_urdu(doc.grand_total, doc.currency) }}
"""

import frappe
from frappe.utils import flt

# Urdu name of each supported currency: (main unit, 1/100 sub-unit).
# Unknown currencies fall back to the ISO code itself so we never mislabel one.
CURRENCY_UR = {
	"PKR": ("روپے", "پیسے"),
	"USD": ("امریکی ڈالر", "سینٹ"),
	"EUR": ("یورو", "سینٹ"),
	"GBP": ("برطانوی پاؤنڈ", "پینس"),
	"SAR": ("سعودی ریال", "ہلالہ"),
	"AED": ("اماراتی درہم", "فلس"),
	"INR": ("بھارتی روپے", "پیسے"),
}


def _num2words_urdu(number):
	"""Integer -> Urdu words via indic-numtowords (South Asian lakh/crore grouping)."""
	from indic_numtowords import num2words

	return num2words(int(number), lang="ur")


def money_in_words_urdu(amount, currency=None):
	"""Return `amount` spelled out in Urdu, e.g. 'ستر ہزار ایک سو اسی روپے فقط'.

	Handles the paisa (sub-unit) part and negative totals (credit / debit notes
	carry a negative grand_total). Returns '' on any failure so a print format
	never breaks over an amount it cannot spell."""
	try:
		amount = abs(flt(amount))
		main = int(amount)
		fraction = int(round((amount - main) * 100))
		if fraction == 100:  # rounding pushed it to the next whole unit
			main += 1
			fraction = 0

		main_name, fraction_name = CURRENCY_UR.get(
			(currency or "PKR").upper(), (currency or "PKR", None)
		)

		words = f"{_num2words_urdu(main)} {main_name}"
		if fraction and fraction_name:
			words += f" اور {_num2words_urdu(fraction)} {fraction_name}"
		return f"{words} فقط"
	except Exception:
		frappe.log_error(title="Pakistan Compliance: Urdu in-words failed")
		return ""


def fmt_money_abs(value, currency=None):
	"""Format the magnitude of a money value in the given currency. Returns (returns
	/ credit / debit notes) store negative amounts; on those documents we show the
	positive figure and let the 'Credit Note' / 'Debit Note' title convey direction."""
	from frappe.utils import fmt_money

	return fmt_money(abs(flt(value)), currency=currency)


def qr_png_data_uri(content, box_size=4, border=2):
	"""Render `content` to a QR code PNG and return it as a data: URI, so print
	formats can embed the FBR invoice QR inline (no external QR service, no stored
	file). Returns '' on any failure so a print format never breaks over it."""
	if not content:
		return ""
	try:
		import base64
		from io import BytesIO

		import qrcode

		qr = qrcode.QRCode(box_size=box_size, border=border)
		qr.add_data(content)
		qr.make(fit=True)
		img = qr.make_image(fill_color="black", back_color="white")
		buf = BytesIO()
		img.save(buf, format="PNG")
		return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
	except Exception:
		frappe.log_error(title="Pakistan Compliance: QR render failed")
		return ""


def show_urdu_in_words():
	"""Whether print formats should render the Urdu amount in words, from the
	'Show Urdu Amount in Words' toggle on Pakistan Tax Settings. The field default
	is on, and install.py seeds it, so a fresh (never-saved) settings doc still
	shows Urdu. (An unset Check reads back as 0, not None, so the seeding is what
	makes 'default on' real; turning the toggle off persists 0 and stays off.)"""
	return bool(frappe.db.get_single_value("Pakistan Tax Settings", "show_urdu_in_words"))
