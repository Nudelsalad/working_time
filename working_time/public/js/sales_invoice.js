// Do NOT update values during refresh to avoid making the doc dirty repeatedly
frappe.ui.form.on('Sales Invoice', {
  refresh(frm) {
    // Intentionally empty. Fetching happens via fetch_from and row change handler.
  },
});

frappe.ui.form.on('Sales Invoice Timesheet', {
  time_sheet(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row.time_sheet) return;
    frappe.db.get_value('Timesheet', row.time_sheet, 'technician_on_site').then(r => {
      if (r && r.message) {
        const fetched = !!r.message.technician_on_site;
        if ((row.technician_on_site ? true : false) !== fetched) {
          frappe.model.set_value(cdt, cdn, 'technician_on_site', fetched);
        }
      }
    });
  },
});
