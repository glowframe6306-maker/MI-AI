
/* CORTEX CORE AI SAFE CHAT ONLY CLEAR V4 START */
(function () {
    "use strict";

    var PURGE_VERSION =
        "mi_ai_safe_chat_only_clear_20260718_v4";

    var DONE_KEY =
        "__mi_ai_safe_chat_clear_done__:" + PURGE_VERSION;

    function isChatKey(key) {
        var lower = String(key || "").toLowerCase();

        var chatWords = [
            "chat",
            "message",
            "conversation",
            "history",
            "thread",
            "saved_chats",
            "savedchats",
            "chatlist",
            "chat_list",
            "recent_chats",
            "recentchats",
            "current_chat",
            "currentchat",
            "active_chat",
            "activechat",
            "guest_chat",
            "guestchat"
        ];

        return chatWords.some(function (word) {
            return lower.indexOf(word) !== -1;
        });
    }

    function isProtectedSettingKey(key) {
        var lower = String(key || "").toLowerCase();

        var protectedWords = [
            "firebase:authuser:",
            "firebase-heartbeat",
            "firebase-installations",
            "auth",
            "token",
            "login",
            "session_user",
            "current_user",
            "theme",
            "font",
            "language",
            "locale",
            "setting",
            "appearance",
            "accent",
            "color",
            "background",
            "wallpaper",
            "notification",
            "sound",
            "voice",
            "accessibility",
            "translation",
            "profile",
            "role",
            "permission"
        ];

        return protectedWords.some(function (word) {
            return lower.indexOf(word) !== -1;
        });
    }

    function clearChatLocalStorageOnly() {
        var keys = [];

        for (var index = 0; index < localStorage.length; index += 1) {
            var key = localStorage.key(index);

            if (key) {
                keys.push(key);
            }
        }

        keys.forEach(function (key) {
            if (
                isChatKey(key) &&
                !isProtectedSettingKey(key)
            ) {
                try {
                    localStorage.removeItem(key);
                } catch (error) {}
            }
        });

        try {
            localStorage.setItem(DONE_KEY, "done");
        } catch (error) {}
    }

    function clearChatSessionStorageOnly() {
        try {
            var keys = [];

            for (
                var index = 0;
                index < sessionStorage.length;
                index += 1
            ) {
                var key = sessionStorage.key(index);

                if (key) {
                    keys.push(key);
                }
            }

            keys.forEach(function (key) {
                if (
                    isChatKey(key) &&
                    !isProtectedSettingKey(key)
                ) {
                    sessionStorage.removeItem(key);
                }
            });
        } catch (error) {}
    }

    function clearChatIndexedDBOnly() {
        try {
            if (
                !window.indexedDB ||
                typeof indexedDB.databases !== "function"
            ) {
                return;
            }

            indexedDB.databases()
                .then(function (databases) {
                    (databases || []).forEach(function (database) {
                        var name = String(
                            database &&
                            database.name ||
                            ""
                        );

                        var lower = name.toLowerCase();

                        var isChatDatabase =
                            lower.indexOf("chat") !== -1 ||
                            lower.indexOf("message") !== -1 ||
                            lower.indexOf("conversation") !== -1;

                        var isProtectedDatabase =
                            lower.indexOf("firebase") !== -1 ||
                            lower.indexOf("auth") !== -1 ||
                            lower.indexOf("setting") !== -1;

                        if (
                            isChatDatabase &&
                            !isProtectedDatabase
                        ) {
                            try {
                                indexedDB.deleteDatabase(name);
                            } catch (error) {}
                        }
                    });
                })
                .catch(function () {});
        } catch (error) {}
    }

    function clearVisibleChatElements() {
        var selectors = [
            "#chat",
            "#chatList",
            "#chat-list",
            "#savedChats",
            "#saved-chats",
            ".chat-list",
            ".saved-chats",
            "[data-chat-list]"
        ];

        selectors.forEach(function (selector) {
            try {
                document
                    .querySelectorAll(selector)
                    .forEach(function (element) {
                        element.innerHTML = "";
                    });
            } catch (error) {}
        });
    }

    if (localStorage.getItem(DONE_KEY) !== "done") {
        clearChatLocalStorageOnly();
        clearChatSessionStorageOnly();
        clearChatIndexedDBOnly();

        console.log(
            "[CORTEX CORE AI] Old chats cleared; settings preserved."
        );
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            function () {
                clearVisibleChatElements();
                setTimeout(clearVisibleChatElements, 500);
            },
            { once: true }
        );
    } else {
        clearVisibleChatElements();
        setTimeout(clearVisibleChatElements, 500);
    }
})();
/* CORTEX CORE AI SAFE CHAT ONLY CLEAR V4 END */
