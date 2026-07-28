
(function () {
    "use strict";

    function revealApplication() {
        document.documentElement.classList.remove(
            "loading",
            "is-loading",
            "app-loading",
            "page-loading",
            "mi-app-booting",
            "mi-smooth-loading"
        );

        if (document.body) {
            document.body.classList.remove(
                "loading",
                "is-loading",
                "app-loading",
                "page-loading",
                "mi-app-booting",
                "mi-smooth-loading"
            );

            document.body.style.visibility = "visible";
            document.body.style.opacity = "1";
            document.body.removeAttribute("aria-busy");
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            revealApplication,
            { once: true }
        );
    } else {
        revealApplication();
    }

    window.setTimeout(revealApplication, 1000);
    window.setTimeout(revealApplication, 3000);
})();
