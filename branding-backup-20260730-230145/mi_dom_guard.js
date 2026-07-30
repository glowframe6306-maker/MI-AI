(function () {
    "use strict";

    if (window.__MI_DOM_GUARD_INSTALLED__) return;
    window.__MI_DOM_GUARD_INSTALLED__ = true;

    function looksLikeLooseJavaScriptFragment(value) {
        if (typeof value !== "string") return false;

        const trimmed = value.replace(/^\s+|\s+$/g, "");
        if (!trimmed) return false;
        if (/<\/?script\b/i.test(trimmed)) return false;

        return /(?:^|[\s;{}(])(?:function\s*\(|const\s+\w+|let\s+\w+|var\s+\w+|return\b|if\s*\(|for\s*\(|while\s*\(|switch\s*\(|try\s*\{|catch\s*\(|await\b|async\b|=>|document\.|window\.|console\.|new\s+\w+)/.test(trimmed);
    }

    function sanitizeHtmlForInsertion(value) {
        if (typeof value !== "string") return value;
        if (!value) return value;

        const matches = Array.from(value.matchAll(/<(\/)?script\b[^>]*>/gi));
        if (!matches.length) {
            return looksLikeLooseJavaScriptFragment(value)
                ? "<!-- mi-loose-js-fragment -->"
                : value;
        }

        let output = "";
        let cursor = 0;
        let insideScript = false;

        for (const match of matches) {
            const before = value.slice(cursor, match.index);
            const shouldNeutralize =
                !insideScript &&
                before.trim() &&
                looksLikeLooseJavaScriptFragment(before);

            output += shouldNeutralize ? "<!-- mi-loose-js-fragment -->" : before;
            output += match[0];
            cursor = match.index + match[0].length;
            insideScript = match[0].toLowerCase().startsWith("<script");
        }

        const tail = value.slice(cursor);
        if (!insideScript && tail.trim() && looksLikeLooseJavaScriptFragment(tail)) {
            output += "<!-- mi-loose-js-fragment -->";
        } else {
            output += tail;
        }

        return output;
    }

    function installInnerHtmlGuard() {
        if (typeof Element === "undefined") return;

        const descriptor = Object.getOwnPropertyDescriptor(Element.prototype, "innerHTML");
        if (!descriptor || descriptor.set == null) return;
        if (descriptor.set.__miPatched) return;

        const originalSet = descriptor.set;
        const originalGet = descriptor.get;

        Object.defineProperty(Element.prototype, "innerHTML", {
            configurable: true,
            enumerable: descriptor.enumerable,
            get: function () {
                return originalGet ? originalGet.call(this) : undefined;
            },
            set: function (value) {
                return originalSet.call(this, sanitizeHtmlForInsertion(value));
            }
        });

        descriptor.set.__miPatched = true;
    }

    function installInsertAdjacentHtmlGuard() {
        if (typeof Element === "undefined") return;

        const original = Element.prototype.insertAdjacentHTML;
        if (!original || original.__miPatched) return;

        Element.prototype.insertAdjacentHTML = function (position, value) {
            return original.call(this, position, sanitizeHtmlForInsertion(value));
        };

        original.__miPatched = true;
    }

    try {
        installInnerHtmlGuard();
        installInsertAdjacentHtmlGuard();
    } catch (error) {
        console.warn("[MI AI] DOM guard install failed", error);
    }

    window.MI_DOM_GUARD = {
        looksLikeLooseJavaScriptFragment: looksLikeLooseJavaScriptFragment,
        sanitizeHtmlForInsertion: sanitizeHtmlForInsertion
    };
})();
