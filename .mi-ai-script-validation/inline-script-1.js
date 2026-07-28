
(function () {
    "use strict";

    /*
       The project creates many MutationObservers. Repeated DOM changes can
       schedule the same callback hundreds of times. This wrapper combines
       callbacks per animation frame without disabling any observer.
    */
    if (
        typeof window.MutationObserver === "function" &&
        !window.__MI_OBSERVER_GUARD_INSTALLED__
    ) {
        window.__MI_OBSERVER_GUARD_INSTALLED__ = true;

        const NativeMutationObserver = window.MutationObserver;

        window.MutationObserver = function (callback) {
            let queuedRecords = [];
            let queuedObserver = null;
            let scheduled = false;

            const nativeObserver = new NativeMutationObserver(
                function (records, observer) {
                    queuedRecords.push.apply(
                        queuedRecords,
                        records
                    );

                    queuedObserver = observer;

                    if (scheduled) {
                        return;
                    }

                    scheduled = true;

                    requestAnimationFrame(function () {
                        const recordsToSend =
                            queuedRecords.slice();

                        const observerToSend =
                            queuedObserver;

                        queuedRecords.length = 0;
                        queuedObserver = null;
                        scheduled = false;

                        try {
                            callback(
                                recordsToSend,
                                observerToSend
                            );
                        } catch (error) {
                            console.error(
                                "[MI AI] Observer callback error:",
                                error
                            );
                        }
                    });
                }
            );

            return nativeObserver;
        };

        window.MutationObserver.prototype =
            NativeMutationObserver.prototype;
    }

    function releaseBusyState() {
        const classes = [
            "loading",
            "is-loading",
            "app-loading",
            "page-loading",
            "booting",
            "mi-app-booting",
            "mi-smooth-loading"
        ];

        document.documentElement.classList.remove(
            ...classes
        );

        document.documentElement.style.removeProperty(
            "cursor"
        );

        if (document.body) {
            document.body.classList.remove(...classes);
            document.body.removeAttribute("aria-busy");
            document.body.style.removeProperty("cursor");
        }

        document.querySelectorAll(
            '[style*="cursor: wait"],' +
            '[style*="cursor:wait"],' +
            '[style*="cursor: progress"],' +
            '[style*="cursor:progress"]'
        ).forEach(function (element) {
            element.style.removeProperty("cursor");
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            releaseBusyState,
            { once: true }
        );
    } else {
        releaseBusyState();
    }

    window.addEventListener(
        "mi-ai-main-started",
        releaseBusyState,
        { once: true }
    );

    window.setTimeout(releaseBusyState, 1000);
    window.setTimeout(releaseBusyState, 3000);
})();
