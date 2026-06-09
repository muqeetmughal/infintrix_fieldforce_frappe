import frappe


def execute():
    defaults = ["Sales", "Recovery", "Complaint", "Follow-up"]
    for name in defaults:
        if not frappe.db.exists("Visit Type", name):
            doc = frappe.new_doc("Visit Type")
            doc.visit_type_name = name
            doc.insert()
