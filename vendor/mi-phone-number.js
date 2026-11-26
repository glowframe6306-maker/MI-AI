(function (root, factory) {
    if (typeof module === "object" && module.exports) {
        module.exports = factory(require("./libphonenumber-js.min.js"));
    } else {
        root.CortexPhoneNumber = factory(root.libphonenumber);
    }
})(typeof globalThis === "object" ? globalThis : this, function (phoneLibrary) {
    "use strict";

    if (!phoneLibrary) {
        throw new Error("The phone-number metadata library must load first.");
    }

    var countryList = null;
    var countriesByIso = null;
    var countryNames = new Intl.DisplayNames(["en"], { type: "region" });

    function flagForRegion(region) {
        return Array.from(region.toUpperCase()).map(function (letter) {
            return String.fromCodePoint(127397 + letter.charCodeAt(0));
        }).join("");
    }

    function getCountries() {
        if (countryList) return countryList;

        countryList = phoneLibrary.getCountries().map(function (region) {
            return {
                iso: region,
                name: countryNames.of(region) || region,
                callingCode: phoneLibrary.getCountryCallingCode(region),
                flag: flagForRegion(region)
            };
        }).sort(function (left, right) {
            return left.name.localeCompare(right.name);
        });

        countriesByIso = Object.create(null);
        countryList.forEach(function (country) {
            countriesByIso[country.iso] = country;
        });
        return countryList;
    }

    function searchCountries(query) {
        var term = String(query || "").trim().toLocaleLowerCase();
        if (!term) return getCountries();

        var callingCodeTerm = term.replace(/^\+/, "").replace(/\D/g, "");
        return getCountries().filter(function (country) {
            return country.name.toLocaleLowerCase().includes(term) ||
                country.iso.toLocaleLowerCase() === term ||
                country.iso.toLocaleLowerCase().includes(term) ||
                (callingCodeTerm && country.callingCode.includes(callingCodeTerm));
        });
    }

    function formatInput(value, region) {
        var input = String(value || "");
        if (!input) return "";
        try {
            return new phoneLibrary.AsYouType(region).input(input);
        } catch (_) {
            return input;
        }
    }

    function parseNumber(value, region) {
        try {
            return phoneLibrary.parsePhoneNumber(value, region);
        } catch (_) {
            return undefined;
        }
    }

    function inferCountry(value, defaultRegion) {
        var input = String(value || "").trim();
        if (!input.startsWith("+")) return defaultRegion;
        var parsed = parseNumber(input);
        return parsed && parsed.country && getCountriesByIso()[parsed.country]
            ? parsed.country
            : defaultRegion;
    }

    function getCountriesByIso() {
        if (!countriesByIso) getCountries();
        return countriesByIso;
    }

    function normalizeNumber(value, selectedRegion) {
        var input = String(value || "").trim();
        var selectedCountry = getCountriesByIso()[selectedRegion];
        if (!selectedCountry) {
            return { ok: false, reason: "country", country: selectedRegion };
        }
        if (!input) {
            return { ok: false, reason: "empty", country: selectedRegion };
        }
        if (!/^\+?[\d\s().-]+$/.test(input)) {
            return { ok: false, reason: "characters", country: selectedRegion };
        }

        var parsed = parseNumber(input, selectedRegion);
        if ((!parsed || !parsed.isValid()) && !input.startsWith("+")) {
            var digits = input.replace(/\D/g, "");
            if (digits.startsWith(selectedCountry.callingCode)) {
                var withInternationalPrefix = parseNumber("+" + digits);
                if (withInternationalPrefix && withInternationalPrefix.isValid()) {
                    parsed = withInternationalPrefix;
                }
            }
        }

        if (!parsed || !parsed.isValid()) {
            return {
                ok: false,
                reason: parsed && !parsed.isPossible() ? "length" : "invalid",
                country: selectedRegion
            };
        }

        var resolvedRegion = parsed.country && getCountriesByIso()[parsed.country]
            ? parsed.country
            : selectedRegion;
        var resolvedCountry = getCountriesByIso()[resolvedRegion];
        return {
            ok: true,
            e164: parsed.number,
            country: resolvedRegion,
            callingCode: resolvedCountry.callingCode
        };
    }

    return {
        getCountries: getCountries,
        searchCountries: searchCountries,
        formatInput: formatInput,
        inferCountry: inferCountry,
        normalizeNumber: normalizeNumber
    };
});
