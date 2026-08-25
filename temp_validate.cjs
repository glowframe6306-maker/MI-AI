const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync('index.html', 'utf8');
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
scripts.forEach((match, index) => new vm.Script(match[1], { filename: `index.html#script-${index + 1}` }));
console.log(`PASS: ${scripts.length} inline scripts parsed`);
