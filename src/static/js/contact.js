(() => {
    'use strict';

    const form = document.querySelector('[data-contact-form]');
    if (!form || !form.getAttribute('action')) return;

    const button = form.querySelector('[data-contact-submit]');
    const status = form.querySelector('[data-contact-status]');
    if (!button || !status || button.disabled) return;

    const buttonLabel = button.textContent;
    let sending = false;
    let successTimeout;

    function showStatus(state, message) {
        clearTimeout(successTimeout);
        status.className = status.dataset[`${state}Class`];
        status.textContent = message;
        if (state === 'success') {
            successTimeout = setTimeout(() => {
                status.textContent = '';
                status.className = 'empty:hidden';
            }, 5000);
        }
    }

    form.addEventListener('submit', async event => {
        event.preventDefault();
        // Also guard submissions triggered by Enter or another script.
        if (sending) return;

        sending = true;
        button.disabled = true;
        button.textContent = 'Sending…';
        form.setAttribute('aria-busy', 'true');
        showStatus('sending', 'Sending message…');

        try {
            const response = await fetch(form.action, {
                method: 'POST',
                body: new FormData(form),
                headers: { Accept: 'application/json' },
            });
            if (!response.ok) throw new Error('Submission not confirmed');

            form.reset();
            showStatus('success', 'Your message has been sent. Thank you!');
        } catch {
            // Keep the user's message; never retry automatically after a
            // connection failure, since the submission may have arrived.
            showStatus('error', 'We couldn’t confirm your submission. Please try again.');
        } finally {
            sending = false;
            button.disabled = false;
            button.textContent = buttonLabel;
            form.removeAttribute('aria-busy');
        }
    });
})();
