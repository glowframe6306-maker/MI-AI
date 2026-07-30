
(function () {
    "use strict";

    if (window.__miMobileLargeNotchV1) return;
    window.__miMobileLargeNotchV1 = true;

    function ensureViewport() {
        let viewport = document.querySelector('meta[name="viewport"]');

        if (!viewport) {
            viewport = document.createElement("meta");
            viewport.name = "viewport";
            document.head.appendChild(viewport);
        }

        viewport.content =
            "width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover";
    }

    function markHeader() {
        const selectors = [
            "header",
            ".header",
            "#header",
            ".topbar",
            ".top-bar",
            ".app-header",
            ".chat-header",
            "nav",
            ".navbar"
        ];

        const header = document.querySelector(selectors.join(","));
        if (header) {
            header.setAttribute("data-mi-notch-safe-header", "true");
        }
    }

    function start() {
        ensureViewport();
        markHeader();

        const observer = new MutationObserver(function () {
            markHeader();
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start, { once: true });
    } else {
        start();
    }
})();
