// Copyright (c) 2026, muqeetmughal786@gmail.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Field Visit Plan", {
	refresh(frm) {
		if (frm.doc.status === "In Progress" && frm.doc.actual_field_visit) {
			frm.add_custom_button(__("View Field Visit"), function () {
				frappe.set_route("Form", "Field Visit", frm.doc.actual_field_visit);
			});
		}
	},
	party_type(frm) {
		frm.set_value("party", "");
		frm.set_value("party_name", "");
		frm.set_value("customer", "");
		frm.set_value("lead", "");
		frm.set_value("opportunity", "");
		frm.set_value("supplier", "");
	},
});
