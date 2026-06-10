# Copyright (c) 2026, muqeetmughal786@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestFieldVisitPlan(FrappeTestCase):
	def setUp(self):
		frappe.db.savepoint("test_field_visit_plan")

	def tearDown(self):
		frappe.db.rollback(save_point="test_field_visit_plan")

	def test_create_field_visit_plan(self):
		plan = frappe.get_doc({
			"doctype": "Field Visit Plan",
			"customer": "_Test Customer",
			"plan_date": frappe.utils.today(),
			"field_type": "Sales",
			"priority": "High",
			"visit_purpose": "Test visit plan creation",
		})
		plan.insert()
		self.assertEqual(plan.status, "Scheduled")
		self.assertEqual(plan.assigned_by, frappe.session.user)

	def test_customer_name_fetch(self):
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": "Test Fetch Name",
			"customer_type": "Individual",
			"customer_group": "_Test Customer Group",
			"territory": "_Test Territory",
		}).insert(ignore_if_duplicate=True)

		plan = frappe.get_doc({
			"doctype": "Field Visit Plan",
			"customer": customer.name,
			"plan_date": frappe.utils.today(),
		})
		plan.insert()
		self.assertEqual(plan.customer_name, "Test Fetch Name")
