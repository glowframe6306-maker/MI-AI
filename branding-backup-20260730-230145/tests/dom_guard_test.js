const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const guardSource = fs.readFileSync(path.join(__dirname, '..', 'mi_dom_guard.js'), 'utf8');

function loadGuard() {
  const context = {
    window: {},
    document: {},
    Element: function Element() {},
    console: console,
    setTimeout,
    clearTimeout
  };

  context.window = context;
  context.global = context;
  context.globalThis = context;
  context.Element.prototype = {};

  vm.createContext(context);
  vm.runInContext(guardSource, context);
  return context.window.MI_DOM_GUARD;
}

const guard = loadGuard();

assert.strictEqual(
  guard.sanitizeHtmlForInsertion('<div class="ok">Hello</div>'),
  '<div class="ok">Hello</div>'
);

assert.strictEqual(
  guard.sanitizeHtmlForInsertion('function demo(){ return 1; }'),
  '<!-- mi-loose-js-fragment -->'
);

assert.ok(
  guard.sanitizeHtmlForInsertion('<div>Hi</div>function demo(){ return 1; }').includes('<!-- mi-loose-js-fragment -->')
);

assert.ok(
  guard.sanitizeHtmlForInsertion('<div>Hi</div><script>alert(1)</script><div>Bye</div>').includes('<script>alert(1)</script>')
);

console.log('dom guard regression tests passed');
