frappe.ui.form.on('Task', {
  refresh(frm) {
    frm.add_custom_button(__('Sync from OpenProject'), async () => {
      let project = frm.doc.project;
      if (!project) {
        const d = new frappe.ui.Dialog({
          title: __('Sync from OpenProject'),
          fields: [
            { fieldtype: 'Link', fieldname: 'project', label: __('Project'), options: 'Project', reqd: 1 },
          ],
        });
        d.set_primary_action(__('Sync'), (values) => {
          d.hide();
          if (values && values.project) {
            frappe.call({
              method: 'working_time.openproject_sync.sync_project_from_openproject',
              args: { project_name: values.project },
              freeze: true,
              callback: () => frm.reload_doc(),
            });
          }
        });
        d.show();
      } else {
        frappe.call({
          method: 'working_time.openproject_sync.sync_project_from_openproject',
          args: { project_name: project },
          freeze: true,
          callback: () => frm.reload_doc(),
        });
      }
    }, __('OpenProject'));
  },
});
