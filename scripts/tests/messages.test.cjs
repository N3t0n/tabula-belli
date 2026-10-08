const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { runInNewContext } = require('node:vm');

const script = readFileSync(resolve(__dirname, '../../src/static/js/messages.js'), 'utf8');

function setup(autoDismiss, { hovered = false, focused = false } = {}) {
    let now = 0;
    let nextId = 0;
    let factory;
    let initialize;
    const timers = new Map();
    const element = {
        matches: () => hovered,
        contains: () => focused,
    };
    runInNewContext(script, {
        document: {
            activeElement: {},
            addEventListener: (name, callback) => { initialize = callback; },
        },
        Alpine: { data: (name, callback) => { factory = callback; } },
        Date: { now: () => now },
        setTimeout: (callback, delay) => {
            const id = ++nextId;
            timers.set(id, { callback, due: now + delay });
            return id;
        },
        clearTimeout: id => timers.delete(id),
    });
    initialize();
    const notice = factory(autoDismiss);
    notice.$el = element;
    notice.init();
    return {
        notice, timers,
        advance(ms) {
            now += ms;
            for (const [id, timer] of [...timers]) {
                if (timer.due <= now) {
                    timers.delete(id);
                    timer.callback();
                }
            }
        },
    };
}

test('success closes after five seconds of unpaused time', () => {
    const ui = setup(true);
    ui.advance(4999);
    assert.equal(ui.notice.show, true);
    ui.advance(1);
    assert.equal(ui.notice.show, false);
    assert.equal(ui.timers.size, 0);
});

test('persistent notices never acquire a dismissal timer', () => {
    const ui = setup(false);
    ui.advance(60000);
    ui.notice.setHovered(true);
    ui.notice.setHovered(false);
    ui.notice.setFocused(true);
    ui.notice.setFocused(false);
    assert.equal(ui.notice.show, true);
    assert.equal(ui.timers.size, 0);
    ui.notice.dismiss();
    assert.equal(ui.notice.show, false);
});

test('overlapping pointer and keyboard interaction pauses until both leave', () => {
    const ui = setup(true);
    ui.advance(2000);
    ui.notice.setHovered(true);
    ui.notice.setFocused(true);
    ui.advance(10000);
    ui.notice.setHovered(false);
    assert.equal(ui.timers.size, 0);
    ui.notice.setFocused(false);
    ui.advance(2999);
    assert.equal(ui.notice.show, true);
    ui.advance(1);
    assert.equal(ui.notice.show, false);
});

test('initial interaction prevents scheduling until the notice is left', () => {
    for (const initial of [{ hovered: true }, { focused: true }]) {
        const ui = setup(true, initial);
        ui.advance(10000);
        assert.equal(ui.notice.show, true);
        assert.equal(ui.timers.size, 0);
        ui.notice.setHovered(false);
        ui.notice.setFocused(false);
        ui.advance(5000);
        assert.equal(ui.notice.show, false);
    }
});

test('manual dismissal cancels timers and cannot be restarted by leaving', () => {
    const ui = setup(true);
    ui.notice.dismiss();
    ui.notice.setHovered(false);
    ui.notice.setFocused(false);
    assert.equal(ui.timers.size, 0);
    assert.equal(ui.notice.show, false);
});

test('destroying one notice clears only its timer', () => {
    const ui = setup(true);
    ui.notice.destroy();
    assert.equal(ui.timers.size, 0);
    ui.advance(10000);
    assert.equal(ui.notice.show, true);
});
