(function () {
    "use strict";

    if (window.__miAiVisibleCleanupInstalled) {
        return;
    }

    window.__miAiVisibleCleanupInstalled = true;

    const suspiciousPattern =
        /(?:Ã|Â|ð|â|ï|Æ|ƒ|‚|€|™|œ|ž|Ÿ|¤|¢|£)/;

    const exactLabels = [
        "Chief Owner Permissions",
        "Customer Support",
        "New Chat",
        "Settings",
        "Login",
        "Logout",
        "User Greeting"
    ];

    function suspiciousScore(value) {
        const matches = String(value || "").match(
            /(?:Ã|Â|ð|â|ï|Æ|ƒ|‚|€|™|œ|ž|Ÿ|¤|¢|£)/g
        );

        return matches ? matches.length : 0;
    }

    function cleanKnownLabel(value) {
        const text = String(value || "");

        for (const label of exactLabels) {
            if (text.includes(label)) {
                if (label === "Chief Owner Permissions") {
                    return "🛡️ Chief Owner Permissions";
                }

                if (label === "User Greeting") {
                    return "💬 User Greeting";
                }

                return label;
            }
        }

        return null;
    }

    function cleanMultilineText(value) {
        const text = String(value || "");

        if (!suspiciousPattern.test(text)) {
            return text;
        }

        const knownLabel = cleanKnownLabel(text);

        if (knownLabel) {
            return knownLabel;
        }

        const lines = text
            .split(/\r?\n/)
            .map(function (line) {
                return line.trim();
            })
            .filter(Boolean);

        const cleanLines = lines.filter(function (line) {
            return (
                suspiciousScore(line) === 0 &&
                /[A-Za-z0-9\u0D80-\u0DFF\u0B80-\u0BFF]/.test(line)
            );
        });

        if (cleanLines.length > 0) {
            return cleanLines.join(" ");
        }

        return text;
    }

    function cleanTextNode(node) {
        if (!node || node.nodeType !== Node.TEXT_NODE) {
            return;
        }

        const parent = node.parentElement;

        if (
            parent &&
            parent.closest(
                "script, style, code, pre, textarea, noscript"
            )
        ) {
            return;
        }

        const original = node.nodeValue || "";

        if (!suspiciousPattern.test(original)) {
            return;
        }

        const cleaned = cleanMultilineText(original);

        if (cleaned !== original) {
            node.nodeValue = cleaned;
        }
    }

    function cleanAttribute(element, attributeName) {
        if (!element || !element.getAttribute) {
            return;
        }

        const original = element.getAttribute(attributeName);

        if (!original || !suspiciousPattern.test(original)) {
            return;
        }

        const cleaned = cleanMultilineText(original);

        if (cleaned !== original) {
            element.setAttribute(attributeName, cleaned);
        }
    }

    function cleanElementText(element) {
        if (
            !element ||
            element.nodeType !== Node.ELEMENT_NODE ||
            element.closest(
                "script, style, code, pre, textarea, noscript"
            )
        ) {
            return;
        }

        const original = element.textContent || "";

        if (!suspiciousPattern.test(original)) {
            return;
        }

        const knownLabel = cleanKnownLabel(original);

        if (
            knownLabel &&
            element.children.length === 0
        ) {
            element.textContent = knownLabel;
        }
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

        if (root.nodeType === Node.ELEMENT_NODE) {
            cleanElementText(root);
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
                    "[title], [aria-label], [placeholder], button, a, option"
                )
            );
        }

        for (const element of elements) {
            cleanAttribute(element, "title");
            cleanAttribute(element, "aria-label");
            cleanAttribute(element, "placeholder");
            cleanElementText(element);
        }
    }

    function cleanStoredValue(value) {
        if (typeof value === "string") {
            return cleanMultilineText(value);
        }

        if (Array.isArray(value)) {
            return value.map(cleanStoredValue);
        }

        if (value && typeof value === "object") {
            const result = {};

            for (const [key, childValue] of Object.entries(value)) {
                result[key] = cleanStoredValue(childValue);
            }

            return result;
        }

        return value;
    }

    function cleanLocalStorage() {
        for (let index = 0; index < localStorage.length; index += 1) {
            const key = localStorage.key(index);

            if (!key) {
                continue;
            }

            const original = localStorage.getItem(key);

            if (!original || !suspiciousPattern.test(original)) {
                continue;
            }

            try {
                const parsed = JSON.parse(original);
                const cleaned = cleanStoredValue(parsed);
                const serialized = JSON.stringify(cleaned);

                if (serialized !== original) {
                    localStorage.setItem(key, serialized);
                }
            } catch (error) {
                const cleaned = cleanMultilineText(original);

                if (cleaned !== original) {
                    localStorage.setItem(key, cleaned);
                }
            }
        }
    }

    let scheduled = false;

    function scheduleCleanup() {
        if (scheduled) {
            return;
        }

        scheduled = true;

        requestAnimationFrame(function () {
            scheduled = false;
            cleanRoot(document.body);
        });
    }

    function startCleanup() {
        try {
            cleanLocalStorage();
        } catch (error) {
            console.warn(
                "[MI AI] Local visible-text cleanup skipped:",
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

            scheduleCleanup();
        });

        observer.observe(document.body, {
            subtree: true,
            childList: true,
            characterData: true,
            attributes: true,
            attributeFilter: [
                "title",
                "aria-label",
                "placeholder"
            ]
        });

        setTimeout(scheduleCleanup, 250);
        setTimeout(scheduleCleanup, 750);
        setTimeout(scheduleCleanup, 1500);
        setTimeout(scheduleCleanup, 3000);
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            startCleanup,
            { once: true }
        );
    } else {
        startCleanup();
    }
})();