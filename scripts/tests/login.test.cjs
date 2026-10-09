const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { runInNewContext } = require('node:vm');
const { resolve } = require('node:path');

const markup = readFileSync(resolve(__dirname, '../../src/templates/account/login.html'), 'utf8');
const form = markup.match(/<form\b[\s\S]*?>/)[0];
const button = markup.match(/<button\b[^>]*type="submit"[^>]*>/)[0];
const attribute = (source, name) => {
    const match = source.match(new RegExp(`${name}="([^"]*)"`));
    assert.ok(match, `Missing login attribute: ${name}`);
    return match[1];
};

test('login allows one submission, blocks repeated submits and unlocks on page restoration', () => {
    const state = runInNewContext(`(${attribute(form, 'x-data')})`);
    let prevented = 0;
    state.$event = { preventDefault() { prevented += 1; } };

    runInNewContext(attribute(form, '@submit'), state);
    assert.equal(prevented, 0);
    assert.equal(runInNewContext(attribute(button, ':disabled'), state), true);
    assert.equal(runInNewContext(attribute(form, ':aria-busy'), state), true);

    runInNewContext(attribute(form, '@submit'), state);
    assert.equal(prevented, 1);

    runInNewContext(attribute(form, '@pageshow.window'), state);
    assert.equal(runInNewContext(attribute(button, ':disabled'), state), false);
    assert.equal(runInNewContext(attribute(form, ':aria-busy'), state), false);
    runInNewContext(attribute(form, '@submit'), state);
    assert.equal(prevented, 1);
});
