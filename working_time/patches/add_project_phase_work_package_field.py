import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    fields = {
        "Project": [
            {
                "fieldname": "openproject_phase_work_package_id",
                "label": "OpenProject Phase Work Package ID",
                "fieldtype": "Data",
                "insert_after": "openproject_last_synced_at",
                "translatable": 0,
                "description": "Optional Work Package ID of type Phase; restrict sync to its descendants.",
            }
        ]
    }
    create_custom_fields(fields)
