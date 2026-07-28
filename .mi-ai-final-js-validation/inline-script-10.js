
/* MI AI CHIEF OWNER FRONTEND RESTORE V1 START */
(function () {
    "use strict";

    var accessState = {
        authenticated: false,
        role: "guest",
        isChiefOwner: false,
        permissions: {}
    };

    var ownerSelectors = [
        "[data-chief-owner]",
        "[data-owner-only]",
        "[data-admin-only]",
        ".chief-owner-only",
        ".owner-only",
        ".mi-chief-owner-only",
        "#chiefOwnerPanel",
        "#chief-owner-panel",
        "#ownerPanel",
        "#owner-panel",
        "#adminPanel",
        "#admin-panel",
        "#roleRequests",
        "#role-requests",
        "#roleManagement",
        "#role-management",
        "#manageSubOwners",
        "#manage-sub-owners",
        "#manageAdmins",
        "#manage-admins"
    ];

    function setOwnerElementsVisible(visible) {
        ownerSelectors.forEach(function (selector) {
            try {
                document
                    .querySelectorAll(selector)
                    .forEach(function (element) {
                        if (!element.dataset.miOriginalDisplay) {
                            element.dataset.miOriginalDisplay =
                                element.style.display || "";
                        }

                        if (visible) {
                            element.hidden = false;
                            element.style.display =
                                element.dataset.miOriginalDisplay || "";
                            element.removeAttribute(
                                "aria-hidden"
                            );
                        } else {
                            element.hidden = true;
                            element.style.display = "none";
                            element.setAttribute(
                                "aria-hidden",
                                "true"
                            );
                        }
                    });
            } catch (error) {}
        });
    }

    function applyAccess(access) {
        accessState = Object.assign(
            {
                authenticated: false,
                role: "guest",
                isChiefOwner: false,
                permissions: {}
            },
            access || {}
        );

        window.miChiefOwnerAccess = accessState;
        window.MI_CHIEF_OWNER_ACCESS = accessState;

        document.documentElement.classList.toggle(
            "mi-chief-owner",
            Boolean(accessState.isChiefOwner)
        );

        if (document.body) {
            document.body.classList.toggle(
                "mi-chief-owner",
                Boolean(accessState.isChiefOwner)
            );
        }

        setOwnerElementsVisible(
            Boolean(accessState.isChiefOwner)
        );

        window.dispatchEvent(
            new CustomEvent(
                "mi-chief-owner-access-changed",
                {
                    detail: accessState
                }
            )
        );

        console.log(
            "[MI Chief Owner] Access synchronized:",
            accessState
        );
    }

    async function getFirebaseUser() {
        try {
            if (
                window.firebase &&
                firebase.auth &&
                typeof firebase.auth === "function"
            ) {
                return firebase.auth().currentUser || null;
            }
        } catch (error) {}

        try {
            if (
                window.miFirebaseAuth &&
                window.miFirebaseAuth.currentUser
            ) {
                return window.miFirebaseAuth.currentUser;
            }
        } catch (error) {}

        return null;
    }

    async function synchronizeChiefOwnerAccess(
        forceRefresh
    ) {
        var user = await getFirebaseUser();

        if (!user || typeof user.getIdToken !== "function") {
            applyAccess({
                authenticated: false,
                role: "guest",
                isChiefOwner: false,
                permissions: {}
            });

            return window.miChiefOwnerAccess;
        }

        try {
            var token = await user.getIdToken(
                Boolean(forceRefresh)
            );

            var response = await fetch(
                "/api/chief-owner/me",
                {
                    method: "GET",
                    headers: {
                        "Authorization": "Bearer " + token,
                        "Accept": "application/json"
                    },
                    cache: "no-store"
                }
            );

            var payload = await response
                .json()
                .catch(function () {
                    return {};
                });

            if (!response.ok) {
                throw new Error(
                    payload.error ||
                    "Chief Owner authorization failed."
                );
            }

            applyAccess(payload);

            return payload;

        } catch (error) {
            console.error(
                "[MI Chief Owner] Authorization error:",
                error
            );

            applyAccess({
                authenticated: true,
                role: "user",
                isChiefOwner: false,
                permissions: {},
                error: String(
                    error && error.message || error
                )
            });

            return window.miChiefOwnerAccess;
        }
    }

    window.synchronizeChiefOwnerAccess =
        synchronizeChiefOwnerAccess;

    window.miHasPermission = function (permission) {
        if (accessState.isChiefOwner) {
            return true;
        }

        return Boolean(
            accessState.permissions &&
            accessState.permissions[permission]
        );
    };

    function attachFirebaseListener() {
        try {
            if (
                window.firebase &&
                firebase.auth &&
                typeof firebase.auth === "function"
            ) {
                firebase.auth().onAuthStateChanged(
                    function (user) {
                        if (user) {
                            synchronizeChiefOwnerAccess(true);
                        } else {
                            applyAccess({
                                authenticated: false,
                                role: "guest",
                                isChiefOwner: false,
                                permissions: {}
                            });
                        }
                    }
                );

                return true;
            }
        } catch (error) {}

        return false;
    }

    function startOwnerSynchronization() {
        setOwnerElementsVisible(false);

        var attempts = 0;

        var timer = setInterval(function () {
            attempts += 1;

            if (attachFirebaseListener()) {
                clearInterval(timer);
                synchronizeChiefOwnerAccess(true);
                return;
            }

            if (attempts >= 40) {
                clearInterval(timer);
                synchronizeChiefOwnerAccess(false);
            }
        }, 250);

        window.addEventListener(
            "focus",
            function () {
                synchronizeChiefOwnerAccess(false);
            }
        );

        window.addEventListener(
            "mi-login-success",
            function () {
                synchronizeChiefOwnerAccess(true);
            }
        );

        window.addEventListener(
            "mi-logout",
            function () {
                applyAccess({
                    authenticated: false,
                    role: "guest",
                    isChiefOwner: false,
                    permissions: {}
                });
            }
        );
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            startOwnerSynchronization,
            { once: true }
        );
    } else {
        startOwnerSynchronization();
    }
})();
/* MI AI CHIEF OWNER FRONTEND RESTORE V1 END */
