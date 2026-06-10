# Copyright (c) 2026, muqeetmughal786@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FieldVisitPlan(Document):
	def before_validate(self):
		if not self.plan_date:
			self.plan_date = frappe.utils.today()
		if not self.assigned_by:
			self.assigned_by = frappe.session.user
		if not self.assigned_on:
			self.assigned_on = frappe.utils.now()

		self._sync_party_fields()

	def _sync_party_fields(self):
		if self.party_type == "Customer" and self.party:
			self.customer = self.party
			name = frappe.db.get_value("Customer", self.party, "customer_name")
			if name:
				self.party_name = name
		elif self.party_type == "Lead" and self.party:
			self.lead = self.party
			name = frappe.db.get_value("Lead", self.party, "lead_name")
			if name:
				self.party_name = name
		elif self.party_type == "Opportunity" and self.party:
			self.opportunity = self.party
			name = frappe.db.get_value("Opportunity", self.party, "opportunity_name")
			if name:
				self.party_name = name
		elif self.party_type == "Supplier" and self.party:
			self.supplier = self.party
			name = frappe.db.get_value("Supplier", self.party, "supplier_name")
			if name:
				self.party_name = name
