(() => {
    const edit = document.getElementById('edit-dialog');
    const confirmation = document.getElementById('confirmation-dialog');
    let previousOverflow;
    let opener;
    let confirmAction;

    function open(dialog, trigger) {
        if (dialog.open) return;
        opener = trigger || document.activeElement;
        previousOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        dialog.showModal();
    }

    function close(dialog) {
        if (dialog.open) dialog.close();
    }

    for (const dialog of [edit, confirmation].filter(Boolean)) {
        dialog.addEventListener('close', () => {
            document.body.style.overflow = previousOverflow;
            if (opener?.isConnected) opener.focus();
            confirmAction = null;
        });
        dialog.querySelectorAll('[data-modal-close]').forEach(button => {
            button.addEventListener('click', () => close(dialog));
        });
    }

    if (confirmation) {
        confirmation.addEventListener('click', event => {
            const bounds = confirmation.getBoundingClientRect();
            if (event.target === confirmation && (
                event.clientX < bounds.left || event.clientX > bounds.right ||
                event.clientY < bounds.top || event.clientY > bounds.bottom
            )) close(confirmation);
        });
        document.body.addEventListener('htmx:confirm', event => {
            if (!event.detail.question) return;
            event.preventDefault();
            if (confirmation.open || edit?.open) return;
            confirmation.querySelector('[data-confirm-message]').textContent = event.detail.question;
            confirmAction = () => event.detail.issueRequest(true);
            open(confirmation, event.detail.elt);
        });
        confirmation.querySelector('[data-modal-confirm]').addEventListener('click', () => {
            const action = confirmAction;
            confirmAction = null;
            close(confirmation);
            action?.();
        });
    }

    if (!edit) return;
    const loading = document.getElementById('profile-load-status');
    const error = document.getElementById('profile-load-error');
    const saveError = document.getElementById('profile-save-error');
    let editTrigger;

    function isOpening(event) {
        return event.detail.elt?.matches('[data-profile-edit]');
    }

    function isSaving(event) {
        return event.detail.elt?.matches('#modal-content form');
    }

    document.body.addEventListener('htmx:beforeRequest', event => {
        if (isOpening(event)) {
            editTrigger = event.detail.elt;
            editTrigger.disabled = true;
            editTrigger.setAttribute('aria-busy', 'true');
            loading.hidden = false;
            error.hidden = true;
            saveError.hidden = true;
        }
        if (isSaving(event)) {
            saveError.hidden = true;
            event.detail.elt.querySelector('[type="submit"]').disabled = true;
            event.detail.elt.setAttribute('aria-busy', 'true');
        }
    });
    document.body.addEventListener('htmx:afterSwap', event => {
        if (event.detail.target?.id === 'modal-content') {
            open(edit, editTrigger);
        } else if (edit.open && event.detail.xhr.status === 400) {
            edit.querySelector('[aria-invalid="true"]')?.focus();
        }
    });
    document.body.addEventListener('htmx:afterRequest', event => {
        if (isOpening(event)) {
            editTrigger.disabled = false;
            editTrigger.removeAttribute('aria-busy');
            loading.hidden = true;
            if (event.detail.failed) error.hidden = false;
        }
        if (isSaving(event)) {
            const form = edit.querySelector('form');
            form?.removeAttribute('aria-busy');
            const submit = form?.querySelector('[type="submit"]');
            if (submit && submit.getAttribute('aria-disabled') !== 'true') submit.disabled = false;
            if (event.detail.failed && event.detail.xhr.status !== 400) saveError.hidden = false;
        }
    });
    edit.addEventListener('click', event => {
        if (event.target.closest('[data-edit-cancel]')) close(edit);
    });
    window.addEventListener('modal-close', () => close(edit));
})();
