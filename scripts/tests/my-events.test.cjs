const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { runInNewContext } = require('node:vm');
const script = readFileSync(resolve(__dirname, '../../src/static/js/my-events.js'), 'utf8');

function setup() {
    const handlers = new Map();
    const error = { hidden: true };
    let focused = false;
    let initialize;
    runInNewContext(script, {
        document: {
            addEventListener: (_, handler) => { initialize = handler; },
            getElementById: id => id === 'my-events-request-error' ? error : { focus: () => { focused = true; } },
            body: { addEventListener: (name, handler) => handlers.set(name, handler) },
        },
    });
    initialize();
    return {
        error, focused: () => focused,
        emit: (name, overrides = {}) => handlers.get(name)({ detail: {
            target: { id: 'my-events-content' }, ...overrides,
        } }),
    };
}

test('failed cancellation exposes feedback without automatically repeating the POST', () => {
    for (const event of ['htmx:sendError', 'htmx:timeout', 'htmx:afterRequest']) {
        const ui = setup();
        ui.emit(event, { failed: true });
        assert.equal(ui.error.hidden, false);
        ui.emit('htmx:beforeRequest');
        assert.equal(ui.error.hidden, true);
    }
});

test('successful replacement restores keyboard focus without showing a transport error', () => {
    const ui = setup();
    ui.emit('htmx:afterRequest', { failed: false });
    ui.emit('htmx:afterSettle');
    assert.equal(ui.error.hidden, true);
    assert.equal(ui.focused(), true);
});

test('other application requests do not alter My Events feedback or focus', () => {
    const ui = setup();
    ui.emit('htmx:afterRequest', { failed: true, target: { id: 'registration-button' } });
    ui.emit('htmx:afterSettle', { target: { id: 'registration-button' } });
    assert.equal(ui.error.hidden, true);
    assert.equal(ui.focused(), false);
});
