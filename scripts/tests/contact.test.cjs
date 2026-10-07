const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { runInNewContext } = require('node:vm');

const script = readFileSync(resolve(__dirname, '../../src/static/js/contact.js'), 'utf8');

// Small DOM doubles exercise the submission lifecycle without network access.
function setup(fetchResponse, { configured = true, present = true } = {}) {
    const button = { disabled: !configured, textContent: 'Send message' };
    const status = {
        textContent: '', className: 'empty:hidden',
        dataset: { sendingClass: 'sending', successClass: 'success', errorClass: 'error' },
    };
    const values = { email: 'visitor@example.com', subject: 'Test subject', message: 'Test message' };
    const attributes = {};
    const calls = [];
    const timers = new Map();
    let nextTimer = 0;
    let submit;
    const form = {
        action: configured ? 'https://formspree.io/f/test-form' : '',
        getAttribute: () => configured ? 'https://formspree.io/f/test-form' : null,
        querySelector: selector => selector === '[data-contact-submit]' ? button : status,
        addEventListener: (name, listener) => { submit = listener; },
        setAttribute: (name, value) => { attributes[name] = value; },
        removeAttribute: name => { delete attributes[name]; },
        reset: () => { Object.keys(values).forEach(key => { values[key] = ''; }); },
    };
    runInNewContext(script, {
        document: { querySelector: () => present ? form : null },
        FormData: class { constructor() { Object.assign(this, values); } },
        fetch: async (url, options) => {
            calls.push({ url, options });
            return fetchResponse();
        },
        setTimeout: (callback, delay) => {
            const id = ++nextTimer;
            timers.set(id, { callback, delay });
            return id;
        },
        clearTimeout: id => timers.delete(id),
    });
    return {
        button, status, values, calls, attributes, timers,
        hasHandler: () => Boolean(submit),
        submit: () => submit({ preventDefault() {} }),
    };
}

test('confirmed submission sends all fields as JSON-response POST and clears the form', async () => {
    const ui = setup(() => ({ ok: true }));
    await ui.submit();
    assert.equal(ui.calls[0].url, 'https://formspree.io/f/test-form');
    assert.equal(ui.calls[0].options.method, 'POST');
    assert.equal(ui.calls[0].options.headers.Accept, 'application/json');
    assert.equal(ui.calls[0].options.body.subject, 'Test subject');
    assert.equal(ui.calls[0].options.body.email, 'visitor@example.com');
    assert.equal(ui.calls[0].options.body.message, 'Test message');
    assert.ok(Object.values(ui.values).every(value => value === ''));
    assert.equal(ui.status.className, 'success');
    assert.match(ui.status.textContent, /has been sent/);
    assert.equal(ui.button.disabled, false);
    assert.equal(ui.button.textContent, 'Send message');
    assert.equal(ui.attributes['aria-busy'], undefined);
});

for (const statusCode of [422, 429, 500]) {
    test(`HTTP ${statusCode} preserves fields and re-enables submission`, async () => {
        const ui = setup(() => ({ ok: false, status: statusCode }));
        await ui.submit();
        assert.equal(ui.values.message, 'Test message');
        assert.equal(ui.values.subject, 'Test subject');
        assert.equal(ui.values.email, 'visitor@example.com');
        assert.equal(ui.status.className, 'error');
        assert.match(ui.status.textContent, /couldn’t confirm/);
        assert.equal(ui.button.disabled, false);
        assert.equal(ui.calls.length, 1);
    });
}

test('connection failure preserves the message, does not retry, and permits a later attempt', async () => {
    let attempt = 0;
    const ui = setup(() => {
        if (++attempt === 1) throw new TypeError('Network failure');
        return { ok: true };
    });
    await ui.submit();
    assert.equal(ui.values.message, 'Test message');
    assert.equal(ui.status.className, 'error');
    assert.equal(ui.calls.length, 1);
    assert.equal(ui.button.disabled, false);
    await ui.submit();
    assert.equal(ui.calls.length, 2);
    assert.equal(ui.status.className, 'success');
});

test('an in-flight submission blocks a second event and displays its busy state', async () => {
    let finish;
    const ui = setup(() => new Promise(resolve => { finish = resolve; }));
    const first = ui.submit();
    assert.equal(ui.button.disabled, true);
    assert.equal(ui.button.textContent, 'Sending…');
    assert.equal(ui.status.className, 'sending');
    assert.equal(ui.attributes['aria-busy'], 'true');
    await ui.submit();
    assert.equal(ui.calls.length, 1);
    finish({ ok: true });
    await first;
    assert.equal(ui.button.disabled, false);
});

test('missing configuration or form never installs an accidental submission handler', () => {
    assert.equal(setup(() => { throw new Error('Must not send'); }, { configured: false }).hasHandler(), false);
    assert.equal(setup(() => { throw new Error('Must not send'); }, { present: false }).hasHandler(), false);
});

test('success disappears after five seconds without changing fields or the button', async () => {
    const ui = setup(() => ({ ok: true }));
    await ui.submit();
    assert.equal(ui.timers.size, 1);
    const timer = [...ui.timers.values()][0];
    assert.equal(timer.delay, 5000);
    timer.callback();
    assert.equal(ui.status.textContent, '');
    assert.equal(ui.status.className, 'empty:hidden');
    assert.equal(ui.button.disabled, false);
    assert.ok(Object.values(ui.values).every(value => value === ''));
});

test('errors do not expire and a new attempt cancels the previous success timer', async () => {
    let attempt = 0;
    let finish;
    const ui = setup(() => {
        if (++attempt === 1) return { ok: true };
        return new Promise(resolve => { finish = resolve; });
    });
    await ui.submit();
    assert.equal(ui.timers.size, 1);
    ui.values.message = 'A second message';
    const second = ui.submit();
    assert.equal(ui.timers.size, 0);
    assert.equal(ui.status.className, 'sending');
    finish({ ok: false });
    await second;
    assert.equal(ui.status.className, 'error');
    assert.equal(ui.timers.size, 0);
    assert.equal(ui.values.message, 'A second message');
});
