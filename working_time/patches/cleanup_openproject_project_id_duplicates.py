import frappe


def execute():
    # Find all custom fields on Project that look like OpenProject Project ID
    cfs = frappe.get_all(
        "Custom Field",
        filters={"dt": "Project"},
        fields=["name", "fieldname", "label"],
    )

    # Keep exactly one with fieldname == 'openproject_project_id'
    target_fieldname = "openproject_project_id"
    to_delete = []
    has_primary = False

    for cf in cfs:
        if (cf.label or "").strip() == "OpenProject Project ID" or (cf.fieldname or "").startswith(
            target_fieldname
        ):
            if cf.fieldname == target_fieldname and not has_primary:
                has_primary = True
            else:
                to_delete.append(cf.name)

    # If none with exact fieldname exists but variants do, keep the first variant and rename to the canonical fieldname
    if not has_primary:
        variants = [
            cf for cf in cfs if (cf.label or "").strip() == "OpenProject Project ID" or (cf.fieldname or "").startswith(target_fieldname)
        ]
        if variants:
            # Keep first, rename its fieldname if needed
            keep = variants[0]
            if keep.fieldname != target_fieldname:
                frappe.db.set_value("Custom Field", keep.name, "fieldname", target_fieldname)
            # Delete the rest besides the one we keep
            for cf in variants[1:]:
                if cf.name not in to_delete:
                    to_delete.append(cf.name)

    for name in to_delete:
        try:
            frappe.delete_doc("Custom Field", name)
        except Exception:
            pass
