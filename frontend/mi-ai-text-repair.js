(function () {
    "use strict";

    if (window.__miAiTextRepairInstalled) {
        return;
    }

    window.__miAiTextRepairInstalled = true;

    const suspicious =
        /(?:Ã|Â|ðŸ|ð|â€|â€™|â€œ|â€|â|âš|ï¸|Æ’|ƒ|‚|€|™)/;

    const cp1252 = new Map([
        [0x20AC, 0x80],
        [0x201A, 0x82],
        [0x0192, 0x83],
        [0x201E, 0x84],
        [0x2026, 0x85],
        [0x2020, 0x86],
        [0x2021, 0x87],
        [0x02C6, 0x88],
        [0x2030, 0x89],
        [0x0160, 0x8A],
        [0x2039, 0x8B],
        [0x0152, 0x8C],
        [0x017D, 0x8E],
        [0x2018, 0x91],
        [0x2019, 0x92],
        [0x201C, 0x93],
        [0x201D, 0x94],
        [0x2022, 0x95],
        [0x2013, 0x96],
        [0x2014, 0x97],
        [0x02DC, 0x98],
        [0x2122, 0x99],
        [0x0161, 0x9A],
        [0x203A, 0x9B],
        [0x0153, 0x9C],
        [0x017E, 0x9E],
        [0x0178, 0x9F]
    ]);

    const exactFixes = [
        ["ðŸ“Œ", "📌"],
        ["ðŸ’¬", "💬"],
        ["âŒ", "❌"],
        ["ðŸ—‘ï¸", "🗑️"],
        ["ðŸ—‘", "🗑"],
        ["ðŸ“¤", "📤"],
        ["ðŸ–Šï¸", "🖊️"],
        ["ðŸ–Š", "🖊"],
        ["âš™ï¸", "⚙️"],
        ["âš™", "⚙"],
        ["ðŸŽ§", "🎧"],
        ["ðŸ””", "🔔"],
        ["ðŸ“§", "📧"],
        ["ðŸšª", "🚪"],
        ["âž•", "➕"],
        ["ðŸ‘¤", "👤"],
        ["ðŸ›¡ï¸", "🛡️"],
        ["ðŸ›¡", "🛡"]
    ];

    function score(value) {
        const matches = String(value || "").match(
            /(?:Ã|Â|ðŸ|ð|â€|â€™|â€œ|â|âš|ï¸|Æ’|ƒ|‚|€|™)/g
        );

        return matches ? matches.length : 0;
    }

    function applyExactFixes(value) {
        let result = String(value ?? "");

        for (const [broken, correct] of exactFixes) {
            result = result.split(broken).join(correct);
        }

        return result;
    }

    function toBytes(value) {
        const bytes = [];

        for (const character of value) {
            const code = character.codePointAt(0);

            if (code <= 255) {
                bytes.push(code);
            } else if (cp1252.has(code)) {
                bytes.push(cp1252.get(code));
            } else {
                return null;
            }
        }

        return new Uint8Array(bytes);
    }

    function decodeLayer(value) {
        const original = String(value ?? "");

        if (!suspicious.test(original)) {
            return original;
        }

        const bytes = toBytes(original);

        if (!bytes) {
            return original;
        }

        try {
            const decoded = new TextDecoder(
                "utf-8",
                { fatal: true }
            ).decode(bytes);

            return score(decoded) < score(original)
                ? decoded
                : original;
        } catch (error) {
            return original;
        }
    }

    function repairText(value) {
        const original = String(value ?? "");
        let current = applyExactFixes(original);

        for (let pass = 0; pass < 8; pass += 1) {
            const repaired = applyExactFixes(
                decodeLayer(current)
            );

            if (repaired === current) {
                break;
            }

            if (score(repaired) > score(current)) {
                break;
            }

            current = repaired;
        }

        return score(current) <= score(original)
            ? current
            : original;
    }

    window.miAiRepairVisibleText = repairText;

    function ignored(element) {
        return Boolean(
            element &&
            element.closest &&
            element.closest(
                "script, style, code, pre, textarea, noscript"
            )
        );
    }

    function repairTextNode(node) {
        if (
            !node ||
            node.nodeType !== Node.TEXT_NODE ||
            ignored(node.parentElement)
        ) {
            return;
        }

        const original = node.nodeValue || "";

        if (!suspicious.test(original)) {
            return;
        }

        const repaired = repairText(original);

        if (repaired !== original) {
            node.nodeValue = repaired;
        }
    }

    function repairAttributes(element) {
        if (!element || !element.getAttribute) {
            return;
        }

        for (const name of [
            "title",
            "aria-label",
            "placeholder"
        ]) {
            const original = element.getAttribute(name);

            if (!original || !suspicious.test(original)) {
                continue;
            }

            const repaired = repairText(original);

            if (repaired !== original) {
                element.setAttribute(name, repaired);
            }
        }

        if (
            "value" in element &&
            typeof element.value === "string" &&
            suspicious.test(element.value)
        ) {
            element.value = repairText(element.value);
        }
    }

    function repairRoot(root) {
        if (!root) {
            return;
        }

        if (root.nodeType === Node.TEXT_NODE) {
            repairTextNode(root);
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

        let textNode;

        while ((textNode = walker.nextNode())) {
            repairTextNode(textNode);
        }

        if (root.nodeType === Node.ELEMENT_NODE) {
            repairAttributes(root);
        }

        if (root.querySelectorAll) {
            root.querySelectorAll(
                "[title], [aria-label], [placeholder], input, button, option"
            ).forEach(repairAttributes);
        }
    }

    function start() {
        repairRoot(document.body);

        const observer = new MutationObserver(function (records) {
            for (const record of records) {
                if (record.type === "characterData") {
                    repairTextNode(record.target);
                }

                for (const node of record.addedNodes || []) {
                    repairRoot(node);
                }

                if (
                    record.type === "attributes" &&
                    record.target
                ) {
                    repairAttributes(record.target);
                }
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true,
            attributes: true,
            attributeFilter: [
                "title",
                "aria-label",
                "placeholder",
                "value"
            ]
        });

        setTimeout(function () {
            repairRoot(document.body);
        }, 500);

        setTimeout(function () {
            repairRoot(document.body);
        }, 1500);

        setTimeout(function () {
            repairRoot(document.body);
        }, 3000);
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