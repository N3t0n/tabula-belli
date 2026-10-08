// Feedback belongs outside the swapped listing so errors never remove filters or results.
document.addEventListener('DOMContentLoaded', () => {
    const requests = new WeakMap();

    function context(event) {
        const detail = event.detail;
        const listing = detail.target;
        if (!listing?.matches('[data-event-listing]') || detail.requestConfig?.verb !== 'get') return;
        const wrapper = listing.closest('[data-listing-feedback]');
        return wrapper && { detail, listing, wrapper };
    }

    function setBusy({ listing, wrapper }, busy) {
        listing.setAttribute('aria-busy', String(busy));
        wrapper.querySelector('[data-listing-loading]').hidden = !busy;
        wrapper.querySelector('[data-listing-retry]').disabled = busy;
    }

    document.body.addEventListener('htmx:beforeRequest', event => {
        const ui = context(event);
        if (!ui) return;
        requests.set(ui.wrapper, {
            xhr: ui.detail.xhr,
            source: ui.detail.elt,
            path: ui.detail.requestConfig.path,
            parameters: { ...ui.detail.requestConfig.parameters },
            listing: ui.listing,
        });
        ui.wrapper.querySelector('[data-listing-error]').hidden = true;
        setBusy(ui, true);
    });

    document.body.addEventListener('htmx:beforeSwap', event => {
        const ui = context(event);
        if (!ui) return;
        // Form validation elsewhere may swap 400 responses; read-only listings must not.
        if (ui.detail.xhr.status >= 400 || requests.get(ui.wrapper)?.xhr !== ui.detail.xhr) {
            ui.detail.shouldSwap = false;
            ui.detail.isError = true;
        }
    });

    document.body.addEventListener('htmx:afterRequest', event => {
        const ui = context(event);
        if (!ui || requests.get(ui.wrapper)?.xhr !== ui.detail.xhr) return;
        setBusy(ui, false);
        ui.wrapper.querySelector('[data-listing-error]').hidden = !ui.detail.failed;
    });

    for (const name of ['htmx:sendError', 'htmx:timeout', 'htmx:onLoadError']) {
        document.body.addEventListener(name, event => {
            const ui = context(event);
            if (!ui || requests.get(ui.wrapper)?.xhr !== ui.detail.xhr) return;
            setBusy(ui, false);
            ui.wrapper.querySelector('[data-listing-error]').hidden = false;
        });
    }

    document.body.addEventListener('click', event => {
        const button = event.target.closest('[data-listing-retry]');
        if (!button || button.disabled) return;
        const request = requests.get(button.closest('[data-listing-feedback]'));
        if (!request) return;
        // Retry only the failed GET; never replay registrations, cancellations or saves.
        htmx.ajax('GET', request.path, {
            source: request.source,
            target: request.listing,
            swap: 'innerHTML',
            values: request.parameters,
        }).catch(() => {}); // HTMX lifecycle events display transport failures.
    });
});
