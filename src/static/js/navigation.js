(() => {
    const toggle = document.querySelector('[data-collapse-toggle="mobile-menu-2"]');
    const menu = document.getElementById('mobile-menu-2');
    if (!toggle || !menu) return;

    toggle.closest('nav').addEventListener('keydown', event => {
        if (event.key !== 'Escape' || toggle.getAttribute('aria-expanded') !== 'true') return;
        if (event.target !== toggle && !menu.contains(event.target)) return;
        if (!toggle.getClientRects().length) return;

        event.preventDefault();
        toggle.click();
        toggle.focus();
    });
})();
