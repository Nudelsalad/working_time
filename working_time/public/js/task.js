frappe.ui.form.on('Task', {
  refresh(frm) {
    if (frm.doc.project) {
      frm.add_custom_button('Sync from OpenProject', () => {
        frappe.call({
          method: 'working_time.working_time.openproject_sync.sync_project_from_openproject',
          args: { project_name: frm.doc.project },
          freeze: true,
          callback: () => frm.reload_doc(),
        });
      }, __('OpenProject'));
    }
  },
});
