# Copyright (c) 2026, AlpineERP and contributors
# For license information, please see license.txt

"""FBR reporting of point-of-sale sales: the retry queue, the FBR POS (IMS) client against a
fake FBR, Digital Invoicing of POS Invoices against a patched DI client, and the receipt data.

No FBR service is contacted: `requests.post` and the DI client are replaced, and the default
environment is Mock. These tests prove OUR behaviour (queueing, retries, never blocking a sale,
no secrets leaking); they cannot prove FBR accepts the payload (see the module docstring of
pos/ims_client.py)."""

import json
from unittest import mock

import requests

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from pakistan_compliance import fbr_client, fbr_invoice
from pakistan_compliance.pos import api, digital, ims_client, queue, receipt, settings
from pakistan_compliance.pos.ims_client import FbrRejected, FbrTransient

NAMES = {"POS Invoice": "FBRPOS-TEST-POSINV", "Sales Invoice": "FBRPOS-TEST-SINV"}
OK_DI = {
	"invoiceNumber": "7000007DI1234567890",
	"validationResponse": {"statusCode": "00", "status": "Valid", "error": "", "invoiceStatuses": []},
}


def set_settings(**values):
	doc = frappe.get_doc("FBR POS Settings")
	doc.update(values)
	doc.save(ignore_permissions=True)


class TestPosFbr(IntegrationTestCase):
	def setUp(self):
		set_settings(environment="Mock", show_qr=1, max_attempts=10, request_timeout=20, pos_base_url="", pos_id="", pos_token="")
		self.enqueued = []
		patcher = mock.patch("frappe.enqueue", side_effect=lambda *a, **k: self.enqueued.append((a, k)))
		patcher.start()
		self.addCleanup(patcher.stop)
		self.sale = {dt: self.make_sale(dt) for dt in NAMES}
		self.addCleanup(self.drop_sales)

	def tearDown(self):
		frappe.set_user("Administrator")
		# leave the settings as a fresh site has them, whatever a test changed
		set_settings(environment="Mock", show_qr=1, max_attempts=10, pos_base_url="", pos_id="", pos_token="")

	def make_sale(self, doctype):
		"""A bare submitted invoice row (queue state needs only the row, not a full sale)."""
		frappe.db.delete(doctype, {"name": NAMES[doctype]})
		doc = frappe.new_doc(doctype)
		doc.name = NAMES[doctype]
		doc.company = frappe.get_all("Company", pluck="name", limit=1)[0]
		doc.customer = self._any_customer()
		doc.posting_date = "2026-10-25"
		doc.docstatus = 1
		doc.db_insert()
		return doc.name

	def _any_customer(self):
		"""A customer to point the sale at; built here so a clean site (no demo data) works."""
		name = frappe.get_all("Customer", pluck="name", limit=1)
		if name:
			return name[0]
		return (
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "PK POS Test Customer",
					"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
					"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def drop_sales(self):
		for doctype, name in NAMES.items():
			frappe.db.delete(doctype, {"name": name})
			frappe.db.delete("FBR POS Log", {"document": name})

	def row(self, doctype="POS Invoice"):
		return frappe.db.get_value(doctype, NAMES[doctype], [*receipt.FIELDS, "custom_fbr_attempts", "custom_fbr_next_attempt", "custom_fbr_channels", "custom_fbr_reported"], as_dict=True)

	def logs(self, doctype="POS Invoice"):
		return frappe.get_all("FBR POS Log", filters={"document": NAMES[doctype]}, fields=["channel", "status", "fbr_invoice_number", "attempt"], order_by="creation asc")

	# --- the queue ----------------------------------------------------------------------------

	def test_a_sale_is_queued_then_reported_with_a_mock_number(self):
		self.assertEqual(queue.enqueue("POS Invoice", NAMES["POS Invoice"], "FBR POS"), ["pos"])
		self.assertEqual(self.row().custom_fbr_status, "Pending")
		self.assertEqual(self.enqueued[-1][1]["name"], NAMES["POS Invoice"])
		queue.process("POS Invoice", NAMES["POS Invoice"])
		row = self.row()
		self.assertEqual(row.custom_fbr_status, "Reported")
		self.assertTrue(row.custom_fbr_pos_number.startswith("MOCK-"))
		self.assertEqual(row.custom_fbr_qr_payload, row.custom_fbr_pos_number)
		self.assertEqual([(l.channel, l.status) for l in self.logs()], [("FBR POS", "Reported")])
		# a second run never issues a second number or a second log row
		queue.process("POS Invoice", NAMES["POS Invoice"])
		self.assertEqual(self.row().custom_fbr_pos_number, row.custom_fbr_pos_number)
		self.assertEqual(len(self.logs()), 1)

	def test_the_mode_decides_the_channels(self):
		self.assertEqual(settings.channels_for("FBR POS"), ["pos"])
		self.assertEqual(settings.channels_for("Digital Invoicing"), ["di"])
		self.assertEqual(settings.channels_for("Both"), ["pos", "di"])
		self.assertEqual(settings.channels_for("None"), [])
		self.assertEqual(queue.enqueue("POS Invoice", NAMES["POS Invoice"], "None"), [])
		self.assertFalse(self.row().custom_fbr_status)
		with self.assertRaises(frappe.ValidationError):
			queue.enqueue("Quotation", "X", "FBR POS")

	def test_digital_invoicing_of_a_pos_invoice_and_both_channels(self):
		queue.enqueue("POS Invoice", NAMES["POS Invoice"], "Both")
		queue.process("POS Invoice", NAMES["POS Invoice"])
		row = self.row()
		self.assertEqual(row.custom_fbr_status, "Reported")
		self.assertTrue(row.custom_fbr_pos_number.startswith("MOCK-"))
		self.assertTrue(row.custom_fbr_invoice_number.startswith("MOCKDI-"))
		self.assertEqual(row.custom_fbr_reported, 1)
		self.assertEqual(row.custom_fbr_qr_payload, row.custom_fbr_pos_number)  # the fiscal number is the QR
		self.assertEqual({l.channel for l in self.logs()}, {"FBR POS", "Digital Invoicing"})

	def test_fbr_down_retries_with_growing_waits_then_fails_for_a_manager(self):
		set_settings(max_attempts=3)
		queue.enqueue("POS Invoice", NAMES["POS Invoice"], "FBR POS")
		with mock.patch.object(ims_client, "post", side_effect=FbrTransient("FBR is busy or down (503).")):
			queue.process("POS Invoice", NAMES["POS Invoice"])
			row = self.row()
			self.assertEqual((row.custom_fbr_status, row.custom_fbr_attempts), ("Pending", 1))
			self.assertGreater(row.custom_fbr_next_attempt, now_datetime())
			self.assertIn("503", row.custom_fbr_error)
			queue.process("POS Invoice", NAMES["POS Invoice"])
			self.assertEqual(self.row().custom_fbr_attempts, 2)
			queue.process("POS Invoice", NAMES["POS Invoice"])
		self.assertEqual(self.row().custom_fbr_status, "Failed")
		self.assertEqual([l.status for l in self.logs()], ["Retrying", "Retrying", "Failed"])
		self.assertEqual(frappe.db.get_value("POS Invoice", NAMES["POS Invoice"], "docstatus"), 1)

	def test_waits_grow_and_cap(self):
		self.assertEqual([queue.wait_seconds(n) for n in (1, 2, 3, 8, 9, 50)], [30, 60, 120, 3600, 3600, 3600])

	def test_retry_due_picks_up_only_what_is_due(self):
		name = NAMES["POS Invoice"]
		queue.enqueue("POS Invoice", name, "FBR POS")
		frappe.db.set_value("POS Invoice", name, "custom_fbr_next_attempt", add_to_date(now_datetime(), minutes=10), update_modified=False)
		with mock.patch.object(queue, "process") as process:
			queue.retry_due()
			self.assertNotIn(mock.call("POS Invoice", name), process.call_args_list)
			frappe.db.set_value("POS Invoice", name, "custom_fbr_next_attempt", add_to_date(now_datetime(), minutes=-1), update_modified=False)
			queue.retry_due()
			self.assertIn(mock.call("POS Invoice", name), process.call_args_list)

	def test_a_sale_another_worker_is_sending_waits_until_it_is_stale(self):
		name = NAMES["POS Invoice"]
		queue.enqueue("POS Invoice", name, "FBR POS")
		frappe.db.set_value("POS Invoice", name, {"custom_fbr_status": "Sending", "custom_fbr_next_attempt": now_datetime()}, update_modified=False)
		with mock.patch.object(ims_client, "post", return_value=("X-1", {}, {})) as post:
			queue.process("POS Invoice", name)
			post.assert_not_called()
			frappe.db.set_value("POS Invoice", name, "custom_fbr_next_attempt", add_to_date(now_datetime(), minutes=-30), update_modified=False)
			queue.process("POS Invoice", name)
			post.assert_called_once()
		self.assertEqual(self.row().custom_fbr_pos_number, "X-1")

	def test_a_refusal_is_final_and_a_retry_starts_fresh(self):
		name = NAMES["POS Invoice"]
		queue.enqueue("POS Invoice", name, "FBR POS")
		with mock.patch.object(ims_client, "post", side_effect=FbrRejected("Invalid buyer NTN")):
			queue.process("POS Invoice", name)
		row = self.row()
		self.assertEqual((row.custom_fbr_status, row.custom_fbr_error), ("Failed", "Invalid buyer NTN"))
		self.assertEqual(api.retry("POS Invoice", name), {"queued": 1})
		self.assertEqual(self.row().custom_fbr_status, "Pending")
		queue.process("POS Invoice", name)
		self.assertEqual(self.row().custom_fbr_status, "Reported")
		with self.assertRaises(frappe.ValidationError):
			api.retry("POS Invoice", name)  # nothing to retry once reported

	def test_both_channels_keep_what_succeeded_when_the_other_fails(self):
		name = NAMES["POS Invoice"]
		queue.enqueue("POS Invoice", name, "Both")
		with mock.patch.object(ims_client, "post", return_value=("POS-1", {}, {})), mock.patch.object(digital, "post", side_effect=FbrTransient("down")):
			queue.process("POS Invoice", name)
		row = self.row()
		self.assertEqual((row.custom_fbr_status, row.custom_fbr_pos_number, row.custom_fbr_channels), ("Pending", "POS-1", "di"))
		with mock.patch.object(ims_client, "post") as pos, mock.patch.object(digital, "post", return_value=("IRN-9", None, {})):
			queue.process("POS Invoice", name)
			pos.assert_not_called()  # only the channel still owed
		row = self.row()
		self.assertEqual((row.custom_fbr_status, row.custom_fbr_pos_number, row.custom_fbr_invoice_number), ("Reported", "POS-1", "IRN-9"))

	def test_an_unexpected_bug_never_raises_and_hides_its_text(self):
		queue.enqueue("POS Invoice", NAMES["POS Invoice"], "FBR POS")
		with mock.patch.object(ims_client, "post", side_effect=RuntimeError("boom")):
			queue.process("POS Invoice", NAMES["POS Invoice"])
		row = self.row()
		self.assertEqual(row.custom_fbr_status, "Failed")
		self.assertNotIn("boom", row.custom_fbr_error)

	def test_sales_invoices_use_the_same_queue(self):
		queue.enqueue("Sales Invoice", NAMES["Sales Invoice"], "FBR POS")
		queue.process("Sales Invoice", NAMES["Sales Invoice"])
		self.assertEqual(self.row("Sales Invoice").custom_fbr_status, "Reported")

	# --- Digital Invoicing --------------------------------------------------------------------

	def test_digital_invoicing_of_a_pos_invoice_uses_the_existing_payload_client_and_parser(self):
		set_settings(environment="Sandbox")
		doc = frappe.get_doc("POS Invoice", NAMES["POS Invoice"])
		with mock.patch.object(fbr_invoice, "build_invoice_payload", return_value={"invoiceType": "Sale Invoice"}) as build, \
			mock.patch.object(fbr_client, "post_invoice", return_value=OK_DI) as post:
			irn, request, response = digital.post(doc)
		self.assertEqual(irn, "7000007DI1234567890")
		build.assert_called_once_with(doc)
		self.assertEqual(post.call_args.args[0], {"invoiceType": "Sale Invoice"})

		bad = {"invoiceNumber": "", "validationResponse": {"statusCode": "01", "error": "", "invoiceStatuses": [{"itemSNo": "1", "error": "Invalid registration type"}]}}
		with mock.patch.object(fbr_invoice, "build_invoice_payload", return_value={}), mock.patch.object(fbr_client, "post_invoice", return_value=bad):
			with self.assertRaises(FbrRejected) as refused:
				digital.post(doc)
		self.assertIn("Invalid registration type", str(refused.exception))
		with mock.patch.object(fbr_invoice, "build_invoice_payload", return_value={}), mock.patch.object(fbr_client, "post_invoice", side_effect=fbr_client.FBRError("Could not reach FBR")):
			with self.assertRaises(FbrTransient):
				digital.post(doc)

	def test_a_sales_invoice_goes_through_report_to_fbr_unchanged(self):
		set_settings(environment="Sandbox")
		doc = frappe.get_doc("Sales Invoice", NAMES["Sales Invoice"])
		with mock.patch.object(fbr_invoice, "report_to_fbr", return_value={"status": "Reported", "irn": "IRN-5", "error": ""}) as report:
			self.assertEqual(digital.post(doc)[0], "IRN-5")
			report.assert_called_once_with(NAMES["Sales Invoice"])
			report.return_value = {"status": "Failed", "irn": "", "error": "Invalid HS code"}
			with self.assertRaises(FbrRejected):
				digital.post(doc)

	# --- the FBR POS client -------------------------------------------------------------------

	def test_payload_maps_sale_tax_buyer_and_returns(self):
		doc = frappe.new_doc("POS Invoice")
		doc.update({"name": "SALE-1", "customer": frappe.get_all("Customer", pluck="name", limit=1)[0], "posting_date": "2026-10-25", "posting_time": "11:30:00", "net_total": 1000, "total_taxes_and_charges": 180, "grand_total": 1180, "rounded_total": 1180, "total_qty": 2})
		doc.append("items", {"item_code": "ANY", "item_name": "Mineral Water", "qty": 2, "net_amount": 1000})
		doc.append("taxes", {"charge_type": "On Net Total", "description": "Sales Tax 18%", "rate": 18, "tax_amount": 180})
		payload = ims_client.build_payload(doc)
		self.assertEqual((payload["USIN"], payload["TotalBillAmount"], payload["TotalSaleValue"], payload["TotalTaxCharged"], payload["InvoiceType"]), ("SALE-1", 1180, 1000, 180, ims_client.INVOICE_NEW))
		self.assertEqual(payload["DateTime"], "2026-10-25 11:30:00")
		item = payload["Items"][0]
		self.assertEqual((item["TaxRate"], item["SaleValue"], item["TaxCharged"], item["TotalAmount"]), (18, 1000, 180, 1180))

		doc.update({"is_return": 1, "return_against": "SALE-0", "net_total": -1000, "grand_total": -1180, "rounded_total": -1180, "total_qty": -2, "total_taxes_and_charges": -180})
		doc.items[0].update({"qty": -2, "net_amount": -1000})
		payload = ims_client.build_payload(doc)
		self.assertEqual((payload["InvoiceType"], payload["RefUSIN"], payload["TotalBillAmount"]), (ims_client.INVOICE_CREDIT, "SALE-0", 1180))

	def test_mock_numbers_are_stable_per_invoice_and_marked(self):
		doc = frappe.get_doc("POS Invoice", NAMES["POS Invoice"])
		self.assertEqual(ims_client.post(doc)[0], ims_client.post(doc)[0])
		self.assertTrue(ims_client.post(doc)[0].startswith("MOCK-"))

	def fake_response(self, status_code=200, body=None, json_ok=True):
		response = mock.Mock(status_code=status_code)
		response.json.side_effect = (lambda: body) if json_ok else ValueError("not json")
		return response

	def test_the_client_against_a_fake_fbr(self):
		set_settings(environment="Sandbox", pos_base_url="https://fbr.example.test/post", pos_id="POS-77", pos_token="super-secret-token")
		doc = frappe.get_doc("POS Invoice", NAMES["POS Invoice"])
		with mock.patch.object(ims_client, "build_payload", return_value={"USIN": doc.name}):
			with mock.patch("requests.post", return_value=self.fake_response(200, {"InvoiceNumber": "FBR-0001", "Code": "100", "Response": "ok"})) as post:
				number, request, response = ims_client.post(doc)
				self.assertEqual(number, "FBR-0001")
				args, kwargs = post.call_args
				self.assertEqual(args[0], "https://fbr.example.test/post")
				self.assertEqual(kwargs["headers"]["Authorization"], "Bearer super-secret-token")
			for code in (500, 503, 429, 401):
				with mock.patch("requests.post", return_value=self.fake_response(code, {})):
					with self.assertRaises(FbrTransient):
						ims_client.post(doc)
			with mock.patch("requests.post", return_value=self.fake_response(200, json_ok=False)):
				with self.assertRaises(FbrTransient):
					ims_client.post(doc)
			with mock.patch("requests.post", return_value=self.fake_response(200, {"Code": "210", "Response": "Invalid POS ID"})):
				with self.assertRaises(FbrRejected) as refused:
					ims_client.post(doc)
				self.assertIn("Invalid POS ID", str(refused.exception))
			# the token must not leak through a network error
			with mock.patch("requests.post", side_effect=requests.ConnectionError("Bearer super-secret-token refused")):
				with self.assertRaises(FbrTransient) as down:
					ims_client.post(doc)
				self.assertNotIn("super-secret-token", str(down.exception))
			# half-configured real mode is refused clearly, and nothing is sent
			set_settings(pos_base_url="")
			with mock.patch("requests.post") as post:
				with self.assertRaises(FbrRejected):
					ims_client.post(doc)
				post.assert_not_called()

	# --- receipt data and access ---------------------------------------------------------------

	def test_receipt_status_has_number_qr_notice_and_no_secrets(self):
		set_settings(environment="Sandbox", pos_base_url="https://fbr.example.test/post", pos_id="POS-77", pos_token="super-secret-token")
		queue.enqueue("POS Invoice", NAMES["POS Invoice"], "FBR POS")
		with mock.patch.object(ims_client, "post", return_value=("FBR-0001", {}, {})):
			queue.process("POS Invoice", NAMES["POS Invoice"])
		data = api.receipt_status("POS Invoice", NAMES["POS Invoice"])
		self.assertEqual((data["status"], data["number"], data["test_mode"]), ("Reported", "FBR-0001", False))
		self.assertTrue(data["qr_svg"].startswith("<svg"))
		self.assertTrue(data["notice"])
		text = json.dumps({**data, **api.public_settings()})
		for secret in ("super-secret-token", "POS-77", "fbr.example.test"):
			self.assertNotIn(secret, text)
		set_settings(show_qr=0)
		self.assertEqual(api.receipt_status("POS Invoice", NAMES["POS Invoice"])["qr_svg"], "")
		self.assertIsNone(receipt.status_of("POS Invoice", "NO-SUCH-INVOICE"))

	def test_the_entry_points_need_an_accounts_role(self):
		email = "fbr.pos.nobody@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Nobody", "send_welcome_email": 0, "user_type": "System User", "roles": [{"role": "Desk User"}]}).insert(ignore_permissions=True)
		frappe.set_user(email)
		for call in (lambda: api.enqueue_report("POS Invoice", NAMES["POS Invoice"], "FBR POS"), lambda: api.receipt_status("POS Invoice", NAMES["POS Invoice"]), api.public_settings, api.retry_failed):
			with self.assertRaises(frappe.PermissionError):
				call()

	def test_only_submitted_sales_can_be_queued(self):
		frappe.db.set_value("POS Invoice", NAMES["POS Invoice"], "docstatus", 0)
		with self.assertRaises(frappe.ValidationError):
			api.enqueue_report("POS Invoice", NAMES["POS Invoice"], "FBR POS")
