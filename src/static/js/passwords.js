(() => {
    const eye = '<svg aria-hidden="true" focusable="false" class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>';
    const eyeOff = '<svg aria-hidden="true" focusable="false" class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="m3 3 18 18M10 5.2A12 12 0 0 1 12 5c6.5 0 10 7 10 7a18 18 0 0 1-3 4M6 6C3.4 8.2 2 12 2 12s3.5 7 10 7c2 0 3.7-.6 5.2-1.5M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>';

    document.querySelectorAll('input.form-control[type="password"]').forEach(input => {
        const wrapper = document.createElement('div');
        wrapper.className = 'password-field';
        input.before(wrapper);
        wrapper.append(input);

        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-icon password-toggle';
        button.disabled = input.disabled;
        button.setAttribute('aria-controls', input.id);
        const fieldLabel = input.labels?.[0]?.textContent.trim() || 'password';

        const update = visible => {
            input.type = visible ? 'text' : 'password';
            button.setAttribute('aria-label', `${visible ? 'Hide' : 'Show'} password: ${fieldLabel}`);
            button.innerHTML = visible ? eyeOff : eye;
        };
        update(false);
        button.addEventListener('click', () => update(input.type === 'password'));
        input.form?.addEventListener('submit', () => update(false));
        input.form?.addEventListener('reset', () => update(false));
        wrapper.append(button);
    });
})();
