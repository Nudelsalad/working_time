frappe.listview_settings['Task'] = {
  onload(listview) {
    listview.page.add_inner_button(__('Sync from OpenProject'), async () => {
      const selected = listview.get_checked_items();
      let project = null;
      if (selected && selected.length) {
        try {
          const r = await frappe.db.get_value('Task', selected[0].name, 'project');
          project = r && r.message && r.message.project;
        } catch (e) {
          // ignore
        }
      }
      const do_sync = (proj) => {
        if (!proj) return;
        frappe.call({
          method: 'working_time.openproject_sync.sync_project_from_openproject',
          args: { project_name: proj },
          freeze: true,
        }).then(() => listview.refresh());
      };
      if (!project) {
        const d = new frappe.ui.Dialog({
          title: __('Sync from OpenProject'),
          fields: [
            { fieldtype: 'Link', fieldname: 'project', label: __('Project'), options: 'Project', reqd: 1 },
          ],
        });
        d.set_primary_action(__('Sync'), (values) => {
          d.hide();
          do_sync(values && values.project);
        });
        d.show();
      } else {
        do_sync(project);
      }
    });
  },
};
