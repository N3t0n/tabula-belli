// Keep transport failures outside the replaced block; never retry a cancellation automatically.
document.addEventListener('DOMContentLoaded', () => {
    const error = document.getElementById('my-events-request-error');
    if (!error) return;
    const isCancellation = event => event.detail.target?.id === 'my-events-content';
    document.body.addEventListener('htmx:beforeRequest', event => {
        if (isCancellation(event)) error.hidden = true;
    });
    document.body.addEventListener('htmx:afterRequest', event => {
        if (isCancellation(event) && event.detail.failed) error.hidden = false;
    });
    for (const name of ['htmx:sendError', 'htmx:timeout']) {
        document.body.addEventListener(name, event => {
            if (isCancellation(event)) error.hidden = false;
        });
    }
    document.body.addEventListener('htmx:afterSettle', event => {
        if (isCancellation(event)) document.getElementById('my-events-content')?.focus();
    });
});
