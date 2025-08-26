# Remove obsolete Project custom field 'default_key'
import frappe

def execute():
    cf = frappe.get_all('Custom Field', filters={'dt': 'Project', 'fieldname': 'default_key'})
    for f in cf:
        try:
            frappe.delete_doc('Custom Field', f.name)
        except Exception:
            # if already removed
            pass
