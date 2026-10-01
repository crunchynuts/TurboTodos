import { apiFetch, saveDownload } from './transport.js';
// Multi-selection and generic CSV/JSON imports. Business rules live in Python.
const $ = (selector, root = document) => root.querySelector(selector);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const splitTags = value => [...new Set(value.split(/[,|]/).map(t => t.trim()).filter(Boolean))];
let host;

export const bulk = {
  selecting: false,
  ids: new Set(),
  busy: false,

  configure(callbacks) { host = callbacks; },

  checkbox(task) {
    if (!this.selecting) return '';
    return `<input type="checkbox" class="task-selection" data-bulk-select="${task.id}" aria-label="Select ${escape(task.title)}" ${this.ids.has(task.id) ? 'checked' : ''}>`;
  },

  toolbar(tasks) {
    const existing = new Set(host.getState().tasks.map(t => t.id));
    this.ids = new Set([...this.ids].filter(id => existing.has(id)));
    if (!this.selecting) return '';
    const visible = new Set(tasks.map(t => t.id));
    const hidden = [...this.ids].filter(id => !visible.has(id)).length;
    return `<div class="bulk-toolbar" aria-label="Bulk task actions">
      <div><strong>${this.ids.size} selected</strong>${hidden ? `<small>including ${hidden} outside this filter</small>` : '<small>Select tasks using the square checkboxes.</small>'}</div>
      <button class="text-button" data-bulk="select-filtered">Select all ${visible.size} filtered</button>
      <button class="text-button" data-bulk="clear">Clear selection</button>
      <span class="bulk-toolbar-spacer"></span>
      <button class="button" data-bulk="add" ${this.ids.size ? '' : 'disabled'}>+ Add tags</button>
      <button class="button" data-bulk="remove" ${this.ids.size ? '' : 'disabled'}>− Remove tags</button>
      <button class="icon-button" data-bulk="toggle" aria-label="Exit task selection">✕</button>
    </div>`;
  },

  async action(action) {
    if (action === 'toggle') {
      this.selecting = !this.selecting;
      if (!this.selecting) this.ids.clear();
      host.render();
    }
    if (action === 'select-filtered') {
      host.getFiltered().forEach(t => this.ids.add(t.id));
      host.render();
    }
    if (action === 'clear') { this.ids.clear(); host.render(); }
    if (action === 'add' || action === 'remove') this.editTags(action);
    if (action === 'import') this.openImport();
  },

  editTags(mode) {
    if (!this.ids.size) return;
    const ids = [...this.ids];
    const tasks = host.getState().tasks.filter(t => this.ids.has(t.id));
    const suggestions = mode === 'remove' ? [...new Set(tasks.flatMap(t => t.tags))] : host.getState().tags;
    host.dialog(mode === 'add' ? 'Add tags to selected tasks' : 'Remove tags from selected tasks', `
      <p class="bulk-description">${ids.length} task${ids.length === 1 ? '' : 's'} selected. ${mode === 'remove' ? 'Only the named tags will be removed; other tags stay in place.' : 'Existing tags will stay in place.'}</p>
      <label class="modal-label">Tags (comma separated)<input id="bulk-tags" name="tags" required placeholder="Planning, Personal, Launch"></label>
      <div class="bulk-tag-options">${suggestions.map(t => `<button type="button" class="side-tag" data-pick-tag="${escape(t)}">${escape(t)}</button>`).join('')}</div>
      <div id="bulk-error" class="inline-error" role="alert"></div>`, async fields => {
      if (this.busy) return;
      const tags = splitTags(fields.get('tags'));
      if (!tags.length) { $('#bulk-error').textContent = 'Enter at least one tag.'; return; }
      const form = $('#modal-form');
      this.busy = true;
      form.querySelector('button[type=submit]').disabled = true;
      try {
        await host.ready();
        const response = await request('/api/tags', {version: host.getState().version, ids, tags, mode});
        host.accept(response, `${mode === 'add' ? 'Tags added to' : 'Tags removed from'} ${ids.length} tasks`);
        host.close(true);
      } catch (error) {
        if (document.contains(form)) $('#bulk-error').textContent = error.message;
      } finally {
        this.busy = false;
        if (document.contains(form)) form.querySelector('button[type=submit]').disabled = false;
      }
    }, mode === 'add' ? 'Add tags' : 'Remove tags');
    $('#modal-form').addEventListener('click', event => {
      const button = event.target.closest('[data-pick-tag]');
      if (!button) return;
      const input = $('#bulk-tags'), tags = splitTags(input.value), tag = button.dataset.pickTag;
      input.value = (tags.includes(tag) ? tags.filter(t => t !== tag) : [...tags, tag]).join(', ');
      button.classList.toggle('selected', !tags.includes(tag));
    });
  },

  openImport() {
    const state = host.getState();
    host.dialog('Bring your tasks along', `
      <p class="bulk-description">Import any task list from CSV or JSON. Only <code>title</code> is required. Review everything before it is saved.</p>
      <div class="import-source">
        <label class="modal-label">Task file<input type="file" id="import-file" accept=".csv,.json,text/csv,application/json"></label>
        <a class="text-button" href="/import-template.csv" download="turbotodos-template.csv">Download CSV template ↗</a>
      </div>
      <details class="paste-import"><summary>Or paste CSV / JSON</summary><textarea id="import-paste" rows="5" aria-label="Paste CSV or JSON tasks" placeholder='[{"title": "Plan the next release", "tags": ["Planning"]}]'></textarea></details>
      <div class="import-defaults">
        <label class="modal-label">Add these tags to every task<input id="import-tags" placeholder="Optional: Planning, Q4"></label>
        <label class="modal-label">Default project<select id="import-project"><option value="">No project</option>${state.projects.filter(p=>p.active!==false).sort((a,b)=>a.name.localeCompare(b.name)).map(p => `<option value="${p.id}">${escape(p.name)}</option>`).join('')}</select></label>
        <label class="modal-label">Default status<select id="import-status">${state.columns.map(c => `<option value="${c.id}">${escape(c.name)}</option>`).join('')}</select></label>
        <label class="modal-label">Duplicates<select id="import-duplicates"><option value="skip">Skip existing & repeated tasks</option><option value="allow">Import duplicates as new tasks</option></select></label>
      </div>
      <p class="field-help">Per-row project and status override defaults. Row tags and shared tags are combined. Duplicates match source_key when supplied, otherwise title + project. CSV tags may be comma- or pipe-separated; JSON tags may be a list.</p>
      <details class="import-schema"><summary>Available columns & formats</summary><p><code>title, tags, project, status, priority, start, due, notes, milestone, reminder, source_key</code></p><p>Dates: YYYY-MM-DD. Reminders: YYYY-MM-DDTHH:MM (local time). Priority: low / medium / high / urgent. Milestone: true / false. Project and status accept an existing name or ID. Notes are plain text. Optional <code>path</code> is added to notes; no linked files are read or uploaded.</p><p>Unknown columns are reported so data is never silently dropped. Up to 5,000 tasks / 8 MB per import. An error in any row prevents the whole import.</p></details>
      <div id="import-error" class="inline-error" role="alert"></div>
      <div id="import-preview" aria-live="polite"></div>
      <button type="button" class="button" id="preview-import">Preview import</button>`, () => commit(), 'Import tasks');
    const form = $('#modal-form'), modal = form.closest('.modal');
    modal.classList.add('import-modal');
    const submit = $('button[type=submit]', form);
    submit.disabled = true;
    let preview = null, sequence = 0;
    const invalidate = () => { sequence++; preview = null; submit.disabled = true; $('#import-preview').innerHTML = ''; $('#import-error').textContent = ''; };
    form.addEventListener('input', invalidate);
    form.addEventListener('change', invalidate);

    $('#preview-import').addEventListener('click', async () => {
      const currentSequence = ++sequence;
      preview = null;
      submit.disabled = true;
      $('#import-error').textContent = '';
      const button = $('#preview-import');
      button.disabled = true;
      button.textContent = 'Checking tasks…';
      try {
        await host.ready();
        const pasted = $('#import-paste').value.trim(), file = $('#import-file').files[0];
        if (!pasted && !file) throw Error('Choose a CSV/JSON file, or paste a task list.');
        if (file && !pasted && file.size > 8 * 1024 * 1024) throw Error('Choose a file smaller than 8 MB.');
        const content = pasted || await file.text();
        const filename = pasted ? (/^[\[{]/.test(pasted) ? 'pasted.json' : 'pasted.csv') : file.name;
        const payload = {filename, content, duplicates: $('#import-duplicates').value,
          defaults: {tags: splitTags($('#import-tags').value), project: $('#import-project').value, status: $('#import-status').value}};
        const result = await request('/api/import/preview', payload);
        if (currentSequence !== sequence || !document.contains(form)) return;
        preview = {payload, result};
        const projectName = id => state.projects.find(p => p.id === id)?.name || '—';
        const statusName = id => state.columns.find(c => c.id === id)?.name || '—';
        $('#import-preview').innerHTML = `<div class="import-summary"><strong>${result.count} to import</strong><span>${result.skipped} duplicates skipped</span><span class="${result.errors.length ? 'inline-error' : ''}">${result.errors.length} errors</span></div>
          ${result.errors.length ? `<div class="import-errors">${result.errors.slice(0,20).map(e => `<p>Row ${e.row}: ${escape(e.error)}</p>`).join('')}${result.errors.length > 20 ? '<p>More errors exist. Fix the input and preview again.</p>' : ''}</div>` : ''}
          <div class="import-table-wrap"><table class="import-table"><thead><tr><th>Row</th><th>Task</th><th>Tags</th><th>Project / status</th><th>Result</th></tr></thead><tbody>${result.preview.map(row => `<tr><td>${row.row}</td><td>${escape(row.title)}</td><td>${row.tags.map(tag => `<span class="tag">${escape(tag)}</span>`).join(' ')}</td><td>${escape(projectName(row.project))}<br><small>${escape(statusName(row.status))}</small></td><td>${escape(row.result)}</td></tr>`).join('')}</tbody></table></div>
          ${result.total > 100 ? `<p class="field-help">Showing the first 100 of ${result.total} rows. Every row has been validated.</p>` : ''}`;
        submit.textContent = `Import ${result.count} tasks`;
        submit.disabled = !result.canImport;
      } catch (error) {
        if (document.contains(form)) $('#import-error').textContent = error.message;
      } finally {
        if (document.contains(form)) { button.disabled = false; button.textContent = 'Preview import'; }
      }
    });

    const commit = async () => {
      if (!preview?.result.canImport || this.busy) return;
      this.busy = true;
      form.inert = true;
      try {
        await host.ready();
        const response = await request('/api/import', {...preview.payload, version: preview.result.version});
        host.accept(response, `${preview.result.count} tasks imported · ${preview.result.skipped} duplicates skipped`);
        host.close(true);
      } catch (error) {
        if (document.contains(form)) {
          $('#import-error').textContent = error.message + ' Preview again before retrying.';
          preview = null;
          submit.disabled = true;
        }
      } finally { this.busy = false; form.inert = false; }
    };
  },
};

async function request(url, body) {
  const response = await apiFetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body});
  const result = await response.json();
  if (!response.ok) throw Error(result.error || 'Unable to save. Please try again.');
  return result;
}

document.addEventListener('click', event => {
  const button = event.target.closest('[data-bulk]');
  if (!button) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  bulk.action(button.dataset.bulk);
}, true);

document.addEventListener('change', event => {
  const input = event.target.closest('[data-bulk-select]');
  if (!input) return;
  if (input.checked) bulk.ids.add(input.dataset.bulkSelect);
  else bulk.ids.delete(input.dataset.bulkSelect);
  host.render();
});

document.addEventListener('click',async event=>{
  const link=event.target.closest('a[download]');
  if(!window.TURBO_DESKTOP||!link)return;
  event.preventDefault();
  try{await saveDownload(new Blob([window.TURBO_IMPORT_TEMPLATE],{type:'text/csv'}),'turbotodos-template.csv');}
  catch(e){alert('Export failed: '+e.message);}
});
