frappe.ui.form.on('Sales Invoice', {
  refresh(frm) {
    (frm.doc.timesheets || []).forEach(row => {
      if (row.time_sheet) {
        frappe.db.get_value('Timesheet', row.time_sheet, 'technician_on_site').then(r => {
          if (r && r.message) {
            frappe.model.set_value(row.doctype, row.name, 'technician_on_site', !!r.message.technician_on_site);
          }
        });
      }
    });
  },
});

frappe.ui.form.on('Sales Invoice Timesheet', {
  time_sheet(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row.time_sheet) return;
    frappe.db.get_value('Timesheet', row.time_sheet, 'technician_on_site').then(r => {
      if (r && r.message) {
        frappe.model.set_value(cdt, cdn, 'technician_on_site', !!r.message.technician_on_site);
      }
    });
  },
});
