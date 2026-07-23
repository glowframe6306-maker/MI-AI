(function () {
    "use strict";

    if (window.__miAiFinalUnknownCharacterCleaner) {
        return;
    }

    window.__miAiFinalUnknownCharacterCleaner = true;

    const suspiciousPattern =
        /[\u0080-\u024F\u2000-\u206F\uFFFD]|Ã|Â|ð|â|ï|Æ|ƒ|‚|€|™|œ|ž|Ÿ/;

    const knownLabels = [
        ["Chief Owner Permissions", "Chief Owner Permissions"],
        ["Customer Support", "Customer Support"],
        ["User Greeting", "User Greeting"],
        ["NEW CHAT", "New Chat"],
        ["New Chat", "New Chat"],
        ["Settings", "Settings"],
        ["Logout", "Logout"],
        ["Login", "Login"]
    ];

    function knownReadableText(value) {
        const text = String(value || "");

        for (const [search, replacement] of knownLabels) {
            if (text.toLowerCase().includes(search.toLowerCase())) {
                return replacement;
            }
        }

        return null;
    }

    function removeCorruptedCharacters(value) {
        const original = String(value ?? "");

        if (!suspiciousPattern.test(original)) {
            return original;
        }

        const known = knownReadableText(original);

        if (known) {
            return known;
        }

        let cleaned = original
            // Remove C1 control and common mojibake character ranges.
            .replace(/[\u0080-\u024F]/g, "")
            .replace(/[\u2000-\u206F]/g, " ")
            .replace(/\uFFFD/g, "")
            // Remove remaining known corruption marker characters.
            .replace(/[ÃÂðâïÆƒ‚€™œžŸ¤¢£]/g, "")
            // Remove invisible control characters except line breaks and tabs.
            .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "")
            // Clean repeated punctuation and spacing left by corruption.
            .replace(/[¦§¨¬­¯°±´µ¶·¸¿]+/g, "")
            .replace(/[ \t]{2,}/g, " ")
            .replace(/\s*\n\s*/g, " ")
            .trim();

        // Keep readable Latin, numbers, Sinhala, Tamil and normal symbols.
        const readableMatches = cleaned.match(
            /[A-Za-z0-9\u0D80-\u0DFF\u0B80-\u0BFF]+/g
        );

        if (!readableMatches || readableMatches.length === 0) {
            return "";
        }

        return cleaned;
    }

    window.miAiRemoveCorruptedCharacters =
        removeCorruptedCharacters;

    function ignored(element) {
        return Boolean(
            element &&
            element.closest &&
            element.closest(
                "script, style, code, pre, textarea, noscript"
            )
        );
    }

    function cleanTextNode(node) {
        if (
            !node ||
            node.nodeType !== Node.TEXT_NODE ||
            ignored(node.parentElement)
        ) {
            return;
        }

        const original = node.nodeValue || "";

        if (!suspiciousPattern.test(original)) {
            return;
        }

        const cleaned = removeCorruptedCharacters(original);

        if (cleaned !== original) {
            node.nodeValue = cleaned;
        }
    }

    function cleanAttribute(element, name) {
        if (!element || !element.getAttribute) {
            return;
        }

        const original = element.getAttribute(name);

        if (!original || !suspiciousPattern.test(original)) {
            return;
        }

        const cleaned = removeCorruptedCharacters(original);

        if (cleaned) {
            element.setAttribute(name, cleaned);
        } else {
            element.removeAttribute(name);
        }
    }

    function cleanValue(element) {
        if (
            !element ||
            !("value" in element) ||
            typeof element.value !== "string" ||
            !suspiciousPattern.test(element.value)
        ) {
            return;
        }

        element.value =
            removeCorruptedCharacters(element.value);
    }

    function cleanRoot(root) {
        if (!root) {
            return;
        }

        if (root.nodeType === Node.TEXT_NODE) {
            cleanTextNode(root);
            return;
        }

        if (
            root.nodeType !== Node.ELEMENT_NODE &&
            root.nodeType !== Node.DOCUMENT_NODE &&
            root.nodeType !== Node.DOCUMENT_FRAGMENT_NODE
        ) {
            return;
        }

        if (
            root.nodeType === Node.ELEMENT_NODE &&
            ignored(root)
        ) {
            return;
        }

        const walker = document.createTreeWalker(
            root,
            NodeFilter.SHOW_TEXT
        );

        let node;

        while ((node = walker.nextNode())) {
            cleanTextNode(node);
        }

        const elements = [];

        if (root.nodeType === Node.ELEMENT_NODE) {
            elements.push(root);
        }

        if (root.querySelectorAll) {
            elements.push(
                ...root.querySelectorAll(
                    "[title], [aria-label], [placeholder], " +
                    "input, button, option"
                )
            );
        }

        for (const element of elements) {
            cleanAttribute(element, "title");
            cleanAttribute(element, "aria-label");
            cleanAttribute(element, "placeholder");
            cleanValue(element);
        }
    }

    function cleanStoredObject(value) {
        if (typeof value === "string") {
            return removeCorruptedCharacters(value);
        }

        if (Array.isArray(value)) {
            return value.map(cleanStoredObject);
        }

        if (
            value &&
            typeof value === "object"
        ) {
            const result = {};

            for (const [key, child] of Object.entries(value)) {
                result[key] = cleanStoredObject(child);
            }

            return result;
        }

        return value;
    }

    function cleanStorage(storage) {
        const updates = [];

        for (let index = 0; index < storage.length; index += 1) {
            const key = storage.key(index);

            if (!key) {
                continue;
            }

            const original = storage.getItem(key);

            if (!original || !suspiciousPattern.test(original)) {
                continue;
            }

            try {
                const parsed = JSON.parse(original);
                const cleaned = cleanStoredObject(parsed);

                updates.push([
                    key,
                    JSON.stringify(cleaned)
                ]);
            } catch (error) {
                updates.push([
                    key,
                    removeCorruptedCharacters(original)
                ]);
            }
        }

        for (const [key, cleaned] of updates) {
            storage.setItem(key, cleaned);
        }
    }

    let scheduled = false;

    function scheduleClean() {
        if (scheduled) {
            return;
        }

        scheduled = true;

        requestAnimationFrame(function () {
            scheduled = false;
            cleanRoot(document.body);
        });
    }

    function start() {
        try {
            cleanStorage(localStorage);
            cleanStorage(sessionStorage);
        } catch (error) {
            console.warn(
                "[MI AI] Stored title cleanup skipped:",
                error
            );
        }

        cleanRoot(document.body);

        const observer = new MutationObserver(function (records) {
            for (const record of records) {
                if (record.type === "characterData") {
                    cleanTextNode(record.target);
                }

                for (const addedNode of record.addedNodes || []) {
                    cleanRoot(addedNode);
                }

                if (
                    record.type === "attributes" &&
                    record.target
                ) {
                    cleanRoot(record.target);
                }
            }

            scheduleClean();
        });

        observer.observe(document.body, {
            subtree: true,
            childList: true,
            characterData: true,
            attributes: true,
            attributeFilter: [
                "title",
                "aria-label",
                "placeholder",
                "value"
            ]
        });

        setTimeout(scheduleClean, 100);
        setTimeout(scheduleClean, 500);
        setTimeout(scheduleClean, 1000);
        setTimeout(scheduleClean, 2000);
        setTimeout(scheduleClean, 5000);
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            start,
            { once: true }
        );
    } else {
        start();
    }
})();