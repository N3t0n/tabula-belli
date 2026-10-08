const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { runInNewContext } = require('node:vm');

const script = readFileSync(resolve(__dirname, '../../src/static/js/listings.js'), 'utf8');

function setup() {
    const handlers = new Map();
    const retries = [];
    let initialize;
    const loading = { hidden: true };
    const error = { hidden: true };
    const retry = { disabled: false, closest: () => wrapper };
    const wrapper = {
        querySelector: selector => ({
            '[data-listing-loading]': loading,
            '[data-listing-error]': error,
            '[data-listing-retry]': retry,
        }[selector]),
    };
    const listing = {
        matches: selector => selector === '[data-event-listing]',
        closest: () => wrapper,
        setAttribute: (name, value) => { listing[name] = value; },
        innerHTML: 'Previous results and filters',
    };
    const source = {};
    runInNewContext(script, {
        document: {
            addEventListener: (name, handler) => { initialize = handler; },
            body: { addEventListener: (name, handler) => { handlers.set(name, handler); } },
        },
        htmx: { ajax: (...args) => { retries.push(args); return Promise.resolve(); } },
    });
    initialize();
    return {
        loading, error, retry, listing, source, retries,
        request(overrides = {}) {
            return {
                xhr: { status: 200 }, target: listing, elt: source,
                requestConfig: { verb: 'get', path: '/events/', parameters: { status: 'completed', page: '2' } },
                ...overrides,
            };
        },
        emit(name, detail) { handlers.get(name)({ detail }); },
        clickRetry() { handlers.get('click')({ target: { closest: () => retry } }); },
    };
}

test('loading keeps results readable and success restores the retry control', () => {
    const ui = setup();
    const request = ui.request();
    ui.emit('htmx:beforeRequest', request);
    assert.equal(ui.loading.hidden, false);
    assert.equal(ui.listing['aria-busy'], 'true');
    assert.equal(ui.retry.disabled, true);
    assert.equal(ui.listing.innerHTML, 'Previous results and filters');
    ui.emit('htmx:afterRequest', { ...request, failed: false });
    assert.equal(ui.loading.hidden, true);
    assert.equal(ui.error.hidden, true);
    assert.equal(ui.retry.disabled, false);
    assert.equal(ui.listing['aria-busy'], 'false');
});

test('400 and 500 responses cannot replace a listing, even with global form validation enabled', () => {
    for (const status of [400, 500]) {
        const ui = setup();
        const request = ui.request({ xhr: { status } });
        ui.emit('htmx:beforeRequest', request);
        const swap = { ...request, shouldSwap: true, isError: false };
        ui.emit('htmx:beforeSwap', swap);
        assert.equal(swap.shouldSwap, false);
        assert.equal(swap.isError, true);
        ui.emit('htmx:afterRequest', { ...request, failed: swap.isError });
        assert.equal(ui.error.hidden, false);
        assert.equal(ui.listing.innerHTML, 'Previous results and filters');
        assert.equal(ui.retry.disabled, false);
    }
});

test('transport failures and timeouts expose a recoverable error without automatic requests', () => {
    for (const name of ['htmx:sendError', 'htmx:timeout', 'htmx:onLoadError']) {
        const ui = setup();
        const request = ui.request({ xhr: { status: 0 } });
        ui.emit('htmx:beforeRequest', request);
        ui.emit('htmx:afterRequest', request);
        ui.emit(name, request);
        assert.equal(ui.loading.hidden, true);
        assert.equal(ui.error.hidden, false);
        assert.equal(ui.listing['aria-busy'], 'false');
        assert.equal(ui.retries.length, 0);
    }
});

test('manual retry preserves the failed page and filters and cannot run while busy', () => {
    const ui = setup();
    const request = ui.request();
    ui.emit('htmx:beforeRequest', request);
    ui.clickRetry();
    assert.equal(ui.retries.length, 0);
    ui.emit('htmx:afterRequest', { ...request, failed: true });
    ui.clickRetry();
    const [verb, path, options] = ui.retries[0];
    assert.equal(verb, 'GET');
    assert.equal(path, '/events/');
    assert.equal(options.source, ui.source);
    assert.equal(options.target, ui.listing);
    assert.equal(options.values.status, 'completed');
    assert.equal(options.values.page, '2');
    assert.equal(options.swap, undefined); // Inherit the source's swap and settle policy.
});

test('superseded requests cannot overwrite or clear a newer loading state', () => {
    const ui = setup();
    const old = ui.request();
    const current = ui.request();
    ui.emit('htmx:beforeRequest', old);
    ui.emit('htmx:beforeRequest', current);
    const swap = { ...old, shouldSwap: true };
    ui.emit('htmx:beforeSwap', swap);
    ui.emit('htmx:afterRequest', { ...old, failed: true });
    ui.emit('htmx:sendError', old);
    assert.equal(swap.shouldSwap, false);
    assert.equal(ui.loading.hidden, false);
    assert.equal(ui.error.hidden, true);
    ui.emit('htmx:afterRequest', { ...current, failed: false });
    assert.equal(ui.loading.hidden, true);
});

test('intentional aborts do not show a connection error', () => {
    const ui = setup();
    const request = ui.request({ xhr: { status: 0 } });
    ui.emit('htmx:beforeRequest', request);
    ui.emit('htmx:afterRequest', request);
    assert.equal(ui.error.hidden, true);
    assert.equal(ui.retry.disabled, false);
});

test('new requests clear the previous error and successful responses remain swappable', () => {
    const ui = setup();
    const failed = ui.request();
    ui.emit('htmx:beforeRequest', failed);
    ui.emit('htmx:afterRequest', { ...failed, failed: true });
    const next = ui.request();
    ui.emit('htmx:beforeRequest', next);
    assert.equal(ui.error.hidden, true);
    const swap = { ...next, shouldSwap: true, isError: false };
    ui.emit('htmx:beforeSwap', swap);
    assert.equal(swap.shouldSwap, true);
    assert.equal(swap.isError, false);
});

test('POST mutations and other HTMX targets retain their existing behavior', () => {
    const ui = setup();
    for (const request of [
        ui.request({ requestConfig: { verb: 'post' } }),
        ui.request({ target: { matches: () => false } }),
    ]) {
        const swap = { ...request, shouldSwap: true, xhr: { status: 400 } };
        ui.emit('htmx:beforeRequest', request);
        ui.emit('htmx:beforeSwap', swap);
        ui.emit('htmx:afterRequest', { ...request, failed: true });
        assert.equal(swap.shouldSwap, true);
        assert.equal(ui.loading.hidden, true);
        assert.equal(ui.error.hidden, true);
    }
});
