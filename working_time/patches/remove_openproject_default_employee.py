import frappe


def execute():
    # Remove the obsolete Project custom field if it exists
    if frappe.db.exists('Custom Field', {'dt': 'Project', 'fieldname': 'openproject_default_employee'}):
        frappe.delete_doc('Custom Field', frappe.db.get_value('Custom Field', {'dt': 'Project', 'fieldname': 'openproject_default_employee'}))
        frappe.db.commit()
