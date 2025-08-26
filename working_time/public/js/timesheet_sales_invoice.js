frappe.ui.form.on('Timesheet Sales Invoice', {
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
