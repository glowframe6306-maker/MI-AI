const assert = require('assert');
const fs = require('fs');
const path = require('path');

const source = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');

const helperMatch = source.match(/function dismissChatWelcome\(container\)\s*\{([^}]*)\}/);
assert.ok(helperMatch, 'welcome dismissal helper exists');

const dismissWelcome = new Function('container', helperMatch[1]);
let removed = false;
let queriedSelector = '';
dismissWelcome({
  querySelector(selector) {
    queriedSelector = selector;
    return { remove() { removed = true; } };
  }
});
assert.strictEqual(queriedSelector, '#miWelcomeV9');
assert.strictEqual(removed, true, 'dismisses the welcome in the active chat');

removed = false;
dismissWelcome({ querySelector() { return null; } });
assert.strictEqual(removed, false, 'is safe when the welcome is already absent');

const sendStart = source.indexOf('async function sendMessageInternal(msg)');
const sendEnd = source.indexOf('\nfunction scroll()', sendStart);
assert.ok(sendStart >= 0 && sendEnd > sendStart, 'send flow is present');
const sendFlow = source.slice(sendStart, sendEnd);
const bubbleAppend = sendFlow.indexOf('chatBox.appendChild(userBubble);');
const userMessageStored = sendFlow.indexOf("activeChat().push({ role: 'me', text: msg });");
const welcomeDismissed = sendFlow.indexOf('dismissChatWelcome(chatBox);');
const memoryWork = sendFlow.indexOf('const explicitMemorySave');
const conversationFailure = sendFlow.indexOf('Lazy conversation creation failed');
const attachmentFailure = sendFlow.indexOf('Unable to upload the selected file.');

assert.ok(bubbleAppend >= 0 && bubbleAppend < userMessageStored);
assert.ok(userMessageStored < welcomeDismissed, 'welcome is dismissed only after the user message is accepted');
assert.ok(welcomeDismissed < memoryWork, 'welcome is dismissed before waiting on later response work');
assert.ok(conversationFailure >= 0 && conversationFailure < welcomeDismissed, 'conversation-creation failures happen before dismissal');
assert.ok(attachmentFailure >= 0 && attachmentFailure < welcomeDismissed, 'attachment failures happen before dismissal');
assert.strictEqual((sendFlow.match(/activeChat\(\)\.push\(\{ role: 'me', text: msg \}\);/g) || []).length, 1, 'user message is not duplicated');

const openStart = source.indexOf('function openChatClean(chatId)');
const openEnd = source.indexOf('function renderListClean()', openStart);
assert.ok(openStart >= 0 && openEnd > openStart, 'chat-opening flow is present');
const openFlow = source.slice(openStart, openEnd);
assert.ok(/messages\.length\s*===\s*0[\s\S]*?attachments\.length\s*===\s*0[\s\S]*?container\.appendChild\(\s*createWelcome\(\)\s*\)/.test(openFlow), 'only an empty chat receives the welcome');
assert.ok(/messages\.forEach\([\s\S]*?appendStoredMessage/.test(openFlow), 'existing messages render without a welcome');

const createFlowStart = source.indexOf('async function createNewChatOnce()');
const createFlowEnd = source.indexOf('function queueNewChat()', createFlowStart);
assert.ok(createFlowStart >= 0 && createFlowEnd > createFlowStart, 'new-chat flow is present');
assert.ok(/createBlankChatRecord\(\)[\s\S]*?openChatClean\(\s*chatId\s*\)/.test(source.slice(createFlowStart, createFlowEnd)), 'new chats open through the empty-chat welcome path');

console.log('new chat welcome source tests passed');
