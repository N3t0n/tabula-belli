const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { runInNewContext } = require('node:vm');
const { resolve } = require('node:path');
const script = readFileSync(resolve(__dirname, '../../src/static/js/passwords.js'), 'utf8');

function setup() {
    const listeners = {};
    const elements = [];
    const form = { addEventListener(name, fn) { (listeners[name] ||= []).push(fn); } };
    const inputs = [false, false, true].map((disabled, index) => ({
        id: `password${index}`, type: 'password', value: 'test-input', disabled, form,
        labels: [{ textContent: index ? 'Confirm password' : 'Password' }],
        before() {},
    }));
    runInNewContext(script, { document: {
        querySelectorAll() { return inputs; },
        createElement(tag) {
            const element = { tag, attributes: {}, children: [], listeners: {},
                append(child) { this.children.push(child); },
                setAttribute(name, value) { this.attributes[name] = value; },
                addEventListener(name, fn) { this.listeners[name] = fn; },
            };
            elements.push(element);
            return element;
        },
    } });
    return { inputs, buttons: elements.filter(e => e.tag === 'button'), listeners };
}

test('visibility controls preserve values, work independently and never submit the form', () => {
    const { inputs, buttons } = setup();
    buttons[0].listeners.click();
    assert.equal(inputs[0].type, 'text');
    assert.equal(inputs[0].value, 'test-input');
    assert.equal(inputs[1].type, 'password');
    assert.equal(buttons[0].type, 'button');
    assert.equal(buttons[0].attributes['aria-controls'], inputs[0].id);
    assert.match(buttons[0].attributes['aria-label'], /^Hide password/);
    buttons[0].listeners.click();
    assert.equal(inputs[0].type, 'password');
    assert.equal(inputs[0].value, 'test-input');
    assert.match(buttons[0].attributes['aria-label'], /^Show password/);
    assert.equal(buttons[2].disabled, true);
});

test('submission and reset hide revealed passwords again', () => {
    const { inputs, buttons, listeners } = setup();
    for (const event of ['submit', 'reset']) {
        buttons[0].listeners.click();
        buttons[1].listeners.click();
        listeners[event].forEach(fn => fn());
        assert.ok(inputs.every(input => input.type === 'password'));
        assert.ok(buttons.every(button => button.attributes['aria-label'].startsWith('Show password')));
    }
});
