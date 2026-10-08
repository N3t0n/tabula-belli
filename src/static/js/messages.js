(() => {
    'use strict';

    document.addEventListener('alpine:init', () => {
        Alpine.data('messageNotice', (autoDismiss = false) => {
            let timer;
            let remaining = 5000;
            let startedAt;

            return {
                show: true,
                hovered: false,
                focused: false,

                init() {
                    this.hovered = this.$el.matches(':hover');
                    this.focused = this.$el.contains(document.activeElement);
                    this.resume();
                },
                pause() {
                    if (timer === undefined) return;
                    clearTimeout(timer);
                    timer = undefined;
                    remaining = Math.max(0, remaining - (Date.now() - startedAt));
                },
                resume() {
                    if (!autoDismiss || !this.show || this.hovered || this.focused || timer !== undefined) return;
                    startedAt = Date.now();
                    timer = setTimeout(() => {
                        timer = undefined;
                        this.show = false;
                    }, remaining);
                },
                setHovered(value) {
                    this.hovered = value;
                    if (value) this.pause();
                    else this.resume();
                },
                setFocused(value) {
                    this.focused = value;
                    if (value) this.pause();
                    else this.resume();
                },
                dismiss() {
                    this.pause();
                    this.show = false;
                },
                destroy() {
                    this.pause();
                },
            };
        });
    });
})();
