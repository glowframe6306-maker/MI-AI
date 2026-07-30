
(function () {
    "use strict";

    function resetMouseCursor() {
        try {
            document.documentElement.style.removeProperty("cursor");

            if (document.body) {
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
        } catch (error) {
            console.warn("[CORTEX CORE AI] Cursor reset failed:", error);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            resetMouseCursor,
            { once: true }
        );
    } else {
        resetMouseCursor();
    }

    window.addEventListener("load", resetMouseCursor, { once: true });

    setTimeout(resetMouseCursor, 500);
    setTimeout(resetMouseCursor, 2000);
})();
