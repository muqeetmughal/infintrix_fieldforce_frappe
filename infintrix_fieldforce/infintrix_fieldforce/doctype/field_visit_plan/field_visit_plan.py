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
		if not self.party or not self.party_type:
			return

		name_fields = {
			"Customer": "customer_name",
			"Lead": "lead_name",
			"Opportunity": "opportunity_name",
			"Supplier": "supplier_name",
		}

		name_field = name_fields.get(self.party_type)
		if name_field:
			name = frappe.db.get_value(self.party_type, self.party, name_field)
			if name:
				self.party_name = name
