# Copyright (c) 2026, muqeetmughal786@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FieldVisit(Document):
	def before_validate(self):
		if not self.user:
			self.user = frappe.session.user
		if not self.check_in_time:
			self.check_in_time = frappe.utils.now()

		self._sync_party_fields()

	def _sync_party_fields(self):
		if self.party_type == "Customer" and self.party:
			self.customer = self.party
			if not self.party_name:
				name = frappe.db.get_value("Customer", self.party, "customer_name")
				if name:
					self.party_name = name
		elif self.party_type == "Lead" and self.party:
			self.lead = self.party
			if not self.party_name:
				name = frappe.db.get_value("Lead", self.party, "lead_name")
				if name:
					self.party_name = name
		elif self.party_type == "Opportunity" and self.party:
			self.opportunity = self.party
			if not self.party_name:
				name = frappe.db.get_value("Opportunity", self.party, "opportunity_name")
				if name:
					self.party_name = name
		elif self.party_type == "Supplier" and self.party:
			self.supplier = self.party
			if not self.party_name:
				name = frappe.db.get_value("Supplier", self.party, "supplier_name")
				if name:
					self.party_name = name

	def before_insert(self):
		if self.field_visit_plan:
			plan = frappe.get_doc("Field Visit Plan", self.field_visit_plan)
			if plan.status == "Scheduled":
				plan.status = "In Progress"
				plan.actual_field_visit = self.name
				plan.save(ignore_permissions=True)

	def on_submit(self):
		if self.field_visit_plan:
			plan = frappe.get_doc("Field Visit Plan", self.field_visit_plan)
			plan.status = "Completed"
			plan.save(ignore_permissions=True)
