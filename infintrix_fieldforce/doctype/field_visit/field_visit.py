# Copyright (c) 2026, muqeetmughal786@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FieldVisit(Document):
	def before_validate(self):
		if not self.visit_date:
			self.visit_date = frappe.utils.today()
		if not self.visited_by:
			self.visited_by = frappe.session.user
