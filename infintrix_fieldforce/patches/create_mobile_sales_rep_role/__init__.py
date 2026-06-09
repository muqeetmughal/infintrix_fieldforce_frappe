import frappe


def execute():
    if not frappe.db.exists("Role", "Mobile Sales Rep"):
        role = frappe.new_doc("Role")
        role.role_name = "Mobile Sales Rep"
        role.desk_access = 0
        role.insert()
