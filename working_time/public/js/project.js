frappe.ui.form.on('Project', {
  refresh(frm) {
    if (!frm.is_new() && frm.doc.openproject_site && frm.doc.openproject_project_id) {
      frm.add_custom_button(__('Sync now'), async () => {
        await frappe.call({
          method: 'working_time.openproject_sync.sync_project_from_openproject',
          args: { project_name: frm.doc.name },
          freeze: true,
          freeze_message: __('Syncing from OpenProject...'),
        });
        frm.reload_doc();
      }, __('OpenProject'));


      frm.add_custom_button(__('Validate mapping'), async () => {
        const r = await frappe.call({
          method: 'working_time.openproject_sync.validate_openproject_mapping',
          args: { project_name: frm.doc.name },
          freeze: true,
        });
        const m = r && r.message;
        frappe.msgprint(__('Project OK: #{0} {1} ({2})', [m.id, m.name, m.identifier]));
      }, __('OpenProject'));
    }

    // Helper: Find and set OpenProject Project without needing numeric ID
    if (!frm.is_new() && frm.doc.openproject_site) {
      frm.add_custom_button(__('Find OpenProject Project'), () => {
        const d = new frappe.ui.Dialog({
          title: __('Find OpenProject Project'),
          fields: [
            { fieldtype: 'Data', fieldname: 'q', label: __('URL / Identifier / Name'), reqd: 1, description: __('Paste the OpenProject project URL or type its name/identifier') },
            { fieldtype: 'Section Break' },
            { fieldtype: 'Select', fieldname: 'result', label: __('Results'), options: [], reqd: 0 },
          ],
          primary_action_label: __('Search'),
          primary_action: (values) => {
            frappe.call({
              method: 'working_time.openproject_sync.search_openproject_projects',
              args: { site: frm.doc.openproject_site, q: values.q, limit: 50 },
              freeze: true,
            }).then(r => {
              const results = (r && r.message && r.message.results) || [];
              d._op_results = results;
              const opts = results.map((x, i) => `${x.label}`);
              const fld = d.get_field('result');
              fld.df.options = opts.length ? opts : [__('No matches')];
              fld.refresh();
            });
          },
          secondary_action_label: __('Set Project'),
          secondary_action: () => {
            const fld = d.get_field('result');
            const idx = (fld.get_value && fld.get_value()) ? fld.df.options.indexOf(fld.get_value()) : -1;
            const sel = idx >= 0 && d._op_results ? d._op_results[idx] : null;
            if (sel && sel.id) {
              frm.set_value('openproject_project_id', sel.id);
              d.hide();
            } else {
              frappe.msgprint(__('Please search and select a result first.'));
            }
          }
        });
        d.show();
      }, __('OpenProject'));
    }
  },
});
