frappe.ui.form.on('Project', {
  refresh(frm) {
    if (!frm.is_new() && frm.doc.openproject_site && frm.doc.openproject_project_id) {
      frm.add_custom_button('Sync from OpenProject', async () => {
        await frappe.call({
          method: 'working_time.openproject_sync.sync_project_from_openproject',
          args: {
            project_name: frm.doc.name,
          },
          freeze: true,
          freeze_message: __('Syncing from OpenProject...'),
        });
        frm.reload_doc();
      }).addClass('btn-primary');
    }
  },
});
