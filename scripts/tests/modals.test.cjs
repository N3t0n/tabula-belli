const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element extends EventTarget {
    constructor() { super(); this.hidden = true; this.disabled = false; this.attrs = {}; this.isConnected = true; }
    focus() { this.focused = true; }
    setAttribute(name, value) { this.attrs[name] = value; }
    removeAttribute(name) { delete this.attrs[name]; }
    getAttribute(name) { return this.attrs[name]; }
    matches(selector) { return selector === this.selector; }
    querySelector(selector) { return this.nodes?.[selector]; }
    querySelectorAll() { return this.closers || []; }
    showModal() { this.open = true; }
    close() { this.open = false; this.dispatchEvent(new Event('close')); }
}
function setup() {
    const body = new Element(); body.style = { overflow: 'auto' };
    const window = new Element();
    const edit = new Element(); const confirmation = new Element();
    const cancel = new Element(); const confirm = new Element(); const message = new Element();
    const opener = new Element(); opener.selector = '[data-profile-edit]';
    const form = new Element(); form.selector = '#modal-content form';
    const submit = new Element(); const invalid = new Element();
    form.nodes = { '[type="submit"]': submit };
    edit.nodes = { form, '[aria-invalid="true"]': invalid };
    confirmation.nodes = { '[data-modal-confirm]': confirm, '[data-confirm-message]': message };
    confirmation.closers = [cancel];
    const nodes = { 'edit-dialog': edit, 'confirmation-dialog': confirmation,
        'profile-load-status': new Element(), 'profile-load-error': new Element(), 'profile-save-error': new Element() };
    const document = { body, activeElement: opener, getElementById: id => nodes[id] };
    vm.runInNewContext(fs.readFileSync('src/static/js/modals.js', 'utf8'), { document, window });
    const emit = (name, detail) => { const event = new Event(name, { cancelable: true }); event.detail = detail; body.dispatchEvent(event); return event; };
    return { nodes, body, edit, confirmation, cancel, confirm, message, opener, form, submit, invalid, window, emit };
}

test('confirmation cancellation never issues the request; confirmation issues it once', () => {
    const s = setup(); let requests = 0;
    const detail = { question: 'Cancel registration?', elt: s.opener, issueRequest: () => requests++ };
    assert.equal(s.emit('htmx:confirm', detail).defaultPrevented, true);
    assert.equal(s.message.textContent, detail.question);
    s.cancel.dispatchEvent(new Event('click'));
    assert.equal(requests, 0); assert.equal(s.body.style.overflow, 'auto');
    s.emit('htmx:confirm', detail);
    s.confirm.dispatchEvent(new Event('click')); s.confirm.dispatchEvent(new Event('click'));
    assert.equal(requests, 1); assert.equal(s.opener.focused, true);
});

test('failed profile loading restores the opener and never opens stale content', () => {
    const s = setup();
    s.emit('htmx:beforeRequest', { elt: s.opener });
    assert.equal(s.opener.disabled, true); assert.equal(s.nodes['profile-load-status'].hidden, false);
    s.emit('htmx:afterRequest', { elt: s.opener, failed: true });
    assert.equal(s.edit.open, undefined); assert.equal(s.opener.disabled, false);
    assert.equal(s.nodes['profile-load-error'].hidden, false);
});

test('loaded edit dialog locks scrolling; server failure retains form and unlocks submission', () => {
    const s = setup();
    s.emit('htmx:beforeRequest', { elt: s.opener });
    s.emit('htmx:afterSwap', { target: { id: 'modal-content' } });
    assert.equal(s.edit.open, true); assert.equal(s.body.style.overflow, 'hidden');
    s.emit('htmx:beforeRequest', { elt: s.form }); assert.equal(s.submit.disabled, true);
    s.emit('htmx:afterRequest', { elt: s.form, failed: true, xhr: { status: 503 } });
    assert.equal(s.submit.disabled, false); assert.equal(s.nodes['profile-save-error'].hidden, false);
    assert.equal(s.edit.nodes.form, s.form);
    s.window.dispatchEvent(new Event('modal-close'));
    assert.equal(s.edit.open, false); assert.equal(s.body.style.overflow, 'auto');
});

test('validation responses focus the invalid field without replacing the dialog', () => {
    const s = setup(); s.edit.open = true;
    s.emit('htmx:afterSwap', { target: {}, xhr: { status: 400 } });
    assert.equal(s.invalid.focused, true); assert.equal(s.edit.open, true);
});

test('every destructive HTMX form declares confirmation on the request element', () => {
    const root = 'src/apps/events/templates';
    let checked = 0;
    function inspect(directory) {
        for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
            const path = `${directory}/${entry.name}`;
            if (entry.isDirectory()) { inspect(path); continue; }
            if (!entry.name.endsWith('.html')) continue;
            const html = fs.readFileSync(path, 'utf8');
            for (const match of html.matchAll(/<form\b([^>]*)>[\s\S]*?<\/form>/g)) {
                const attributes = match[1];
                if (!/hx-post="[^"\n]*(?:my_events:cancel|event_cancel_registration|my_events:remove_participant)/.test(attributes)) continue;
                assert.match(attributes, /hx-confirm="[^"]+"/, `${path}: confirmation must be on the form sending the request`);
                checked++;
            }
        }
    }
    inspect(root);
    assert.equal(checked, 8);
});
