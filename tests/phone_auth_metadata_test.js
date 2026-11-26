const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const phone = require("../vendor/mi-phone-number.js");

const countries = phone.getCountries();
const countryByIso = Object.fromEntries(countries.map(country => [country.iso, country]));
const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");

assert.ok(countries.length > 200, "phone metadata should include worldwide regions");
assert.equal(countryByIso.LK.callingCode, "94");
assert.equal(countryByIso.LK.name, "Sri Lanka");
assert.equal(countryByIso.IN.callingCode, "91");
assert.equal(countryByIso.GB.callingCode, "44");
assert.equal(countryByIso.US.callingCode, "1");
assert.ok(countryByIso.LK.flag, "country entries include a flag");
assert.ok(countries.filter(country => country.callingCode === "1").length > 1,
    "regions sharing +1 remain distinct");

assert.ok(phone.searchCountries("sRi LaNkA").some(country => country.iso === "LK"));
assert.ok(phone.searchCountries("+91").some(country => country.iso === "IN"));
assert.ok(phone.searchCountries("gb").some(country => country.iso === "GB"));
assert.ok(phone.searchCountries("United States").some(country => country.iso === "US"));
assert.ok(phone.searchCountries("+1").some(country => country.iso === "CA"));
assert.ok(!phone.searchCountries("+44").some(country => country.iso === "AO"),
    "calling-code searches do not match unrelated codes containing the same digits");
assert.equal(phone.searchCountries("not-a-real-place").length, 0);

assert.equal(phone.inferCountry("+919876543210", "LK"), "IN");
assert.equal(phone.normalizeNumber("077 123 4567", "LK").e164, "+94771234567");
assert.equal(phone.normalizeNumber("94771234567", "LK").e164, "+94771234567",
    "a pasted selected-country prefix is not duplicated");
assert.equal(phone.normalizeNumber("9876543210", "IN").e164, "+919876543210");
assert.equal(phone.normalizeNumber("07911 123456", "GB").e164, "+447911123456");
assert.equal(phone.normalizeNumber("2025550123", "US").e164, "+12025550123");
assert.equal(phone.normalizeNumber("not a number", "LK").reason, "characters");
assert.equal(phone.normalizeNumber("123", "LK").ok, false);
assert.ok(phone.formatInput("0771234567", "LK"));

assert.match(html, /var miPhoneSelectedRegion = ['"]LK['"]/);
assert.match(html, /signInWithPhoneNumber\(miPhoneNumber, miPhoneRecaptcha\)/);
assert.match(html, /miPhoneNumber = normalized\.e164/);
assert.match(html, /id="miPhoneCountryButton"/);

console.log("phone auth metadata and normalization tests passed");
