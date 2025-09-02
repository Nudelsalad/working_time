import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    fields = {
        "Task": [
            {
                "fieldname": "openproject_last_synced_at",
                "label": "OpenProject Last Synced At",
                "fieldtype": "Datetime",
                "insert_after": "openproject_work_package_url_task",
                "read_only": 1,
                "translatable": 0,
            }
        ]
    }
    create_custom_fields(fields)
