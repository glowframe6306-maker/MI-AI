
window.FIREBASE_CONFIG = {
  apiKey: "AIzaSyAxrIAKDz0b9GdHp4K_-jBKZWIcWZTww5g",
  authDomain: "mi-ai-99e6a.firebaseapp.com",
  projectId: "mi-ai-99e6a",
  storageBucket: "mi-ai-99e6a.firebasestorage.app",
  messagingSenderId: "845086558623",
  appId: "1:845086558623:web:8ff161f6a157cf87d395aa"
};

let firebaseAuth = null;
let authMode = 'signin';
let user = null;
let currentLanguage = 'en';
let translations = {};
const translationCache = {};
const RTL_LANGUAGE_CODES = new Set(['ar', 'fa', 'he', 'ur']);
const SUPPORTED_LANGUAGES = [
  { code: 'en', file: 'en', label: 'English' },
  { code: 'si', file: 'si', label: 'Sinhala' },
  { code: 'ta', file: 'ta', label: 'Tamil' }
];
function getFirebaseConfig() {
  const config =
    window.FIREBASE_CONFIG &&
    typeof window.FIREBASE_CONFIG === "object"
      ? window.FIREBASE_CONFIG
      : null;

  if (
    !config ||
    !String(config.apiKey || "").trim() ||
    !String(config.authDomain || "").trim() ||
    !String(config.projectId || "").trim() ||
    !String(config.appId || "").trim()
  ) {
    return null;
  }

  return config;
}

async function initFirebase() {

    if (firebaseAuth) return firebaseAuth;

    const config = getFirebaseConfig();

    if (!config || !config.apiKey) {
        throw new Error("Firebase configuration is missing.");
    }

    if (!window.firebase || !window.firebase.apps) {
        throw new Error("Firebase SDK failed to load.");
    }

    if (!window.firebase.apps.length) {
        window.firebase.initializeApp(config);
    }

    firebaseAuth = window.firebase.auth();

    return firebaseAuth;
}

function getCurrentLanguageStorageKey() {
  const userId = (user && user.id) || localStorage.getItem('mi_user_id') || '';
  return userId ? `mi_language_${userId}` : null;
}

function getStoredLanguageCode() {
  if (!isAuthenticated()) return 'en';
  const storageKey = getCurrentLanguageStorageKey();
  if (!storageKey) return 'en';
  return localStorage.getItem(storageKey) || 'en';
}

function normalizeLanguageCode(code) {
  const candidate = (code || 'en').toLowerCase();
  const match = SUPPORTED_LANGUAGES.find((entry) => entry.code === candidate);
  return match ? match.code : 'en';
}

async function loadLocale(langCode) {
  const normalized = normalizeLanguageCode(langCode);
  if (translationCache[normalized]) return translationCache[normalized];

  const entry = SUPPORTED_LANGUAGES.find((item) => item.code === normalized) || SUPPORTED_LANGUAGES[0];
  try {
    const response = await fetch(`./locales/${entry.file}.json`);
    if (!response.ok) throw new Error('missing locale');
    const data = await response.json();
    translationCache[normalized] = data;
    return data;
  } catch (error) {
    translationCache[normalized] = {};
    return {};
  }
}

function t(key, fallback = '') {
  return sanitizeUiText(translations[key] || fallback || key);
}

function populateLanguageSelector() {
  const select = document.getElementById('languageSelect');
  if (!select) return;
  select.innerHTML = '';
  SUPPORTED_LANGUAGES.forEach((language) => {
    const option = document.createElement('option');
    option.value = language.code;
    option.textContent = language.label;
    select.appendChild(option);
  });
}

function updateTranslatedUi() {
  repairDocumentText(document.body);

  const loginBtn = document.getElementById('loginBtn');
  if (loginBtn) loginBtn.textContent = `${sanitizeUiText('🔐')} ${t('auth.login', 'Login')}`;

  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) logoutBtn.textContent = `${sanitizeUiText('↪')} ${t('auth.logout', 'Logout')}`;

  const newChatButton = document.querySelector('#sidebar button[onclick="newChat()"]');
  if (newChatButton) newChatButton.innerHTML = `${sanitizeUiText('➕')} ${t('sidebar.newChat', 'New Chat')}`;

  const settingsButton = document.getElementById('settingsBtn');
  if (settingsButton) settingsButton.innerHTML = `${sanitizeUiText('⚙️')} ${t('sidebar.settings', 'Settings')}`;

  const supportButton = document.getElementById('supportBtn');
  if (supportButton) supportButton.innerHTML = `${sanitizeUiText('📞')} ${t('sidebar.support', 'Customer Support')}`;

  const mobileMenuClose = document.getElementById('mobileMenuClose');
  if (mobileMenuClose) mobileMenuClose.setAttribute('aria-label', t('nav.closeMenu', 'Close menu'));

  const mobileMenuToggle = document.getElementById('mobileMenuToggle');
  if (mobileMenuToggle) mobileMenuToggle.setAttribute('aria-label', t('nav.openMenu', 'Open menu'));

  const settingsTitle = document.querySelector('#settingsPanel h3');
  if (settingsTitle) settingsTitle.textContent = t('settings.title', 'Settings');

  const languageLabel = document.querySelector('#settingsPanel label[data-i18n="settings.language"]');
  if (languageLabel) languageLabel.textContent = t('settings.language', 'Language');

  const themeLabel = document.querySelector('#settingsPanel label[data-i18n="settings.theme"]');
  if (themeLabel) themeLabel.textContent = t('settings.theme', 'Theme');

  const fontLabel = document.querySelector('#settingsPanel label[data-i18n="settings.fontSize"]');
  if (fontLabel) fontLabel.textContent = t('settings.fontSize', 'Font Size');

  const applyButton = document.querySelector('#settingsPanel button[onclick="applyTheme()"]');
  if (applyButton) applyButton.textContent = t('settings.apply', 'Apply');

  const chatInput = document.getElementById('msg');
  if (chatInput) chatInput.placeholder = t('chat.placeholder', 'Ask from MI AI...');

  const sendButton = document.getElementById('sendBtn');
  if (sendButton) sendButton.title = t('chat.send', 'Send');

  const signInTab = document.getElementById('signInTab');
  if (signInTab) signInTab.textContent = t('auth.signIn', 'Sign In');

  const registerTab = document.getElementById('registerTab');
  if (registerTab) registerTab.textContent = t('auth.register', 'Register');

  const resetButton = document.querySelector('#authForm button[onclick="handlePasswordReset()"]');
  if (resetButton) resetButton.textContent = t('auth.resetPassword', 'Reset password');

  const languageSelect = document.getElementById('languageSelect');
  if (languageSelect) languageSelect.value = currentLanguage;

  document.documentElement.setAttribute('lang', currentLanguage);
  document.documentElement.setAttribute('dir', RTL_LANGUAGE_CODES.has(currentLanguage) ? 'rtl' : 'ltr');
  document.body.setAttribute('dir', RTL_LANGUAGE_CODES.has(currentLanguage) ? 'rtl' : 'ltr');
  document.body.classList.toggle('rtl', RTL_LANGUAGE_CODES.has(currentLanguage));
  document.documentElement.classList.toggle('rtl', RTL_LANGUAGE_CODES.has(currentLanguage));
  document.title = t('app.title', 'MI AI');
}

async function applyLanguage(langCode, persist = true) {
  const normalized = normalizeLanguageCode(langCode);
  const localeData = await loadLocale(normalized);
  const fallback = translationCache.en || {};
  translations = { ...fallback, ...(localeData || {}) };
  currentLanguage = normalized;

  updateTranslatedUi();

  if (persist && isAuthenticated()) {
    const storageKey = getCurrentLanguageStorageKey();
    if (storageKey) {
      localStorage.setItem(storageKey, normalized);
    }

    // Auto-save language to Firestore if authenticated
    if (window.firestorePersistence && window.miFirebaseUser) {
        window.firestorePersistence.saveSettings({ language: normalized }).catch(err =>
            console.error('[Persistence] Language save error:', err)
        );
    }
  }

  if (!isAuthenticated()) {
    localStorage.removeItem('mi_current_language');
  }
}

async function changeLanguage(langCode) {
  const normalized = normalizeLanguageCode(langCode);
  await applyLanguage(normalized, true);
}

function triggerFileUpload() {
  const input = document.getElementById('fileInput');
  if (input) input.click();
}

function setAttachmentUiState(isVisible, message, progressValue) {
  const preview = document.getElementById('attachmentPreview');
  const progress = document.getElementById('attachmentProgress');
  if (!preview || !progress) return;
  if (isVisible) {
    preview.style.display = 'block';
    preview.innerHTML = message;
  } else {
    preview.style.display = 'none';
    preview.innerHTML = '';
  }
  if (progressValue !== undefined && progressValue !== null) {
    progress.style.display = 'block';
    progress.textContent = progressValue;
  } else {
    progress.style.display = 'none';
    progress.textContent = '';
  }
}

function formatFileSize(bytes) {
  if (!bytes || bytes <= 0) return '0 KB';
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = Number(bytes);
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size = size / 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(size >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function getAttachmentDisplayIcon(file) {
  const type = (file && file.type) || '';
  if (type.startsWith('image/')) return 'Ãƒ°Ã…¸â‚¬"Ã‚¼Ãƒ¯Ã‚¸Ã‚';
  if (type.includes('pdf')) return 'Ãƒ°Ã…¸â‚¬Å“â‚¬Å¾';
  if (type.includes('spreadsheet') || type.includes('excel') || type.includes('csv')) return 'Ãƒ°Ã…¸â‚¬Å“Ã… ';
  if (type.includes('presentation') || type.includes('powerpoint')) return 'Ãƒ°Ã…¸â‚¬Å“Ã‚½Ãƒ¯Ã‚¸Ã‚';
  return 'Ãƒ°Ã…¸â‚¬Å“Ã…½';
}

function renderPendingAttachmentPreview() {
  if (!pendingAttachments || !pendingAttachments.length) {
    setAttachmentUiState(false, '', '');
    return;
  }

  const items = pendingAttachments.map((file, index) => `
    <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:8px;">
      <div style="display:flex;align-items:center;gap:8px;min-width:0;">
        <span style="font-size:16px;">${getAttachmentDisplayIcon(file)}</span>
        <div style="min-width:0;">
          <div style="font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${file.name}</div>
          <div style="font-size:12px;color:#94a3b8;">${file.type || 'File'} Ãƒ¢š¬Ã‚¢ ${formatFileSize(file.size)}</div>
        </div>
      </div>
            <button type="button" onclick="removePendingAttachment(${index})" style="border:none;background:transparent;color:#fda4af;cursor:pointer;font-size:13px;">Remove</button>
        </div>
    `).join('');

  setAttachmentUiState(true, `<div style="display:flex;flex-direction:column;gap:4px;">${items}</div>`, '');
}

function handleFileSelection(event) {
  const input = event.target;
  const files = input && input.files ? Array.from(input.files) : [];
  if (!files.length) return;

  try {
    const allowedExtensions = ['.pdf', '.docx', '.doc', '.txt', '.xlsx', '.xls', '.csv', '.pptx', '.ppt', '.png', '.jpg', '.jpeg', '.webp', '.svg'];
    const allowedMimeTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword', 'text/plain', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel', 'text/csv', 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'application/vnd.ms-powerpoint', 'image/png', 'image/jpeg', 'image/webp', 'image/svg+xml'];
    const validFiles = [];
    const errors = [];
    const existingKeys = new Set((pendingAttachments || []).map((file) => `${file.name}:${file.size}:${file.type}`));

    files.forEach((file) => {
      const ext = (file.name || '').substring((file.name || '').lastIndexOf('.')).toLowerCase();
      const mimeOk = allowedMimeTypes.includes(file.type) || allowedExtensions.includes(ext);
      const dedupeKey = `${file.name}:${file.size}:${file.type}`;
      if (existingKeys.has(dedupeKey)) {
        errors.push(`${file.name} is already queued.`);
        return;
      }
      if (!mimeOk) {
        errors.push(`${file.name} is not a supported file type.`);
        return;
      }
      if (!file.size || file.size <= 0) {
        errors.push(`${file.name} is empty.`);
        return;
      }
      if (file.size > 20 * 1024 * 1024) {
        errors.push(`${file.name} is larger than 20 MB.`);
        return;
      }
      validFiles.push(file);
      existingKeys.add(dedupeKey);
    });

    pendingAttachments = pendingAttachments.concat(validFiles);
    attachmentUploadInProgress = false;
    attachmentProgress = 0;
    attachmentStatusText = '';
    renderPendingAttachmentPreview();
    if (errors.length) {
      const message = errors.slice(0, 3).join(' ');
      setAttachmentUiState(true, `<div style="color:#fda4af;">${message}</div>`, '');
    }
    input.value = '';
  } catch (error) {
    console.error('File selection failed', error);
    setAttachmentUiState(true, '<div style="color:#fda4af;">Unable to process the selected file.</div>', '');
    input.value = '';
  }
}

function removePendingAttachment(index) {
  if (typeof index === 'number' && pendingAttachments[index]) {
    pendingAttachments.splice(index, 1);
  } else {
    pendingAttachments = [];
  }
  attachmentUploadInProgress = false;
  attachmentProgress = 0;
  attachmentStatusText = '';
  renderPendingAttachmentPreview();
}

function getUploadErrorMessage(xhr, fallback) {
  try {
    const parsed = JSON.parse(xhr.responseText || '{}');
    if (parsed && parsed.error) return parsed.error;
  } catch (error) {
    console.error('Upload response parse error', error);
  }
  return fallback;
}

async function uploadSingleAttachment(file, index, total) {
  const token = localStorage.getItem('mi_supabase_token');
  if (!token) {
    throw new Error('Please sign in before uploading files.');
  }

  const formData = new FormData();
  formData.append('file', file);
  formData.append('conversation_id', currentChat);

  return await new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload', true);
    xhr.setRequestHeader('Authorization', 'Bearer ' + token);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        attachmentProgress = Math.round((event.loaded / event.total) * 100);
        attachmentStatusText = `Uploading file ${index} of ${total}... ${attachmentProgress}%`;
        setAttachmentUiState(true, `<div style="font-weight:700;">${file.name}</div><div style="font-size:12px;color:#94a3b8;">${attachmentStatusText}</div>`, attachmentStatusText);
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data = JSON.parse(xhr.responseText || '{}');
          if (data && data.attachment) {
            resolve(data.attachment);
          } else {
            reject(new Error(getUploadErrorMessage(xhr, 'Upload failed.')));
          }
        } catch (error) {
          reject(new Error(getUploadErrorMessage(xhr, 'Upload failed.')));
        }
      } else {
        reject(new Error(getUploadErrorMessage(xhr, 'Upload failed.')));
      }
    };
    xhr.onerror = () => {
      reject(new Error('Network error while uploading the file.'));
    };
    xhr.send(formData);
  });
}

async function uploadPendingAttachments() {
  if (!pendingAttachments || !pendingAttachments.length) return { attachments: [], errors: [] };
  if (!currentChat) return { attachments: [], errors: [{ name: 'chat', message: 'No active chat.' }] };

  const token = localStorage.getItem('mi_supabase_token');
  if (!token) {
    return { attachments: [], errors: [{ name: 'auth', message: 'Please sign in before uploading files.' }] };
  }

  const uploadedAttachments = [];
  const errors = [];
  const total = pendingAttachments.length;
  attachmentUploadInProgress = true;

  for (let index = 0; index < pendingAttachments.length; index += 1) {
    const file = pendingAttachments[index];
    let lastError = 'Upload failed.';
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      try {
        const attachment = await uploadSingleAttachment(file, index + 1, total);
        uploadedAttachments.push(attachment);
        lastError = null;
        break;
      } catch (error) {
        lastError = error && error.message ? error.message : 'Upload failed.';
        if (attempt < 3) {
          attachmentStatusText = `Retrying ${file.name} (${attempt}/3)...`;
          setAttachmentUiState(true, `<div style="font-weight:700;">${file.name}</div><div style="font-size:12px;color:#94a3b8;">${attachmentStatusText}</div>`, attachmentStatusText);
        }
      }
    }
    if (lastError) {
      errors.push({ name: file.name, message: lastError });
    }
  }

  attachmentUploadInProgress = false;
  pendingAttachments = [];
  renderPendingAttachmentPreview();
  return { attachments: uploadedAttachments, errors };
}

let chatBox = document.getElementById("chat");
let chatList = document.getElementById("chatList");
let input = document.getElementById("msg");
let menu = document.getElementById("menu");
let authReminder = document.getElementById("authReminder");
let loginPromptBox = null;

let guestId = localStorage.getItem("mi_guest_id");
if (!guestId) {
    guestId = "guest_" + crypto.randomUUID();
    localStorage.setItem("mi_guest_id", guestId);
}

let accountId = localStorage.getItem("mi_account");

if (!accountId) {
    accountId = guestId;
    localStorage.setItem("mi_account", accountId);
}

let chats = {};
let currentChat = null;
let selectedChat = null;
let shareOverlay = null;
let sharedChatData = null;
let replyAbortController = null;
let replyTypingTimer = null;
let replyInProgress = false;
let pendingAttachment = null;
let pendingAttachments = [];
let attachmentUploadInProgress = false;
let attachmentProgress = 0;
let attachmentStatusText = '';

function sanitizeUiText(value) {
    if (value === null || value === undefined) {
        return '';
    }

    if (typeof value !== 'string') {
        return String(value);
    }

    let text = value;

    const replacements = [
        ['\u00f0\u0178\u2018\u2018', '\ud83d\udc51'],
        ['\u00f0\u0178\u201c\u0152', '\ud83d\udcc2'],
        ['\u00f0\u0178\u2019\u00ac', '\ud83d\uddd1\ufe0f'],
        ['\u00f0\u0178\u201c\u0153', '\ud83d\udcc4']
    ];

    replacements.forEach(function (pair) {
        const corruptedText = pair[0];
        const replacementText = pair[1];

        if (corruptedText) {
            text = text.split(corruptedText).join(replacementText);
        }
    });

    return text;
}

function sanitizeStoredChatData(value) {
    if (Array.isArray(value)) {
        return value.map((item) => sanitizeStoredChatData(item));
    }

    if (value && typeof value === 'object') {
        const normalized = {};
        Object.keys(value).forEach((key) => {
            normalized[key] = sanitizeStoredChatData(value[key]);
        });
        return normalized;
    }

    if (typeof value === 'string') {
        return sanitizeUiText(value);
    }

    return value;
}

function repairDocumentText(root = document.body) {
    if (!root || !(root instanceof Node)) return;

    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
    const textNodes = [];
    let currentNode = walker.nextNode();

    while (currentNode) {
        textNodes.push(currentNode);
        currentNode = walker.nextNode();
    }

    textNodes.forEach((node) => {
        if (!node || !node.nodeValue) return;
        const repaired = sanitizeUiText(node.nodeValue);
        if (repaired !== node.nodeValue) {
            node.nodeValue = repaired;
        }
    });

    root.querySelectorAll?.('[aria-label], [title], [alt], [placeholder]').forEach((element) => {
        ['aria-label', 'title', 'alt', 'placeholder'].forEach((attribute) => {
            const attributeValue = element.getAttribute(attribute);
            if (attributeValue) {
                const repaired = sanitizeUiText(attributeValue);
                if (repaired !== attributeValue) {
                    element.setAttribute(attribute, repaired);
                }
            }
        });
    });
}

function isAuthenticated() {
    return Boolean(user && localStorage.getItem('mi_supabase_token'));
}

function getDismissedLoginPromptChats() {
    try {
        return JSON.parse(localStorage.getItem('mi_login_prompt_dismissed_chats') || '[]');
    } catch {
        return [];
    }
}

function saveDismissedLoginPromptChats(chatsList) {
    localStorage.setItem('mi_login_prompt_dismissed_chats', JSON.stringify(chatsList));
}

function getShownLoginPromptChats() {
    try {
        return JSON.parse(localStorage.getItem('mi_login_prompt_shown_chats') || '[]');
    } catch {
        return [];
    }
}

function saveShownLoginPromptChats(chatsList) {
    localStorage.setItem('mi_login_prompt_shown_chats', JSON.stringify(chatsList));
}

function markLoginPromptShown(chatId) {
    if (!chatId) return;
    const shown = getShownLoginPromptChats();
    if (!shown.includes(chatId)) {
        shown.push(chatId);
        saveShownLoginPromptChats(shown);
    }
}

function dismissLoginPrompt(chatId) {
    if (!chatId) return;
    const dismissed = getDismissedLoginPromptChats();
    if (!dismissed.includes(chatId)) {
        dismissed.push(chatId);
        saveDismissedLoginPromptChats(dismissed);
    }
    removeLoginPrompt();
}

function removeLoginPrompt() {
    if (loginPromptBox && loginPromptBox.parentNode) {
        loginPromptBox.parentNode.removeChild(loginPromptBox);
    }
    loginPromptBox = null;
}

function shouldShowLoginPrompt(chatId) {
    if (!chatId || isAuthenticated()) return false;
    const dismissed = getDismissedLoginPromptChats();
    const shown = getShownLoginPromptChats();
    return !dismissed.includes(chatId) && !shown.includes(chatId);
}

function showLoginPrompt(chatId) {
    if (!chatId || !shouldShowLoginPrompt(chatId)) return;
    removeLoginPrompt();

    const box = document.createElement('div');
    box.style.position = 'fixed';
    box.style.top = '50%';
    box.style.left = '50%';
    box.style.transform = 'translate(-50%, -50%)';
    box.style.zIndex = '9999';
    box.style.width = 'min(92vw, 360px)';
    box.style.background = 'linear-gradient(135deg, rgba(15, 23, 42, 0.98), rgba(30, 41, 59, 0.98))';
    box.style.border = '1px solid rgba(255,255,255,0.14)';
    box.style.borderRadius = '18px';
    box.style.padding = '18px 18px 16px';
    box.style.boxShadow = '0 20px 50px rgba(0, 0, 0, 0.35)';
    box.style.color = '#f8fafc';

    box.innerHTML = sanitizeUiText(`
      <button type="button" onclick="dismissLoginPrompt('${chatId}')" style="position:absolute;top:10px;right:10px;border:none;background:transparent;color:#f43f5e;font-size:20px;cursor:pointer;line-height:1;">✕</button>
      <div style="font-size:16px;font-weight:700;margin-bottom:10px;text-align:center;">${t('auth.loginPrompt.title', 'Login to unlock more')}</div>
      <div style="font-size:13px;line-height:1.5;color:#cbd5e1;text-align:center;margin-bottom:12px;">${t('auth.loginPrompt.description', 'Enjoy these benefits when you sign in:')}</div>
      <ul style="margin:0 0 12px 18px;padding:0;font-size:13px;line-height:1.7;color:#e2e8f0;">
        <li>${t('auth.loginPrompt.benefitSave', 'Save and restore your chats')}</li>
        <li>${t('auth.loginPrompt.benefitSync', 'Sync your history across devices')}</li>
        <li>${t('auth.loginPrompt.benefitPersonal', 'Get faster, more personal replies')}</li>
      </ul>
      <div style="display:flex;justify-content:center;">
        <button type="button" onclick="dismissLoginPrompt('${chatId}'); openLogin();" style="padding:8px 12px;border:none;border-radius:999px;background:linear-gradient(135deg,#1e88e5,#38bdf8);color:#fff;font-weight:700;font-size:13px;cursor:pointer;box-shadow:0 8px 18px rgba(30,136,229,0.2);">🔐 Login</button>
      </div>
    `);

    document.body.appendChild(box);
    loginPromptBox = box;
    markLoginPromptShown(chatId);
}

function maybeShowLoginPrompt(chatId) {
    if (!chatId || isAuthenticated()) return;
    const messages = chats[chatId] || [];
    const aiReplies = messages.filter((m) => m.role === 'ai').length;
    const totalMessages = messages.length;

    if (aiReplies >= 3 && totalMessages >= 4 && shouldShowLoginPrompt(chatId)) {
        showLoginPrompt(chatId);
    }
}

function getGuestStorageKey() {
    return "mi_chats_" + guestId;
}

function getAccountScopedChatStorageKey(identity) {
    const normalizedIdentity = (identity || '').trim().toLowerCase();
    return normalizedIdentity ? `mi_chats_${normalizedIdentity}` : getGuestStorageKey();
}

function getUserChatStorageKey() {
    const email = (localStorage.getItem('mi_user_email') || '').trim().toLowerCase();
    const userId = (localStorage.getItem('mi_user_id') || '').trim().toLowerCase();
    const identity = email || userId || guestId;
    return getAccountScopedChatStorageKey(identity);
}

function getActiveStorageKey() {
    return isAuthenticated() ? getUserChatStorageKey() : getGuestStorageKey();
}

function getSessionId() {
    return isAuthenticated() ? user.id : guestId;
}

function createSingleGuestChat() {
    const id = `chat_${Date.now()}`;
    chats = { [id]: [] };
    currentChat = id;
    localStorage.setItem(getGuestStorageKey(), JSON.stringify(chats));
    localStorage.setItem('last_chat', id);
    return id;
}

function resetChatStateForAuthChange() {
    chats = {};
    currentChat = null;
    selectedChat = null;
    sharedChatData = null;
    pendingAttachment = null;
    pendingAttachments = [];
    attachmentUploadInProgress = false;
    attachmentProgress = 0;
    attachmentStatusText = '';
    if (chatBox) chatBox.innerHTML = '';
    renderList();
}

function loadGuestChats() {
    let saved = localStorage.getItem(getGuestStorageKey());
    let parsed = {};
    if (saved) {
        try {
            parsed = sanitizeStoredChatData(JSON.parse(saved) || {});
        } catch {
            parsed = {};
        }
    }

    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        parsed = {};
    }

    const ids = Object.keys(parsed);
    if (ids.length === 0) {
        createSingleGuestChat();
        return;
    }

    const lastChat = localStorage.getItem('last_chat') && parsed[localStorage.getItem('last_chat')] ? localStorage.getItem('last_chat') : ids[ids.length - 1];
    chats = { [lastChat]: parsed[lastChat] || [] };
    currentChat = lastChat;
    localStorage.setItem(getGuestStorageKey(), JSON.stringify(chats));
    localStorage.setItem('last_chat', currentChat);
}

function getCurrentProfileEmail() {
    return (localStorage.getItem('mi_user_email') || '').trim().toLowerCase();
}

function getProfileStorageKey(field) {
    const email = getCurrentProfileEmail();
    return email ? `mi_profile_${field}_${email}` : null;
}

function getProfileData() {
    const email = getCurrentProfileEmail();
    return {
        name: email ? localStorage.getItem(getProfileStorageKey('name')) || '' : '',
        age: email ? localStorage.getItem(getProfileStorageKey('age')) || '' : '',
        email
    };
}

function saveProfileData(profile) {
    if (!profile) return;
    const email = getCurrentProfileEmail();
    if (!email) return;
    if (profile.name !== undefined) localStorage.setItem(`mi_profile_name_${email}`, profile.name);
    if (profile.age !== undefined) localStorage.setItem(`mi_profile_age_${email}`, profile.age);
}

function closeProfilePanel() {
    const box = document.getElementById('profilePanel');
    if (box) box.remove();
}

function openProfilePanel() {
    closeProfilePanel();
    const profile = getProfileData();
    const box = document.createElement('div');
    box.id = 'profilePanel';
    box.style.position = 'fixed';
    box.style.top = '50%';
    box.style.left = '50%';
    box.style.transform = 'translate(-50%, -50%)';
    box.style.width = 'min(92vw, 380px)';
    box.style.maxHeight = '90vh';
    box.style.overflowY = 'auto';
    box.style.background = 'linear-gradient(135deg, rgba(15,23,42,0.98), rgba(30,41,59,0.98))';
    box.style.border = '1px solid rgba(255,255,255,0.14)';
    box.style.borderRadius = '18px';
    box.style.padding = '18px';
    box.style.boxShadow = '0 24px 60px rgba(0,0,0,0.36)';
    box.style.zIndex = '10000';
    box.style.color = '#f8fafc';

    box.innerHTML = `
      <button type="button" onclick="closeProfilePanel()" style="position:absolute;top:10px;right:10px;border:none;background:transparent;color:#f43f5e;font-size:20px;cursor:pointer;line-height:1;">Ãƒ¢Ã…"â‚¬¢</button>
      <div style="font-size:18px;font-weight:700;margin-bottom:14px;">Your profile</div>
      <div style="display:flex;flex-direction:column;gap:10px;">
        <label style="font-size:13px;color:#cbd5e1;">Name</label>
        <div style="display:flex;align-items:center;gap:8px;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.08);">
          <span>Ãƒ°Ã…¸â‚¬Ëœâ‚¬¹</span>
          <input id="profileName" value="${(profile.name || '').replace(/"/g, '&quot;')}" style="width:100%;border:none;outline:none;background:transparent;color:#fff;" />
        </div>
        <label style="font-size:13px;color:#cbd5e1;">Age</label>
        <div style="display:flex;align-items:center;gap:8px;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.08);">
          <span>Ãƒ°Ã…¸Ã…½â‚¬Å¡</span>
          <input id="profileAge" value="${(profile.age || '').replace(/"/g, '&quot;')}" style="width:100%;border:none;outline:none;background:transparent;color:#fff;" />
        </div>
        <label style="font-size:13px;color:#cbd5e1;">Email</label>
        <div style="display:flex;align-items:center;gap:8px;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.08);">
          <span>Ãƒ°Ã…¸â‚¬Å“Ã‚§</span>
          <input id="profileEmail" value="${(profile.email || '').replace(/"/g, '&quot;')}" style="width:100%;border:none;outline:none;background:transparent;color:#fff;" readonly />
        </div>
      </div>
      <div style="margin-top:14px;border-top:1px solid rgba(255,255,255,0.1);padding-top:14px;display:flex;flex-direction:column;gap:10px;">
        <button type="button" onclick="saveProfileAndStay()" style="padding:10px 12px;border:none;border-radius:12px;background:linear-gradient(135deg,#1e88e5,#38bdf8);color:#fff;font-weight:700;cursor:pointer;">Save changes</button>
        <button type="button" onclick="confirmLogout()" style="padding:10px 12px;border:none;border-radius:12px;background:#ef4444;color:#fff;font-weight:700;cursor:pointer;">Logout</button>
      </div>
    `;

    document.body.appendChild(box);
    const nameInput = document.getElementById('profileName');
    const ageInput = document.getElementById('profileAge');
    if (nameInput) nameInput.addEventListener('input', () => saveProfileData({ name: nameInput.value }));
    if (ageInput) ageInput.addEventListener('input', () => saveProfileData({ age: ageInput.value }));
}

function saveProfileAndStay() {
    const nameInput = document.getElementById('profileName');
    const ageInput = document.getElementById('profileAge');
    if (nameInput) saveProfileData({ name: nameInput.value });
    if (ageInput) saveProfileData({ age: ageInput.value });
    closeProfilePanel();
}

function confirmLogout() {
    const box = document.getElementById('profilePanel');
    if (!box) return;
    box.innerHTML = sanitizeUiText(`
      <button type="button" onclick="closeProfilePanel()" style="position:absolute;top:10px;right:10px;border:none;background:transparent;color:#f43f5e;font-size:20px;cursor:pointer;line-height:1;">✕</button>
      <div style="font-size:16px;font-weight:700;margin-bottom:10px;">${t('auth.logoutConfirm.title', 'Are you sure you want to logout?')}</div>
      <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:14px;">
        <button type="button" onclick="openProfilePanel()" style="padding:8px 12px;border:none;border-radius:10px;background:rgba(255,255,255,0.12);color:#fff;font-weight:700;cursor:pointer;">${t('auth.logoutConfirm.cancel', 'Cancel')}</button>
        <button type="button" onclick="handleLogoutConfirmation()" style="padding:8px 12px;border:none;border-radius:10px;background:#ef4444;color:#fff;font-weight:700;cursor:pointer;">${t('auth.logoutConfirm.logout', 'Logout')}</button>
      </div>
    `);
}

function handleLogoutConfirmation() {
    const message = t('auth.logoutConfirm.message', 'You are about to log out. Continue?');
    const shouldLogout = window.confirm(message);
    if (shouldLogout) {
        logout();
    }
}

async function logout() {

    if (
        window.MIAccountSettings &&
        typeof window.MIAccountSettings.save === "function"
    ) {
        window.MIAccountSettings.save();
    }

    // Unsubscribe from Firestore listeners
    if (window.firestorePersistence) {
        window.firestorePersistence.unsubscribeAll();
        window.firestorePersistence.setUser(null);
    }

try {
        const auth = await initFirebase();
        await auth.signOut();
    } catch (e) {
        console.error('Logout error:', e);
    }

    // Clear all account-related localStorage
    localStorage.removeItem('mi_supabase_token');
    localStorage.removeItem('mi_user_id');
    localStorage.removeItem('mi_user_email');

    // Clear account chats from localStorage
    localStorage.removeItem('mi_chats_' + accountId);

user = null;
    accountId = guestId;
    localStorage.setItem('mi_account', accountId);

    // Reset chat state to guest state
    chats = {};
    currentChat = null;

    await applyLanguage('en', false);
    resetChatStateForAuthChange();
    createSingleGuestChat();
    save();
    renderList();
    openChat(currentChat);
    closeProfilePanel();
    updateAuthControls();
    window.dispatchEvent(new Event('mi-chat-user-changed'));
    console.log('[Persistence] Logout complete - state cleared');
}

function updateAuthControls(){
    const loginBtn = document.getElementById('loginBtn');
    const logoutBtn = document.getElementById('logoutBtn');
    const alertBox = document.getElementById('approvalAlert');
    const hasSession = Boolean(user || localStorage.getItem('mi_supabase_token'));

    if (loginBtn) {
        loginBtn.style.display = hasSession ? 'none' : 'inline-flex';
    }

    if (logoutBtn) {
        logoutBtn.style.display = hasSession ? 'inline-flex' : 'none';
    }

    if (alertBox) {
        const pending = getPendingApprovalRequests();
        alertBox.style.display = pending.length ? 'inline-flex' : 'none';
        alertBox.textContent = pending.length ? `Alert (${pending.length})` : 'Alert';
    }

    updateAuthReminder();
    updateTranslatedUi();
}

function updateAuthReminder(){
    if (authReminder) {
        authReminder.style.display = 'none';
        authReminder.innerHTML = '';
    }
}

function getSharedLinkStore() {
  try {
    const raw = localStorage.getItem('mi_shared_chat_links');
    return raw ? JSON.parse(raw) : {};
  } catch (error) {
    console.error('Unable to read shared link store', error);
    return {};
  }
}

function saveSharedLinkStore(store) {
  localStorage.setItem('mi_shared_chat_links', JSON.stringify(store));
}

function generateShortShareId() {
  const existing = getSharedLinkStore();
  let id = '';
  do {
    id = Math.random().toString(36).slice(2, 8);
  } while (existing[id]);
  return id;
}

function getSharedLinkState(sharedId) {
  try {
    const raw = localStorage.getItem(`mi_shared_link_state_${sharedId}`);
    return raw ? JSON.parse(raw) : { openCount: 0, lastOpenedAt: 0 };
  } catch (error) {
    return { openCount: 0, lastOpenedAt: 0 };
  }
}

function saveSharedLinkState(sharedId, state) {
  localStorage.setItem(`mi_shared_link_state_${sharedId}`, JSON.stringify(state));
}

function getPendingApprovalRequests() {
  try {
    const raw = localStorage.getItem('mi_shared_approval_requests');
    return raw ? JSON.parse(raw) : [];
  } catch (error) {
    return [];
  }
}

function savePendingApprovalRequests(requests) {
  localStorage.setItem('mi_shared_approval_requests', JSON.stringify(requests));
}

function getSharedChatPayloadFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const sharedValue = params.get('s') || params.get('share');
  if (!sharedValue) return null;

  const store = getSharedLinkStore();
  if (sharedValue.length <= 8 && /^[a-z0-9]+$/i.test(sharedValue)) {
    return store[sharedValue] || null;
  }

  if (sharedValue.startsWith('http')) {
    try {
      const parsedUrl = new URL(sharedValue);
      const shortId = parsedUrl.searchParams.get('s') || parsedUrl.searchParams.get('share');
      if (shortId) {
        return store[shortId] || null;
      }
    } catch (error) {
      console.error('Unable to parse shared link URL', error);
    }
  }

  try {
    const parsed = JSON.parse(decodeURIComponent(sharedValue));
    if (!parsed || !Array.isArray(parsed.messages)) return null;
    return parsed;
  } catch (error) {
    try {
      const parsed = JSON.parse(sharedValue);
      if (!parsed || !Array.isArray(parsed.messages)) return null;
      return parsed;
    } catch (fallbackError) {
      console.error('Unable to parse shared chat payload', fallbackError);
      return null;
    }
  }
}

function applySharedChatUi(permission, reason) {
  const inputField = document.getElementById('msg');
  const sendButton = document.querySelector('#inputBox button');
  const notice = document.getElementById('sharedRestrictionMessage');
  const isViewOnly = permission === 'view';

  if (inputField) inputField.disabled = isViewOnly;
  if (sendButton) sendButton.disabled = isViewOnly;
  if (notice) {
    notice.style.display = isViewOnly ? 'block' : 'none';
    notice.textContent = isViewOnly ? (reason || 'RESTRICTED BY CHAT OWNER') : '';
  }
}

function getSharedPrivacySummaryItems(payload) {
  const security = payload.security || {};
  const items = [];

  items.push(`Access: ${payload.permission === 'view' ? 'View only' : 'Can edit'}`);

  if (security.openLimitMode && security.openLimitMode !== 'no-expiry') {
    items.push(`Open limit: ${security.openLimitMode === 'custom' ? security.openLimitCustom : security.openLimitMode}`);
  }
  if (security.timeLimitUnit && security.timeLimitUnit !== 'no-expiry') {
    items.push(`Time limit: ${security.timeLimitValue || 1} ${security.timeLimitUnit}`);
  }
  if (security.password) {
    items.push('Password protected');
  }
  if (security.notification === 'on') {
    items.push('Notification enabled');
  }

  return items;
}

function showSharedPrivacyGate(payload) {
  const security = payload.security || {};
  const items = getSharedPrivacySummaryItems(payload);
  const hasSecurityControls = Boolean(
    security.password ||
    (security.openLimitMode && security.openLimitMode !== 'no-expiry') ||
    (security.timeLimitUnit && security.timeLimitUnit !== 'no-expiry') ||
    security.notification === 'on'
  );

  if (!hasSecurityControls) {
    return Promise.resolve(true);
  }

  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.id = 'sharedPrivacyGate';
    overlay.style.position = 'fixed';
    overlay.style.inset = '0';
    overlay.style.background = 'rgba(2,6,23,0.96)';
    overlay.style.backdropFilter = 'blur(10px)';
    overlay.style.display = 'flex';
    overlay.style.alignItems = 'center';
    overlay.style.justifyContent = 'center';
    overlay.style.padding = '24px';
    overlay.style.zIndex = '10004';
    overlay.style.color = '#f8fafc';

    overlay.innerHTML = sanitizeUiText(`
      <div style="width:min(92vw,480px);max-height:90vh;overflow:auto;position:relative;padding:24px 24px 84px;border-radius:24px;background:rgba(15,23,42,0.98);border:1px solid rgba(255,255,255,0.14);box-shadow:0 24px 60px rgba(0,0,0,0.36);">
        <button type="button" id="sharedGateClose" style="position:absolute;top:14px;right:14px;border:none;background:transparent;color:#f43f5e;font-size:20px;cursor:pointer;line-height:1;">✕</button>




        <div style="font-size:22px;font-weight:800;margin-bottom:8px;">Shared chat privacy</div>
        <div style="font-size:13px;color:#cbd5e1;margin-bottom:16px;">This link follows the privacy rules selected by the owner. Review them below, then continue.</div>
        <div style="display:grid;gap:8px;margin-bottom:16px;">
          ${items.length ? items.map((item) => `<div style="padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.08);font-size:14px;">${item}</div>`).join('') : '<div style="padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.08);font-size:14px;">No additional privacy controls were set.</div>'}
        </div>
        ${security.password ? `
          <label style="display:block;font-size:13px;color:#cbd5e1;margin-bottom:6px;">Password</label>
          <input id="sharedGatePassword" type="password" placeholder="Enter password" style="width:100%;padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,0.16);background:#0f172a;color:#fff;margin-bottom:8px;" />
        ` : ''}
        <div id="sharedGateError" style="min-height:16px;font-size:13px;color:#fda4af;margin-bottom:8px;"></div>
        <button id="sharedGateContinue" type="button" style="position:absolute;left:24px;right:24px;bottom:24px;padding:12px 16px;border-radius:14px;background:linear-gradient(135deg,#1e88e5,#38bdf8);color:#fff;font-weight:800;cursor:pointer;">Continue</button>
      </div>
    `;

    document.body.appendChild(overlay);

    const closeButton = document.getElementById('sharedGateClose');
    const continueButton = document.getElementById('sharedGateContinue');
    const passwordInput = document.getElementById('sharedGatePassword');
    const errorEl = document.getElementById('sharedGateError');

    const finalize = (value) => {
      if (security.password && String(value) !== String(security.password)) {
        if (errorEl) errorEl.textContent = 'Incorrect password. Please try again.';
        return false;
      }
      overlay.remove();
      resolve(true);
      return true;
    };

    if (closeButton) {
      closeButton.addEventListener('click', () => {
        overlay.remove();
        resolve(false);
      });
    }

    if (continueButton) {
      continueButton.addEventListener('click', () => {
        const value = passwordInput ? passwordInput.value : '';
        finalize(value);
      });
    }

    if (passwordInput) {
      passwordInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          finalize(passwordInput.value);
        }
      });
      passwordInput.focus();
    } else if (continueButton) {
      continueButton.focus();
    }
  });
}

function showSharedSecurityBanner(payload) {
  const notices = getSharedPrivacySummaryItems(payload);
  if (!notices.length) return;

  const banner = document.createElement('div');
  banner.style.marginBottom = '10px';
  banner.style.padding = '10px 12px';
  banner.style.borderRadius = '12px';
  banner.style.background = 'rgba(30,136,229,0.16)';
  banner.style.border = '1px solid rgba(30,136,229,0.24)';
  banner.style.fontSize = '12px';
  banner.style.color = '#dce8ff';
  banner.innerHTML = `<div style="font-weight:700;margin-bottom:4px;">Shared privacy settings</div><div>${notices.join('<br>')}</div>`;
  if (chatBox) chatBox.insertBefore(banner, chatBox.firstChild);
}

function showSharedAccessMessage(message, isError = true) {
  const notice = document.getElementById('sharedRestrictionMessage');
  if (notice) {
    notice.style.display = 'block';
    notice.textContent = message;
    notice.style.color = isError ? '#fda4af' : '#86efac';
  }
}

function blockSharedScreenshot() {
  if (document.getElementById('sharedScreenshotOverlay')) return;
  const overlay = document.createElement('div');
  overlay.id = 'sharedScreenshotOverlay';
  overlay.style.position = 'fixed';
  overlay.style.inset = '0';
  overlay.style.background = 'rgba(2,6,23,0.72)';
  overlay.style.backdropFilter = 'blur(6px)';
  overlay.style.display = 'flex';
  overlay.style.alignItems = 'center';
  overlay.style.justifyContent = 'center';
  overlay.style.zIndex = '10002';
  overlay.style.color = '#fff';
  overlay.style.fontSize = '16px';
  overlay.style.fontWeight = '700';
  overlay.innerHTML = '<div style="padding:18px 20px;border-radius:14px;background:rgba(15,23,42,0.96);border:1px solid rgba(255,255,255,0.12);">Screenshot warning enabled for this shared chat.</div>';
  document.body.appendChild(overlay);
}

function removeSharedScreenshotOverlay() {
  const overlay = document.getElementById('sharedScreenshotOverlay');
  if (overlay) overlay.remove();
}

function convertTimeValue(value, unit) {
  const amount = Number(value || 0);
  if (!amount) return 0;
  if (unit === 'hour') return amount * 3600 * 1000;
  if (unit === 'minute') return amount * 60 * 1000;
  if (unit === 'second') return amount * 1000;
  return 0;
}

function getViewerEmail() {
  return (localStorage.getItem('mi_user_email') || 'viewer@unknown').trim().toLowerCase();
}

function sendSharedNotification(payload) {
  const security = payload.security || {};
  if (security.notification !== 'on') return;
  const ownerEmail = (payload.ownerEmail || '').trim().toLowerCase();
  if (!ownerEmail) return;
  const viewerEmail = getViewerEmail();
  const time = new Date().toLocaleString();
  const subject = encodeURIComponent('MI AI shared chat opened');
  const body = encodeURIComponent(`A shared chat was opened.\nViewer email: ${viewerEmail}\nTime: ${time}`);
  window.location.href = `mailto:${ownerEmail}?subject=${subject}&body=${body}`;
}

function createApprovalRequest(payload, viewerEmail) {
  const requests = getPendingApprovalRequests();
  const existing = requests.find((item) => item.sharedId === payload.id && item.status === 'pending');
  if (existing) return;
  requests.push({
    sharedId: payload.id,
    chatId: payload.chatId,
    viewerEmail,
    requestedAt: new Date().toLocaleString(),
    status: 'pending'
  });
  savePendingApprovalRequests(requests);
  updateAuthControls();
}

function approveSharedLinkRequest(sharedId) {
  const requests = getPendingApprovalRequests();
  const match = requests.find((item) => item.sharedId === sharedId && item.status === 'pending');
  if (!match) return;
  match.status = 'approved';
  savePendingApprovalRequests(requests);
  const state = getSharedLinkState(sharedId);
  state.status = 'approved';
  saveSharedLinkState(sharedId, state);
  updateAuthControls();
}

function declineSharedLinkRequest(sharedId) {
  const requests = getPendingApprovalRequests();
  const match = requests.find((item) => item.sharedId === sharedId && item.status === 'pending');
  if (!match) return;
  match.status = 'declined';
  savePendingApprovalRequests(requests);
  const state = getSharedLinkState(sharedId);
  state.status = 'declined';
  saveSharedLinkState(sharedId, state);
  updateAuthControls();
}

function showApprovalRequestsPanel() {
  const requests = getPendingApprovalRequests().filter((item) => item.status === 'pending');
  const panel = document.getElementById('approvalRequestsPanel');
  if (panel) panel.remove();

  const box = document.createElement('div');
  box.id = 'approvalRequestsPanel';
  box.style.position = 'fixed';
  box.style.top = '50%';
  box.style.left = '50%';
  box.style.transform = 'translate(-50%, -50%)';
  box.style.width = 'min(92vw, 420px)';
  box.style.maxHeight = '80vh';
  box.style.overflowY = 'auto';
  box.style.background = 'rgba(15,23,42,0.98)';
  box.style.border = '1px solid rgba(255,255,255,0.14)';
  box.style.borderRadius = '18px';
  box.style.padding = '18px';
  box.style.zIndex = '10003';
  box.style.color = '#f8fafc';
  box.innerHTML = sanitizeUiText(`
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
      <div style="font-size:16px;font-weight:700;">Approval requests</div>
      <button type="button" onclick="this.parentElement.parentElement.remove()" style="border:none;background:transparent;color:#f43f5e;font-size:20px;cursor:pointer;line-height:1;">✕</button>




    </div>
    ${requests.length ? requests.map((req) => `
      <div style="margin-bottom:10px;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.08);">
        <div style="font-size:13px;color:#cbd5e1;">${req.viewerEmail || 'Unknown viewer'}</div>
        <div style="font-size:12px;color:#94a3b8;">${req.requestedAt || ''}</div>
        <div style="display:flex;gap:8px;margin-top:8px;">
          <button type="button" onclick="approveSharedLinkRequest('${req.sharedId}'); this.parentElement.parentElement.remove();" style="flex:1;padding:8px 10px;border:none;border-radius:10px;background:#16a34a;color:#fff;font-weight:700;cursor:pointer;">Approve</button>
          <button type="button" onclick="declineSharedLinkRequest('${req.sharedId}'); this.parentElement.parentElement.remove();" style="flex:1;padding:8px 10px;border:none;border-radius:10px;background:#ef4444;color:#fff;font-weight:700;cursor:pointer;">Decline</button>
        </div>
      </div>
    `).join('') : '<div style="font-size:13px;color:#cbd5e1;">No pending requests.</div>'}
  `;
  document.body.appendChild(box);
}

async function initSharedAccess(payload) {
  const sharedId = payload.id || payload.chatId || 'shared';
  const state = getSharedLinkState(sharedId);
  const security = payload.security || {};
  const viewerEmail = getViewerEmail();
  const ownerEmail = (payload.ownerEmail || '').trim().toLowerCase();
  const isOwner = Boolean(ownerEmail && viewerEmail && viewerEmail === ownerEmail);

  const gateAllowed = await showSharedPrivacyGate(payload);
  if (!gateAllowed) {
    showSharedAccessMessage('Access cancelled.');
    return false;
  }

  const now = Date.now();
  const openLimit = security.openLimitMode === 'custom' ? Number(security.openLimitCustom || 0) : Number(security.openLimitMode || 0);
  const timeLimitValue = Number(security.timeLimitValue || 0);
  const timeLimitUnit = security.timeLimitUnit || 'no-expiry';
  const expiresAt = timeLimitValue && timeLimitUnit !== 'no-expiry' ? (state.lastOpenedAt || state.createdAt || payload.createdAt || now) + convertTimeValue(timeLimitValue, timeLimitUnit) : null;

  if (security.openLimitMode && security.openLimitMode !== 'no-expiry' && state.openCount >= openLimit) {
    showSharedAccessMessage('This shared link has expired.');
    return false;
  }

  if (expiresAt && now >= expiresAt) {
    showSharedAccessMessage('This shared link has expired.');
    return false;
  }

  state.openCount = (state.openCount || 0) + 1;
  state.lastOpenedAt = now;
  state.status = state.status === 'approved' ? 'approved' : 'active';
  saveSharedLinkState(sharedId, state);

  if (security.notification === 'on') {
    sendSharedNotification(payload);
  }

  return true;
}

let chatLoadSequence = 0;

async function loadUserChats() {
  const token = localStorage.getItem('mi_supabase_token');
  const userId = localStorage.getItem('mi_user_id');
  const email = (localStorage.getItem('mi_user_email') || '').trim().toLowerCase();
  if (!token || !userId) {
    resetChatStateForAuthChange();
    loadGuestChats();
    save();
    renderList();
    if (currentChat) {
      openChat(currentChat);
    } else if (chatBox) {
      chatBox.innerHTML = '';
    }
    return;
  }

  const requestId = ++chatLoadSequence;
  resetChatStateForAuthChange();
  const previousCurrentChat = currentChat || localStorage.getItem('last_chat');

  try {
    const res = await fetch('/api/conversations', {
      headers: {
        Authorization: 'Bearer ' + token,
        'X-User-Id': userId,
        'X-User-Email': email,
      },
    });
    const json = await res.json();

    let loadedChats = {};
    if (requestId !== chatLoadSequence) return;

    if (res.ok && Array.isArray(json.conversations)) {
      for (const conversation of json.conversations) {
        const conversationId = conversation.id;
        const chatMessages = [];
        chatMessages.title = conversation.title || 'New chat';
        chatMessages.updatedAt = conversation.updated_at || conversation.created_at || Date.now();
        chatMessages.lastPreview = conversation.last_preview || '';
        chatMessages.messageCount = conversation.message_count || 0;
        chatMessages.attachments = [];

        try {
          const messagesRes = await fetch('/api/messages?conversation_id=' + encodeURIComponent(conversationId), {
            headers: {
              Authorization: 'Bearer ' + token,
              'X-User-Id': userId,
              'X-User-Email': email,
            },
          });
          const messagesJson = await messagesRes.json();
          if (messagesRes.ok && Array.isArray(messagesJson.messages)) {
            const mappedMessages = messagesJson.messages.map((message) => ({
              role: message.role === 'me' ? 'me' : 'ai',
              text: message.content,
              createdAt: message.created_at,
            }));
            chatMessages.splice(0, chatMessages.length, ...mappedMessages);
            chatMessages.title = conversation.title || 'New chat';
            chatMessages.updatedAt = conversation.updated_at || conversation.created_at || Date.now();
            chatMessages.lastPreview = mappedMessages[mappedMessages.length - 1]?.text || conversation.last_preview || '';
            chatMessages.messageCount = mappedMessages.length;
          }
        } catch (e) {
          // keep the conversation metadata
        }

        try {
          const attachmentsRes = await fetch('/api/conversations/' + encodeURIComponent(conversationId) + '/attachments', {
            headers: {
              Authorization: 'Bearer ' + token,
              'X-User-Id': userId,
              'X-User-Email': email,
            },
          });
          const attachmentsJson = await attachmentsRes.json();
          if (attachmentsRes.ok && Array.isArray(attachmentsJson.attachments)) {
            chatMessages.attachments = attachmentsJson.attachments;
          }
        } catch (e) {
          // ignore attachment fetch failures
        }

        loadedChats[conversationId] = chatMessages;
      }
    }

    if (requestId !== chatLoadSequence) return;
    chats = loadedChats;
    currentChat = previousCurrentChat && chats[previousCurrentChat] ? previousCurrentChat : Object.keys(chats || {})[0] || null;

    const storageKey = getUserChatStorageKey();
    localStorage.setItem(storageKey, JSON.stringify(chats));
    save();
    renderList();
    if (currentChat) {
      openChat(currentChat);
    } else if (chatBox) {
      chatBox.innerHTML = '';
    }
  } catch (e) {
    if (requestId !== chatLoadSequence) return;
    chats = {};
    currentChat = null;
    const storageKey = getUserChatStorageKey();
    const cached = localStorage.getItem(storageKey);
    if (cached) {
      try {
        const parsed = JSON.parse(cached);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          chats = sanitizeStoredChatData(parsed);
          currentChat = Object.keys(chats || {})[0] || null;
        }
      } catch {
        chats = {};
      }
    }
    save();
    renderList();
    if (currentChat) {
      openChat(currentChat);
    } else if (chatBox) {
      chatBox.innerHTML = '';
    }
  }
}

async function initChat(){

const urlParams = new URLSearchParams(window.location.search);
const verified = urlParams.get('verified');
if (verified === '1') {
    const authMessage = document.getElementById('authMessage');
    if (authMessage) {
        authMessage.textContent = 'Email verified! Your device is now trusted. Please sign in with your password.';
        authMessage.style.color = '#86efac';
    }
} else if (verified === '0') {
    const authMessage = document.getElementById('authMessage');
    if (authMessage) {
        authMessage.textContent = 'Email verification failed or link expired. Please try again.';
        authMessage.style.color = '#fda4af';
    }
}

chatBox = document.getElementById("chat");
chatList = document.getElementById("chatList");
input = document.getElementById("msg");
menu = document.getElementById("menu");
authReminder = document.getElementById("authReminder");

const sharedPayload = getSharedChatPayloadFromUrl();
if (sharedPayload) {
    /*
      The viewer is entering an isolated shared-chat session.

      Do not expose, merge or render owner/viewer account chats.
      Only sharedPayload.messages may be displayed.
    */
    window.MI_SHARED_VIEWER_MODE = true;
    window.MI_SHARED_VIEWER_PAYLOAD = sharedPayload;

    document.body.classList.add(
        'mi-shared-chat-viewer'
    );
    const previousChats = chats && typeof chats === 'object' && !Array.isArray(chats) ? chats : {};
    const previousCurrentChat = currentChat || localStorage.getItem('last_chat');
    sharedChatData = sharedPayload;
    const sharedId = sharedPayload.id || sharedPayload.chatId || 'shared_' + Date.now();
    chats = { [sharedId]: Array.isArray(sharedPayload.messages) ? sharedPayload.messages : [] };
    currentChat = sharedId;

    const allowed = await initSharedAccess(sharedPayload);
    if (!allowed) {
        sharedChatData = null;
        chats = previousChats && typeof previousChats === 'object' && !Array.isArray(previousChats) ? previousChats : {};
        currentChat = previousCurrentChat && chats[previousCurrentChat] ? previousCurrentChat : Object.keys(chats || {})[0] || null;
        applySharedChatUi('edit');
        renderList();
        if (currentChat) {
            openChat(currentChat);
        } else if (chatBox) {
            chatBox.innerHTML = '';
        }
        updateAuthControls();
        return;
    }

    showSharedSecurityBanner(sharedPayload);
    applySharedChatUi(sharedPayload.permission === 'view' ? 'view' : 'edit');
    renderList();
    openChat(currentChat);
    updateAuthControls();

    if (input) {
        input.focus();
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                if (e.shiftKey) return;
                e.preventDefault();
                send();
            }
        });
    }

    return;
}

let token = localStorage.getItem('mi_supabase_token');
let userId = localStorage.getItem('mi_user_id');
let storedEmail = localStorage.getItem('mi_user_email');

try {
    const auth = await initFirebase();
    if (typeof auth.onAuthStateChanged === 'function') {
        auth.onAuthStateChanged(async (firebaseUser) => {
            if (!firebaseUser) {
                user = null;
                localStorage.removeItem('mi_supabase_token');
                localStorage.removeItem('mi_user_id');
                localStorage.removeItem('mi_user_email');
                accountId = guestId;
                localStorage.setItem('mi_account', accountId);
                resetChatStateForAuthChange();
                loadGuestChats();
                save();
                renderList();
                if (currentChat) {
                    openChat(currentChat);
                } else if (chatBox) {
                    chatBox.innerHTML = '';
                }
                updateAuthControls();
                window.dispatchEvent(new Event('mi-chat-user-changed'));
                return;
            }

            const nextUser = { id: firebaseUser.uid, email: firebaseUser.email || null };
            const nextToken = await firebaseUser.getIdToken();
            user = nextUser;
            localStorage.setItem('mi_supabase_token', nextToken);
            localStorage.setItem('mi_user_id', firebaseUser.uid);
            localStorage.setItem('mi_user_email', firebaseUser.email || '');
            accountId = firebaseUser.uid;
            localStorage.setItem('mi_account', accountId);

            // Load user data from Firestore on login
            if (window.firestorePersistence) {
                try {
                    const { chats: firestoreChats, settings: firestoreSettings } = await window.firestorePersistence.loadUserData();

                    // Only load if there's actual data
                    if (Object.keys(firestoreChats).length > 0) {
                        chats = firestoreChats;
                        console.log('[Persistence] User chats loaded from Firestore:', Object.keys(chats).length);
                    } else {
                        await loadUserChats();
                    }

                    // Apply loaded settings
                    if (firestoreSettings.theme) {
                        localStorage.setItem('theme', firestoreSettings.theme);
                        document.documentElement.style.setProperty('--main', firestoreSettings.theme);
                    }
                    if (firestoreSettings.fontSize) {
                        const chatBoxElem = document.getElementById('chat');
                        if (chatBoxElem) {
                            chatBoxElem.style.fontSize = firestoreSettings.fontSize + 'px';
                        }
                        localStorage.setItem('mi_font_size', firestoreSettings.fontSize);
                    }
                    if (firestoreSettings.language) {
                        await applyLanguage(firestoreSettings.language, false);
                    }

                    console.log('[Persistence] User settings loaded from Firestore');
                } catch (err) {
                    console.error('[Persistence] Error loading user data on login:', err);
                    await loadUserChats();
                }
            } else {
                await loadUserChats();
            }

            updateAuthControls();
            window.dispatchEvent(new Event('mi-chat-user-changed'));
        });
    }
} catch (e) {
    console.error('Auth listener setup failed', e);
}

if (token && userId) {
    user = { id: userId, email: storedEmail || null };
    await loadUserChats();
} else {
    loadGuestChats();
}

let theme=localStorage.getItem("theme");

if(theme){
document.documentElement.style.setProperty("--main",theme);
}

if (!chats || typeof chats !== 'object' || Array.isArray(chats) || Object.keys(chats).length === 0) {
    let id="chat_"+Date.now();
    chats[id]=[];
    currentChat=id;
} else if (!currentChat || !chats[currentChat]) {
    currentChat = Object.keys(chats)[0];
}

save();
renderList();
if (currentChat) {
    openChat(currentChat);
} else if (chatBox) {
    chatBox.innerHTML = '';
}
updateAuthControls();

if (input) {
    input.focus();
    input.addEventListener("keydown", e => {
        if (e.key === "Enter") {
            if (e.shiftKey) return;
            e.preventDefault();
            send();
        }
    });
} else {
    console.warn('Chat input element not found');
}

};

/* NEW CHAT */
async function newChat(){
    removeLoginPrompt();

    /*
      A shared-link viewer page is isolated.
      Opening New Chat leaves shared mode first.
    */
    const shareParams =
        new URLSearchParams(
            window.location.search
        );

    if (
        shareParams.has("s") ||
        shareParams.has("share") ||
        document.body.classList.contains(
            "mi-shared-single-chat"
        )
    ) {
        const cleanUrl =
            window.location.origin +
            window.location.pathname;

        window.location.assign(
            cleanUrl
        );

        return;
    }

    /*
      Always add a separate chat.
      Never replace the complete chats object.
    */
    if (
        !chats ||
        typeof chats !== "object" ||
        Array.isArray(chats)
    ) {
        chats = {};
    }

    const localId =
        `chat_${Date.now()}_${Math.random()
            .toString(36)
            .slice(2, 8)}`;

    function initializeChat(chatId) {
        chats[chatId] = [];

        /*
          Arrays are objects, so these metadata properties
          remain compatible with the existing rendering code.
        */
        chats[chatId].title =
            "NEW CHAT";

        chats[chatId].name =
            "NEW CHAT";

        chats[chatId].chatName =
            "NEW CHAT";

        currentChat =
            chatId;

        window.currentChat =
            chatId;

        localStorage.setItem(
            "last_chat",
            chatId
        );

        save();
        renderList();
        openChat(chatId);

        if (
            input &&
            typeof input.focus ===
                "function"
        ) {
            input.focus();
        }

        if (
            window.MIAccountPersistence &&
            typeof window
                .MIAccountPersistence
                .save ===
                "function"
        ) {
            window
                .MIAccountPersistence
                .save();
        }

        window.dispatchEvent(
            new CustomEvent(
                "mi-new-chat-created",
                {
                    detail: {
                        chatId:
                            chatId
                    }
                }
            )
        );
    }

    /*
      Guest users also receive a separate chat.
      Existing guest chats remain unchanged.
    */
    if (!isAuthenticated()) {
        initializeChat(localId);

        localStorage.setItem(
            getGuestStorageKey(),
            JSON.stringify(chats)
        );

        return;
    }

    /*
      Create the server conversation first.
      A local chat remains available if the server request fails.
    */
    const token =
        localStorage.getItem(
            "mi_supabase_token"
        ) || "";

    const userId =
        localStorage.getItem(
            "mi_user_id"
        ) || "";

    const storedEmail =
        (
            localStorage.getItem(
                "mi_user_email"
            ) || ""
        )
            .trim()
            .toLowerCase();

    let serverId = "";

    try {
        const response =
            await fetch(
                "/api/conversations",
                {
                    method:
                        "POST",

                    headers: {
                        "Content-Type":
                            "application/json",

                        "Authorization":
                            "Bearer " +
                            token,

                        "X-Session-Id":
                            accountId ||
                            userId ||
                            "",

                        "X-User-Id":
                            userId,

                        "X-User-Email":
                            storedEmail
                    },

                    body:
                        JSON.stringify({
                            title:
                                "NEW CHAT",

                            session_id:
                                accountId ||
                                userId ||
                                guestId
                        })
                }
            );

        const result =
            await response
                .json()
                .catch(
                    function () {
                        return {};
                    }
                );

        if (
            response.ok &&
            result?.conversation?.id
        ) {
            serverId =
                String(
                    result.conversation.id
                );
        }
    }
    catch (error) {
        console.warn(
            "[MI AI] Server New Chat creation failed; using local chat.",
            error
        );
    }

    initializeChat(
        serverId ||
        localId
    );
}

/* OPEN */
function openChat(id){
removeLoginPrompt();
currentChat=id;
if (!chatBox) {
    console.error('Chat container not found');
    return;
}
chatBox.innerHTML="";
const chatData = chats[id] || [];
const attachments = Array.isArray(chatData.attachments) ? chatData.attachments : [];
if (attachments.length > 0) {
    const attachmentBox = document.createElement('div');
    attachmentBox.style.marginBottom = '12px';
    attachmentBox.innerHTML = attachments.map((attachment) => `
      <div style="margin-bottom:8px;padding:10px 12px;border:1px solid rgba(255,255,255,0.12);border-radius:12px;background:rgba(255,255,255,0.06);color:#f8fafc;">
        <div style="font-size:13px;font-weight:700;">${sanitizeUiText('📎')} ${sanitizeUiText(attachment.file_name || 'Uploaded file')}</div>
        <div style="font-size:12px;color:#94a3b8;margin-top:4px;">${sanitizeUiText(attachment.file_type || '')} ${sanitizeUiText('•')} ${(attachment.file_size / 1024 / 1024).toFixed(2)} MB</div>
      </div>
    `).join('');
    chatBox.appendChild(attachmentBox);
}
(Array.isArray(chatData) ? chatData : []).forEach(m => {
    if (m.role === 'ai') {
        appendAiMessage(chatBox, m.text);
    } else {
        let d = document.createElement("div");
        d.className = m.role;
        d.textContent = sanitizeUiText(m.text);
        chatBox.appendChild(d);
    }
});
localStorage.setItem("last_chat",id);
}

/* RENDER LIST */
function renderList(){
chatList.innerHTML="";

let ids = Object.keys(chats);

if(ids.length > 9){
    chatList.classList.add('scrollable');
    chatList.style.maxHeight='calc(100vh - 260px)';
} else {
    chatList.classList.remove('scrollable');
    chatList.style.maxHeight='none';
}


ids.sort((a,b)=>{

if(chats[a].pin && !chats[b].pin) return -1;

if(!chats[a].pin && chats[b].pin) return 1;

return 0;

});

ids.forEach(id=>{
let div=document.createElement("div");
div.className="chatItem";
div.dataset.id=id;
const visibleChatTitle = sanitizeUiText(
    String(
        chats[id]?.title ||
        chats[id]?.name ||
        chats[id]?.chatName ||
        id
    ).trim()
);

div.textContent =
        visibleChatTitle;

div.onclick=()=>openChat(id);

/* RIGHT CLICK */
div.oncontextmenu=(e)=>{

e.preventDefault();

selectedChat=id;


document.getElementById("pinOption").innerHTML =
chats[id].pin ? `${sanitizeUiText('✕')} Unpin` : `${sanitizeUiText('📌')} Pin`;


menu.style.display="block";
menu.style.left=e.pageX+"px";
menu.style.top=e.pageY+"px";

};

chatList.appendChild(div);
});
}

/* CLOSE OVERLAYS */
function closeAllOverlays(target) {
  const settingsPanel = document.getElementById("settingsPanel");
  const loginBox = document.getElementById("loginBox");
  const supportOverlay = document.getElementById("supportOverlay");

  if (menu.style.display === "block" && !menu.contains(target)) {
    menu.style.display = "none";
  }

  if (settingsPanel && settingsPanel.style.display === "block" &&
      !settingsPanel.contains(target) && target.id !== "settingsBtn") {
    settingsPanel.style.display = "none";
  }

  if (loginBox && loginBox.style.display === "block" &&
      !loginBox.contains(target) && target.id !== "loginBtn") {
    loginBox.style.display = "none";
  }

  if (supportOverlay && !supportOverlay.contains(target) && target.id !== "supportBtn") {
    supportOverlay.remove();
  }

  /*
    Share popup is intentionally excluded here.

    Native select options can be rendered outside the popup DOM.
    Therefore changing Can edit / View only must never be treated
    as an outside click.

    Share is closed only by:
    - cancelShareOverlay()
    - closeShareOverlayAfterGenerate()
  */
}

document.addEventListener("pointerdown", e => {
  const target = e.target;
  closeAllOverlays(target);
}, true);

/* RENAME */
function renameChat(){
if(!selectedChat) return;
let name=prompt("Rename chat:", chats[selectedChat]?.title || selectedChat);
if(!name) return;

const chat = chats[selectedChat];
if (chat) {
  chat.title = name;
  chat.updatedAt = Date.now();
}

const token = localStorage.getItem('mi_supabase_token');
if (token && isAuthenticated()) {
  fetch('/api/conversations/' + encodeURIComponent(selectedChat), {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: 'Bearer ' + token,
      'X-User-Id': localStorage.getItem('mi_user_id') || '',
      'X-User-Email': localStorage.getItem('mi_user_email') || '',
    },
    body: JSON.stringify({ title: name }),
  }).catch(() => {});
}

// Auto-save chat title to Firestore
if (isAuthenticated() && window.firestorePersistence && window.miFirebaseUser) {
    window.firestorePersistence.saveChat(selectedChat, { title: name }).catch(err =>
        console.error('[Persistence] Chat rename error:', err)
    );
}

save();
renderList();
menu.style.display="none";
}

/* DELETE */
function deleteChat(){
if(!selectedChat) return;
if(!confirm("Delete this chat?")) return;

const chatId = selectedChat;
const token = localStorage.getItem('mi_supabase_token');
if (token && isAuthenticated()) {
  fetch('/api/conversations/' + encodeURIComponent(chatId), {
    method: 'DELETE',
    headers: {
      Authorization: 'Bearer ' + token,
      'X-User-Id': localStorage.getItem('mi_user_id') || '',
      'X-User-Email': localStorage.getItem('mi_user_email') || '',
    },
  }).catch(() => {});
}

delete chats[chatId];

if(currentChat===chatId){
currentChat=null;
chatBox.innerHTML="";
}

// Auto-delete from Firestore
if (isAuthenticated() && window.firestorePersistence && window.miFirebaseUser) {
    try {
        const db = window.firebase.firestore();
        db.collection('users').doc(window.miFirebaseUser.uid).collection('chats').doc(chatId).delete()
            .catch(err => console.error('[Persistence] Chat delete error:', err));
    } catch (err) {
        console.error('[Persistence] Error deleting chat from Firestore:', err);
    }
}

save();
renderList();
menu.style.display="none";
}

function pinChat(){

if(!selectedChat)return;

chats[selectedChat].pin =
!chats[selectedChat].pin;

// Auto-save pin status to Firestore
if (isAuthenticated() && window.firestorePersistence && window.miFirebaseUser) {
    window.firestorePersistence.saveChat(selectedChat, { pin: chats[selectedChat].pin }).catch(err =>
        console.error('[Persistence] Chat pin error:', err)
    );
}

save();
renderList();

menu.style.display="none";

}




let shareOverlayCloseAllowed = false;

function removeShareOverlay(force = false) {
  /*
    The Share window may only close through:
    1. Cancel
    2. Successful Generate a link

    Any old dropdown, change, click, outside-click or
    translation handler calling removeShareOverlay()
    without permission is ignored.
  */
  if (!force && !shareOverlayCloseAllowed) {
    return false;
  }

  if (shareOverlay && shareOverlay.parentNode) {
    shareOverlay.parentNode.removeChild(shareOverlay);
  }

  shareOverlay = null;
  shareOverlayCloseAllowed = false;

  return true;
}

function cancelShareOverlay() {
  shareOverlayCloseAllowed = true;
  removeShareOverlay();
}

function closeShareOverlayAfterGenerate() {
  shareOverlayCloseAllowed = true;
  removeShareOverlay();
}

function showShareFeedback(message) {
  const existing = document.getElementById('shareFeedback');
  if (existing) existing.remove();

  const box = document.createElement('div');
  box.id = 'shareFeedback';
  box.style.position = 'fixed';
  box.style.left = '50%';
  box.style.bottom = '24px';
  box.style.transform = 'translateX(-50%)';
  box.style.background = 'rgba(15, 23, 42, 0.96)';
  box.style.color = '#f8fafc';
  box.style.padding = '10px 14px';
  box.style.borderRadius = '999px';
  box.style.zIndex = '10001';
  box.style.boxShadow = '0 12px 28px rgba(0,0,0,0.28)';
  box.style.fontSize = '13px';
  box.style.fontWeight = '700';
  box.textContent = message;

  document.body.appendChild(box);
  setTimeout(() => box.remove(), 1800);
}

function linkifyText(text) {
  if (!text || typeof text !== 'string') return text;

  // HTML escape helper
  const escapeHtml = (str) => {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  };

  // Track replacements to avoid double-linking
  const replacements = [];
  let processedText = text;

  // Pattern: URLs with protocols
  processedText = processedText.replace(/\b(https?|ftp):\/\/[^\s<>]+/gi, (match) => {
    let url = match.replace(/[.,;:!?\'"()\[\]]+$/g, '');
    const link = `<a href="${url}" target="_blank" rel="noopener noreferrer" class="ai-link">${escapeHtml(url)}</a>`;
    replacements.push({ original: match, replacement: link });
    return `__LINK_${replacements.length - 1}__`;
  });

  // Pattern: Email addresses
  processedText = processedText.replace(/\b([a-zA-Z0-9._%-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b/g, (match) => {
    const link = `<a href="mailto:${match}" class="ai-link">${escapeHtml(match)}</a>`;
    replacements.push({ replacement: link });
    return `__LINK_${replacements.length - 1}__`;
  });

  // Pattern: Phone numbers
  processedText = processedText.replace(/\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b/g, (match) => {
    const cleanPhone = match.replace(/[^\d+]/g, '');
    const link = `<a href="tel:${cleanPhone}" class="ai-link">${escapeHtml(match)}</a>`;
    replacements.push({ replacement: link });
    return `__LINK_${replacements.length - 1}__`;
  });

  // Pattern: WhatsApp
  processedText = processedText.replace(/wa\.me\/[^\s<>]+|(?:https?:\/\/)?whatsapp\.com\/[^\s<>]+/gi, (match) => {
    const url = match.match(/^https?:/) ? match : `https://${match}`;
    const link = `<a href="${url}" target="_blank" rel="noopener noreferrer" class="ai-link ai-whatsapp">${escapeHtml(match)}</a>`;
    replacements.push({ replacement: link });
    return `__LINK_${replacements.length - 1}__`;
  });

  // Pattern: Telegram
  processedText = processedText.replace(/t\.me\/[^\s<>]+|@[a-zA-Z0-9_]{5,}/g, (match) => {
    let url = match;
    if (match.startsWith('@')) {
      url = `https://t.me/${match.substring(1)}`;
    } else if (!match.match(/^https?:/)) {
      url = `https://${match}`;
    }
    const link = `<a href="${url}" target="_blank" rel="noopener noreferrer" class="ai-link ai-telegram">${escapeHtml(match)}</a>`;
    replacements.push({ replacement: link });
    return `__LINK_${replacements.length - 1}__`;
  });

  // Pattern: Discord
  processedText = processedText.replace(/discord\.gg\/[^\s<>]+/gi, (match) => {
    const url = match.match(/^https?:/) ? match : `https://${match}`;
    const link = `<a href="${url}" target="_blank" rel="noopener noreferrer" class="ai-link ai-discord">${escapeHtml(match)}</a>`;
    replacements.push({ replacement: link });
    return `__LINK_${replacements.length - 1}__`;
  });

  // Pattern: GitHub
  processedText = processedText.replace(/github\.com\/[a-zA-Z0-9_-]+\/[^\s<>]*/gi, (match) => {
    const url = match.match(/^https?:/) ? match : `https://${match}`;
    const link = `<a href="${url}" target="_blank" rel="noopener noreferrer" class="ai-link ai-github">${escapeHtml(match)}</a>`;
    replacements.push({ replacement: link });
    return `__LINK_${replacements.length - 1}__`;
  });

  // Escape remaining HTML and preserve newlines
  let result = escapeHtml(processedText);

  // Restore the links (they're already safe)
  replacements.forEach((repl, idx) => {
    result = result.replace(`__LINK_${idx}__`, repl.replacement);
  });

  // Preserve line breaks
  result = result.replace(/\n/g, '<br>');

  return result;
}

function isLongWritingResponse(text) {
  const value = String(text || '').trim();
  if (!value) return false;

  // Code blocks and structured formats always get the writing card
  if (value.includes('```')) return true; // Markdown code fences
  if (/^(import|from|def|class|function|const|let|var|async|return|if|for|while)\s/m.test(value)) return true; // Common code keywords
  if (/^(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP)\s/mi.test(value)) return true; // SQL
  if (/^[\s]*[{[]|^[\s]*</m.test(value)) return true; // JSON, arrays, HTML, XML
  if (/^---/m.test(value)) return true; // YAML/Markdown frontmatter

  // Markdown headers (any level)
  if (/^#{1,6}\s/m.test(value)) return true;

  // Markdown lists with multiple items (4 or more)
  const listItems = (value.match(/^[-*+]\s|^\d+\.\s/gm) || []).length;
  if (listItems >= 4) return true;

  // Multiple paragraphs (3+) with substantial length
  const paragraphs = value.split(/\n\n+/).length;
  const wordCount = value.split(/\s+/).length;
  if (paragraphs >= 3 && wordCount > 120) return true;

  // Very long responses (essay/article length)
  if (wordCount > 180) return true;

  return false;
}

function createCopyButton(text) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'aiCopyButton';
  button.title = 'Copy';
  button.innerHTML = 'Ãƒ°Ã…¸â‚¬Å“â‚¬¹';
  button.onclick = async (event) => {
    event.stopPropagation();
    await copyTextToClipboard(text || '');
    showShareFeedback('Copied!');
  };
  return button;
}

function appendAiMessage(container, text) {
  const wrap = document.createElement('div');
  wrap.className = 'ai';
  const body = document.createElement('div');
  body.className = isLongWritingResponse(text) ? 'aiWritingCard' : 'aiMessageBody';
  body.innerHTML = linkifyText(text) || '';
  wrap.appendChild(body);
  wrap.appendChild(createCopyButton(text));
  container.appendChild(wrap);
  return wrap;
}


async function copyTextToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text || '');
    return true;
  } catch (error) {
    const temp = document.createElement('textarea');
    temp.value = text || '';
    temp.setAttribute('readonly', '');
    temp.style.position = 'fixed';
    temp.style.left = '-9999px';
    document.body.appendChild(temp);
    temp.select();
    document.execCommand('copy');
    document.body.removeChild(temp);
    return true;
  }
}

async function copySharedChatAsText(chatId) {
  const chatMessages = chats[chatId] || [];
  const text = chatMessages.map((message) => {
    if (message.role === 'me') {
      return 'user -: ' + (message.text || '');
    }
    return 'MI AI-: ' + (message.text || '');
  }).join('\n\n');

  await copyTextToClipboard(text);
  showShareFeedback('Copied as text.');

}

function showLinkShareOptions(chatId) {
  const body = document.getElementById('shareOptionsBody');
  if (!body) return;

  body.innerHTML = `
    <label style="display:block;font-size:12px;margin-bottom:6px;color:#cbd5e1;">Permission</label>
    <select id="sharePermissionSelect" onchange="event.stopPropagation();" onclick="event.stopPropagation();" style="width:100%;padding:10px;border-radius:10px;border:1px solid rgba(255,255,255,0.14);background:#0f172a;color:#fff;">
      <option value="edit">Can edit</option>
      <option value="view">View only</option>
    </select>

    <div style="margin-top:12px;border-top:1px solid rgba(255,255,255,0.1);padding-top:12px;">
      <button type="button" onclick="toggleMoreSecurityPanel()" style="width:100%;padding:10px 12px;border:none;border-radius:12px;background:rgba(255,255,255,0.08);color:#fff;font-weight:700;cursor:pointer;">More security</button>



      <div id="moreSecurityPanel" style="display:none;margin-top:10px;">
        <div style="margin-bottom:10px;">
          <div style="font-size:12px;color:#cbd5e1;margin-bottom:6px;">How many times can I open it?</div>
          <select id="shareOpenLimitSelect" onchange="event.stopPropagation(); toggleCustomOpenLimitInput();" onclick="event.stopPropagation();" style="width:100%;padding:10px;border-radius:10px;border:1px solid rgba(255,255,255,0.14);background:#0f172a;color:#fff;">
            <option value="no-expiry">No Expiry</option>
            <option value="1">1</option>
            <option value="2">2</option>
            <option value="3">3</option>
            <option value="4">4</option>
            <option value="5">5</option>
            <option value="6">6</option>
            <option value="7">7</option>
            <option value="8">8</option>
            <option value="9">9</option>
            <option value="custom">Custom</option>
          </select>
          <input id="shareOpenLimitCustom" onclick="event.stopPropagation();" onchange="event.stopPropagation();" oninput="event.stopPropagation();" type="number" min="1" placeholder="Custom number" style="display:none;width:100%;margin-top:8px;padding:10px;border-radius:10px;border:1px solid rgba(255,255,255,0.14);background:#0f172a;color:#fff;" />
        </div>

        <div style="margin-bottom:10px;">
          <div style="font-size:12px;color:#cbd5e1;margin-bottom:6px;">After how many times, how many hours can it be used next time?</div>
          <div style="display:flex;gap:8px;">
            <input id="shareTimeLimitValue" onclick="event.stopPropagation();" onchange="event.stopPropagation();" oninput="event.stopPropagation();" type="number" min="1" placeholder="Value" style="flex:1;padding:10px;border-radius:10px;border:1px solid rgba(255,255,255,0.14);background:#0f172a;color:#fff;" />
            <select id="shareTimeLimitUnit" onchange="toggleTimeLimitValueInput()" style="padding:10px;border-radius:10px;border:1px solid rgba(255,255,255,0.14);background:#0f172a;color:#fff;">
              <option value="no-expiry">No Expiry</option>
              <option value="hour">Hour</option>
              <option value="minute">Minute</option>
              <option value="second">Second</option>
            </select>
          </div>
        </div>

        <div style="margin-bottom:10px;">
          <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:#cbd5e1;">
            <input id="sharePasswordEnabled" type="checkbox" onclick="event.stopPropagation();" onchange="event.stopPropagation();" />
            Password
          </label>
          <input id="sharePassword" onclick="event.stopPropagation();" onchange="event.stopPropagation();" oninput="event.stopPropagation();" type="password" placeholder="Password" style="display:none;width:100%;margin-top:8px;padding:10px;border-radius:10px;border:1px solid rgba(255,255,255,0.14);background:#0f172a;color:#fff;" />
          <input id="sharePasswordConfirm" onclick="event.stopPropagation();" onchange="event.stopPropagation();" oninput="event.stopPropagation();" type="password" placeholder="Confirm password" style="display:none;width:100%;margin-top:8px;padding:10px;border-radius:10px;border:1px solid rgba(255,255,255,0.14);background:#0f172a;color:#fff;" />
        </div>
      </div>
    </div>

    <button type="button" onclick="generateSharedChatLink('${chatId}')" style="width:100%;margin-top:12px;padding:10px 12px;border:none;border-radius:12px;background:linear-gradient(135deg,#1e88e5,#38bdf8);color:#fff;font-weight:700;cursor:pointer;">Generate a link</button>
  `;

  const passwordToggle = document.getElementById('sharePasswordEnabled');
  if (passwordToggle) {
    passwordToggle.addEventListener('change', () => {
      const password = document.getElementById('sharePassword');
      const confirm = document.getElementById('sharePasswordConfirm');
      if (password && confirm) {
        const visible = passwordToggle.checked;
        password.style.display = visible ? 'block' : 'none';
        confirm.style.display = visible ? 'block' : 'none';
      }
    });
  }
}

function toggleMoreSecurityPanel() {
  const panel = document.getElementById('moreSecurityPanel');
  if (panel) {
    panel.style.display = panel.style.display === 'block' ? 'none' : 'block';
  }
}

function toggleCustomOpenLimitInput() {
  const select = document.getElementById('shareOpenLimitSelect');
  const custom = document.getElementById('shareOpenLimitCustom');
  if (!select || !custom) return;
  custom.style.display = select.value === 'custom' ? 'block' : 'none';
}

function toggleTimeLimitValueInput() {
  const select = document.getElementById('shareTimeLimitUnit');
  const input = document.getElementById('shareTimeLimitValue');
  if (!select || !input) return;
  input.style.display = select.value === 'no-expiry' ? 'none' : 'block';
}

async function generateSharedChatLink(chatId) {
  const permissionSelect = document.getElementById('sharePermissionSelect');
  const permission = permissionSelect && permissionSelect.value === 'view' ? 'view' : 'edit';
  const openLimitSelect = document.getElementById('shareOpenLimitSelect');
  const openLimitCustom = document.getElementById('shareOpenLimitCustom');
  const timeLimitValue = document.getElementById('shareTimeLimitValue');
  const timeLimitUnit = document.getElementById('shareTimeLimitUnit');
  const passwordEnabled = document.getElementById('sharePasswordEnabled');
  const passwordField = document.getElementById('sharePassword');
  const passwordConfirmField = document.getElementById('sharePasswordConfirm');

  const openLimitMode = openLimitSelect ? openLimitSelect.value : 'no-expiry';
  const customOpenCount = openLimitCustom && openLimitCustom.value ? Number(openLimitCustom.value) : '';
  const timeLimitUnitValue = timeLimitUnit ? timeLimitUnit.value : 'no-expiry';
  const timeLimitValueNumber = timeLimitValue && timeLimitValue.value ? Number(timeLimitValue.value) : '';
  const passwordEnabledValue = Boolean(passwordEnabled && passwordEnabled.checked);
  const password = passwordEnabledValue ? (passwordField ? passwordField.value : '') : '';
  const passwordConfirm = passwordEnabledValue ? (passwordConfirmField ? passwordConfirmField.value : '') : '';

  if (passwordEnabledValue && password !== passwordConfirm) {
    showShareFeedback('Passwords do not match.');
    return;
  }

  if (openLimitMode === 'custom' && (!customOpenCount || !Number.isInteger(customOpenCount) || customOpenCount < 1)) {
    showShareFeedback('Enter a valid open count.');
    return;
  }

  if (timeLimitUnitValue !== 'no-expiry' && (!timeLimitValueNumber || !Number.isInteger(timeLimitValueNumber) || timeLimitValueNumber < 1)) {
    showShareFeedback('Enter a valid time value.');
    return;
  }

  const messages = (chats[chatId] || []).map((message) => ({ role: message.role, text: message.text }));
  const payload = {
    id: generateShortShareId(),
    chatId,
    messages,
    permission,
    ownerEmail: (localStorage.getItem('mi_user_email') || '').trim().toLowerCase(),
    createdAt: Date.now(),
    security: {
      openLimitMode,
      openLimitCustom: openLimitMode === 'custom' ? customOpenCount : '',
      timeLimitUnit: timeLimitUnitValue,
      timeLimitValue: timeLimitUnitValue === 'no-expiry' ? '' : timeLimitValueNumber,
      password: passwordEnabledValue ? password : ''
    }
  };

  const store = getSharedLinkStore();
  store[payload.id] = payload;
  saveSharedLinkStore(store);

  const shareLink = `${window.location.origin}${window.location.pathname}?s=${payload.id}`;

  await copyTextToClipboard(shareLink);
  showShareFeedback('Copied to the clipboard.');
  closeShareOverlayAfterGenerate();
}

function shareChat(){
  const chatId = selectedChat || currentChat;
  if (!chatId || !chats[chatId]) return;

  if (!isAuthenticated()) {
    showShareFeedback('Please log in to share chats.');
    openLogin();
    return;
  }
  removeShareOverlay(true);
  closeMobileMenu();

  shareOverlay = document.createElement('div');
  shareOverlay.id = 'shareOverlay';
  shareOverlay.style.position = 'fixed';
  shareOverlay.style.left = '50%';
  shareOverlay.style.top = '50%';
  shareOverlay.style.transform = 'translate(-50%, -50%)';
  shareOverlay.style.width = 'min(92vw, 320px)';
  shareOverlay.style.background = 'rgba(15,23,42,0.98)';
  shareOverlay.style.border = '1px solid rgba(255,255,255,0.14)';
  shareOverlay.style.borderRadius = '18px';
  shareOverlay.style.padding = '18px';
  shareOverlay.style.zIndex = '10000';
  shareOverlay.style.boxShadow = '0 24px 60px rgba(0,0,0,0.36)';
  shareOverlay.style.color = '#f8fafc';

  shareOverlay.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
      <div style="font-size:16px;font-weight:700;">Share chat</div>
      <button
        id="shareCancelBtn"
        type="button"
        onclick="cancelShareOverlay()"
        style="
          margin:0;
          padding:7px 12px;
          border:1px solid rgba(255,255,255,0.16);
          border-radius:999px;
          background:rgba(255,255,255,0.08);
          color:#fda4af;
          font-size:13px;
          font-weight:700;
          cursor:pointer;
          line-height:1;
        "
      >Cancel</button>
    </div>
    <div id="shareOptionsBody">
      <button type="button" onclick="copySharedChatAsText('${chatId}')" style="width:100%;padding:10px 12px;border:none;border-radius:12px;background:linear-gradient(135deg,#1e88e5,#38bdf8);color:#fff;font-weight:700;cursor:pointer;margin-bottom:10px;">Copy as a text</button>
      <button type="button" onclick="showLinkShareOptions('${chatId}')" style="width:100%;padding:10px 12px;border:none;border-radius:12px;background:rgba(255,255,255,0.1);color:#fff;font-weight:700;cursor:pointer;">Create a link</button>
    </div>
  `;

  document.body.appendChild(shareOverlay);
  menu.style.display = 'none';
}

function getBackendBaseUrl() {
  const configured = String(window.__MI_BACKEND_URL__ || '').trim();

  if (configured) {
    return configured.replace(/\/$/, '');
  }

  return window.location.origin || '';
}

function getChatApiCandidates() {
  const candidates = [];
  const baseUrl = getBackendBaseUrl();

  if (baseUrl && baseUrl !== 'null') {
    candidates.push(`${baseUrl}/api/chat`);
  }

  candidates.push('/api/chat');

  return [...new Set(candidates)];
}

function getStreamingChatApiCandidates() {
  const candidates = [];
  const baseUrl = getBackendBaseUrl();

  if (baseUrl && baseUrl !== 'null') {
    candidates.push(`${baseUrl}/api/chat/stream`);
  }

  candidates.push('/api/chat/stream');

  return [...new Set(candidates)];
}

function getApiBaseCandidates() {
  const baseUrl = getBackendBaseUrl();
  const candidates = [];
  if (baseUrl) candidates.push(baseUrl);
  return candidates.filter((v, i, a) => a.indexOf(v) === i);
}

async function fetchJsonWithFallback(path, options = {}, signal) {
  const endpoints = getApiBaseCandidates().map((base) => `${base}${path}`);
  let lastError = null;

  for (let i = 0; i < endpoints.length; i++) {
    const endpoint = endpoints[i];
    try {
      const response = await fetch(endpoint, { ...options, signal });
      if (response.ok) return response;
      const text = await response.text().catch(() => '');
      lastError = new Error(text || `Server returned ${response.status}`);
    } catch (err) {
      lastError = err;
    }
  }

  throw lastError || new Error('Unable to contact the AI server.');
}

async function fetchChatReply(payload, signal, useStreaming = false) {
  const endpoints = useStreaming ? getStreamingChatApiCandidates() : getChatApiCandidates();
  let lastError = null;

  for (let i = 0; i < endpoints.length; i++) {
    const endpoint = endpoints[i];
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal,
      });

      if (response.ok) return response;

      const text = await response.text().catch(() => '');
      lastError = new Error(text || `Server returned ${response.status}`);
    } catch (err) {
      lastError = err;
    }
  }

  throw lastError || new Error('Unable to contact the AI server.');
}

function createStreamingReplyBubble(initialText = '') {
  const d = document.createElement('div');
  d.className = 'ai';
  const contentBox = document.createElement('div');
  contentBox.className = isLongWritingResponse(initialText) ? 'aiWritingCard' : 'aiMessageBody';
  contentBox.textContent = initialText;
  d.appendChild(contentBox);
  d.appendChild(createCopyButton(initialText));
  chatBox.appendChild(d);
  scroll();
  return { container: d, contentBox };
}

function finalizeStreamingReplyBubble(contentBox, text, conversationId) {
  if (!contentBox) return;
  contentBox.innerHTML = linkifyText(text);
  contentBox.dataset.finalText = text;
  const existingText = String(text || '').trim();
  if (conversationId && chats[conversationId]) {
    chats[conversationId].push({ role: 'ai', text: existingText });
    chats[conversationId].updatedAt = Date.now();
    chats[conversationId].messageCount = (chats[conversationId].messageCount || 0) + 1;
    chats[conversationId].lastPreview = existingText;
    save();

    // Auto-save AI message to Firestore if authenticated
    if (isAuthenticated() && window.firestorePersistence && window.miFirebaseUser) {
        const messageId = `ai_msg_${Date.now()}_${Math.random()}`;
        window.firestorePersistence.saveMessage(conversationId, messageId, {
            role: 'ai',
            text: existingText
        }).catch(err => console.error('[Persistence] AI message save error:', err));
    }

    scroll();
    maybeShowLoginPrompt(conversationId);
  }
}

/* SEND */
function sendOrStop() {
  if (replyInProgress) {
    stopReply();
    return;
  }
  send();
}

async function send() {
  if (replyInProgress) return;

  if (sharedChatData && sharedChatData.permission === 'view') {
    applySharedChatUi('view');
    return;
  }

  const msg = (input && input.value || '').trim();
  if (!msg) return;

  if (!currentChat) {
    const fallbackId = `chat_${Date.now()}`;
    chats[fallbackId] = [];
    currentChat = fallbackId;
    save();
    renderList();
  }

  const conversationId = currentChat;
  const token = localStorage.getItem('mi_supabase_token');
  const userId = localStorage.getItem('mi_user_id') || '';
  const storedEmail = (localStorage.getItem('mi_user_email') || '').trim().toLowerCase();

  input.value = '';
  replyInProgress = true;
  setReplyControlState(true);

  let uploadedAttachments = [];
  let uploadErrors = [];
  try {
    const uploadResult = pendingAttachments.length ? await uploadPendingAttachments() : { attachments: [], errors: [] };
    uploadedAttachments = uploadResult.attachments || [];
    uploadErrors = uploadResult.errors || [];
    if (pendingAttachments.length && !uploadedAttachments.length) {
      replyInProgress = false;
      setReplyControlState(false);
      setAttachmentUiState(true, '<div style="color:#fda4af;">Unable to upload the selected file.</div>', '');
      return;
    }
  } catch (err) {
    replyInProgress = false;
    setReplyControlState(false);
    setAttachmentUiState(true, '<div style="color:#fda4af;">Unable to upload the selected file.</div>', '');
    console.error(err);
    return;
  }

  if (uploadedAttachments.length) {
    if (!Array.isArray(chats[conversationId].attachments)) chats[conversationId].attachments = [];
    uploadedAttachments.forEach((a) => {
      chats[conversationId].attachments = chats[conversationId].attachments.filter((i) => i.id !== a.id);
      chats[conversationId].attachments.push(a);
    });
    chats[conversationId].updatedAt = Date.now();
    save();
    pendingAttachment = null;
    renderPendingAttachmentPreview();
  }

  if (uploadErrors.length) {
    const errorSummary = uploadErrors.slice(0, 3).map((e) => `${e.name}: ${e.message}`).join(' Ãƒ¢š¬Ã‚¢ ');
    setAttachmentUiState(true, `<div style="color:#fda4af;">${errorSummary}</div>`, '');
  }

  const history = (chats[conversationId] || []).map((message) => ({ role: message.role === 'me' ? 'user' : 'assistant', content: message.text || '' }));

  const userBubble = document.createElement('div');
  userBubble.className = 'me';
  userBubble.innerText = msg;
  chatBox.appendChild(userBubble);

  chats[conversationId].push({ role: 'me', text: msg });
  chats[conversationId].updatedAt = Date.now();
  chats[conversationId].messageCount = (chats[conversationId].messageCount || 0) + 1;
  chats[conversationId].lastPreview = msg;
  save();

  // Auto-save user message to Firestore if authenticated
  if (isAuthenticated() && window.firestorePersistence && window.miFirebaseUser) {
      const messageId = `user_msg_${Date.now()}_${Math.random()}`;
      window.firestorePersistence.saveMessage(conversationId, messageId, {
          role: 'me',
          text: msg
      }).catch(err => console.error('[Persistence] User message save error:', err));
  }

  scroll();

  try {
    if (token && conversationId) {
      const headers = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token, 'X-Session-Id': accountId || userId || '', 'X-User-Id': userId || '', 'X-User-Email': storedEmail || '' };
      const messageRes = await fetchJsonWithFallback('/api/messages', { method: 'POST', headers, body: JSON.stringify({ conversation_id: conversationId, session_id: accountId || userId || '', role: 'me', content: msg, attachment_ids: uploadedAttachments.length ? uploadedAttachments.map((a) => a.id) : [], attachment_meta: uploadedAttachments.length ? uploadedAttachments.map((attachment) => ({ file_name: attachment.file_name, file_type: attachment.file_type, file_size: attachment.file_size, upload_time: attachment.upload_time, uploaded_file_url: attachment.uploaded_file_url || null })) : null }) }).catch(() => {});
      if (messageRes && messageRes.ok) {
        await fetchJsonWithFallback('/api/conversations/' + encodeURIComponent(conversationId), { method: 'PATCH', headers, body: JSON.stringify({ title: chats[conversationId].title || 'New chat', updated_at: new Date().toISOString(), last_preview: msg, message_count: chats[conversationId].messageCount || 0 }) }).catch(() => {});
      }
    }
  } catch (err) {
    console.error('Failed to save user message', err);
  }

  /* THINKING */
  const t = document.createElement('div');
  t.className = 'thinking';
  t.innerHTML = `<span class="label">MI AI</span><span class="dot"></span><span class="dot"></span><span class="dot"></span>`;
  chatBox.appendChild(t);
  scroll();

  try {
    replyAbortController = new AbortController();
    const firstTokenTimeoutId = setTimeout(() => {
      if (replyAbortController && replyInProgress) {
        replyAbortController.abort();
      }
    }, 10000);
    const overallTimeoutId = setTimeout(() => {
      if (replyAbortController && replyInProgress) {
        replyAbortController.abort();
      }
    }, 45000);

    const streamResponse = await fetchChatReply({ message: msg, history, conversation_id: conversationId, attachment_ids: uploadedAttachments.length ? uploadedAttachments.map((a) => a.id) : [] }, replyAbortController.signal, true);

    if (!streamResponse.ok) throw new Error('Server returned ' + streamResponse.status);

    const streamBubble = createStreamingReplyBubble('');
    const { contentBox } = streamBubble;
    let fullText = '';
    let buffer = '';
    const reader = streamResponse.body && streamResponse.body.getReader ? streamResponse.body.getReader() : null;

    if (!reader) {
      throw new Error('Streaming responses are not supported by this browser.');
    }

    const decoder = new TextDecoder();
    let streamCompleted = false;

    while (!streamCompleted) {
      const { value, done } = await reader.read();
      if (done) {
        streamCompleted = true;
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf('\n\n');
      while (boundary >= 0) {
        const chunk = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const lines = chunk.split('\n').map((line) => line.trim());
        const eventLine = lines.find((line) => line.startsWith('event:'));
        const dataLine = lines.find((line) => line.startsWith('data:'));
        if (!eventLine || !dataLine) {
          boundary = buffer.indexOf('\n\n');
          continue;
        }
        const eventType = eventLine.replace(/^event:\s*/, '');
        const payloadText = dataLine.replace(/^data:\s*/, '');
        try {
          const payload = JSON.parse(payloadText);
          if (eventType === 'delta' && payload.delta) {
            fullText += payload.delta;
            contentBox.textContent = fullText;
            scroll();
          }
          if (eventType === 'done' && payload.reply) {
            fullText = payload.reply || fullText;
            contentBox.textContent = fullText;
            scroll();
            streamCompleted = true;
          }
          if (eventType === 'error') {
            throw new Error(payload.error || 'Stream failed');
          }
        } catch (err) {
          console.error('Failed to parse stream payload', err);
        }
        boundary = buffer.indexOf('\n\n');
      }
      if (replyAbortController && replyAbortController.signal.aborted) {
        break;
      }
    }

    const trailingText = decoder.decode();
    if (trailingText) {
      buffer += trailingText;
    }
    if (buffer) {
      const lines = buffer.split('\n').map((line) => line.trim());
      const eventLine = lines.find((line) => line.startsWith('event:'));
      const dataLine = lines.find((line) => line.startsWith('data:'));
      if (eventLine && dataLine) {
        try {
          const payload = JSON.parse(dataLine.replace(/^data:\s*/, ''));
          if (payload.delta) {
            fullText += payload.delta;
            contentBox.textContent = fullText;
            scroll();
          }
          if (payload.reply) {
            fullText = payload.reply;
            contentBox.textContent = fullText;
            scroll();
          }
        } catch (err) {
          console.error('Failed to parse stream tail', err);
        }
      }
    }

    clearTimeout(firstTokenTimeoutId);
    clearTimeout(overallTimeoutId);
    t.remove();

    if (!fullText.trim()) {
      throw new Error('No response received');
    }

    contentBox.innerHTML = linkifyText(fullText);
    finalizeStreamingReplyBubble(contentBox, fullText, conversationId);
    replyInProgress = false; setReplyControlState(false);

    (async () => {
      try {
        if (token && conversationId) {
          const headers = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token, 'X-Session-Id': accountId || userId || '', 'X-User-Id': userId || '', 'X-User-Email': storedEmail || '' };
          const aiMessageRes = await fetchJsonWithFallback('/api/messages', { method: 'POST', headers, body: JSON.stringify({ conversation_id: conversationId, session_id: accountId || userId || '', role: 'ai', content: fullText }) });
          if (aiMessageRes && aiMessageRes.ok) {
            await fetchJsonWithFallback('/api/conversations/' + encodeURIComponent(conversationId), { method: 'PATCH', headers, body: JSON.stringify({ title: chats[conversationId].title || 'New chat', updated_at: new Date().toISOString(), last_preview: fullText, message_count: chats[conversationId].messageCount || 0 }) }).catch(() => {});
          }
        }
      } catch (e) { console.error('Failed to save AI reply', e); }
    })();
  } catch (e) {
    if (e && e.name === 'AbortError') {
      replyInProgress = false;
      setReplyControlState(false);
      const thinking = document.querySelector('.thinking'); if (thinking) thinking.remove();
      const fallbackBubble = document.createElement('div');
      fallbackBubble.className = 'ai';
      fallbackBubble.innerText = 'The AI is taking longer than expected. Please try again in a moment.';
      chatBox.appendChild(fallbackBubble);
      chats[conversationId].push({ role: 'ai', text: 'The AI is taking longer than expected. Please try again in a moment.' });
      chats[conversationId].updatedAt = Date.now(); chats[conversationId].messageCount = (chats[conversationId].messageCount || 0) + 1; chats[conversationId].lastPreview = 'The AI is taking longer than expected. Please try again in a moment.'; save(); scroll();
      return;
    }
    console.error("[MI AI] Reply request failed:", e);

    const thinking =
      document.querySelector('.thinking');

    if (thinking) {
      thinking.remove();
    }

    replyInProgress = false;
    setReplyControlState(false);

    /*
      Do not save a fake AI reply when both requests fail.
      Show the real server reason instead of the old generic message.
    */
    let serverMessage =
      String(
        e?.message ||
        "Unable to get an AI response."
      ).trim();

    try {
      const parsedError =
        JSON.parse(serverMessage);

      serverMessage =
        String(
          parsedError.error ||
          parsedError.message ||
          serverMessage
        ).trim();
    }
    catch (parseError) {
      // The error was plain text.
    }

    const errorBubble =
      document.createElement('div');

    errorBubble.className = 'ai';
    errorBubble.innerText =
      "Unable to get an answer: " +
      serverMessage;

    chatBox.appendChild(errorBubble);
    scroll();
  }
}

/* TYPE */
function type(text){
    const d = document.createElement("div");
    d.className = "ai";

    const contentBox = document.createElement("div");
    contentBox.className = isLongWritingResponse(text)
        ? "aiWritingCard"
        : "aiMessageBody";

    d.appendChild(contentBox);
    d.appendChild(createCopyButton(text));
    chatBox.appendChild(d);

    const fullText = String(text || "");
    const chunkSize = Math.max(8, Math.min(40, Math.ceil(fullText.length / 90)));
    let index = 0;
    let lastScroll = 0;

    function finishTyping(){
        contentBox.innerHTML = linkifyText(fullText);
        replyTypingTimer = null;
        replyInProgress = false;
        setReplyControlState(false);

        if (!Array.isArray(chats[currentChat])) {
            chats[currentChat] = [];
        }

        chats[currentChat].push({role:"ai", text:fullText});
        save();
        maybeShowLoginPrompt(currentChat);
        scroll();
    }

    function renderChunk(now){
        if (!replyInProgress) {
            replyTypingTimer = null;
            return;
        }

        index = Math.min(fullText.length, index + chunkSize);
        contentBox.textContent = fullText.slice(0, index);

        if (!lastScroll || now - lastScroll >= 80) {
            scroll();
            lastScroll = now;
        }

        if (index >= fullText.length) {
            finishTyping();
            return;
        }

        replyTypingTimer = requestAnimationFrame(renderChunk);
    }

    replyTypingTimer = requestAnimationFrame(renderChunk);
}

/* ADD */
function add(role,text){
let d=document.createElement("div");
d.className=role;
if (role === 'ai') {
    appendAiMessage(chatBox, text);
    return;
}
d.textContent=text;
chatBox.appendChild(d);

chats[currentChat].push({role,text});
chats[currentChat].updatedAt = Date.now();
chats[currentChat].messageCount = (chats[currentChat].messageCount || 0) + 1;
chats[currentChat].lastPreview = text;
save();

// If the user is authenticated, persist the message to the server as well
try {
    const token = localStorage.getItem('mi_supabase_token');
    const userId = localStorage.getItem('mi_user_id') || '';
    const storedEmail = (localStorage.getItem('mi_user_email') || '').trim().toLowerCase();
    if (token) {
        fetch('/api/messages', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token, 'X-Session-Id': accountId || userId || '', 'X-User-Id': userId || '', 'X-User-Email': storedEmail || '' },
            body: JSON.stringify({ conversation_id: currentChat, session_id: accountId, role: role === 'me' ? 'me' : 'ai', content: text })
        }).catch(() => {});
    }
} catch (e) {}

scroll();
}

/* SCROLL */
function scroll(){
chatBox.scrollTop=chatBox.scrollHeight;
}

async function createServerConversation() {
    const token = localStorage.getItem('mi_supabase_token');
    if (!token) return null;
    try {
        const res = await fetch('/api/conversations', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token,
                'X-User-Id': localStorage.getItem('mi_user_id') || '',
                'X-User-Email': localStorage.getItem('mi_user_email') || '',
            },
            body: JSON.stringify({ title: 'New chat', session_id: accountId }),
        });
        const json = await res.json();
        return res.ok && json.conversation ? json.conversation : null;
    } catch {
        return null;
    }
}

/* SAVE */
async function save() {

    const storageKey = getActiveStorageKey();

    if (storageKey) {
        localStorage.setItem(storageKey, JSON.stringify(chats));
    }

    if (currentChat) {
        localStorage.setItem("last_chat", currentChat);
    }

    // Save to Firestore if authenticated
    if (isAuthenticated() && window.firestorePersistence && window.miFirebaseUser) {
        try {
            // Save all chats and messages to Firestore
            for (const chatId in chats) {
                const chatData = chats[chatId];
                if (Array.isArray(chatData) && chatData.length === 0) continue; // Skip empty chats

                // Save chat metadata
                await window.firestorePersistence.saveChat(chatId, {
                    title: chatData.title || chatId,
                    pin: chatData.pin || false,
                    messageCount: chatData.length || 0
                });

                // Save each message
                chatData.forEach((msg, index) => {
                    if (msg && msg.text) {
                        const messageId = `msg_${index}_${Date.now()}`;
                        window.firestorePersistence.saveMessage(chatId, messageId, {
                            role: msg.role === 'me' ? 'me' : 'ai',
                            text: msg.text
                        }).catch(err => console.error('[Persistence] Message save error:', err));
                    }
                });
            }
            console.log('[Persistence] All chats synced to Firestore');
        } catch (err) {
            console.error('[Persistence] Error syncing chats:', err.message);
        }
    }

    // Logged-in users only
    if (!isAuthenticated()) return;

    const token = localStorage.getItem("mi_supabase_token");

    if (!token || !currentChat) return;

    try {
      localStorage.setItem("mi_chats_" + accountId, JSON.stringify(chats));
    } catch (e) {}
  }

  function persistChats() {
    save();
  }

function setReplyControlState(isActive) {
    const sendButton = document.getElementById('sendBtn');
    if (sendButton) {
        sendButton.innerHTML = isActive ? sanitizeUiText('⏹') : sanitizeUiText('➤');
        sendButton.title = isActive ? 'Stop reply' : 'Send message';
    }
}

function stopReply() {
    if (replyAbortController) {
        replyAbortController.abort();
        replyAbortController = null;
    }
    if (replyTypingTimer) {
        clearInterval(replyTypingTimer);
        replyTypingTimer = null;
    }
    if (replyInProgress) {
        replyInProgress = false;
    }
    const thinking = document.querySelector('.thinking');
    if (thinking) {
        thinking.remove();
    }
    setReplyControlState(false);
}

/* SETTINGS */
function toggleSettings(){
  closeMobileMenu();
  const s=document.getElementById("settingsPanel");
  if (s) {
    s.style.display = s.style.display === "block" ? "none" : "block";
  }
}

/* THEME */
function applyTheme(){
let c=document.getElementById("themeColor").value;
document.documentElement.style.setProperty("--main",c);
localStorage.setItem("theme",c);

// Auto-save to Firestore if authenticated
if (isAuthenticated() && window.firestorePersistence && window.miFirebaseUser) {
    window.firestorePersistence.saveSettings({ theme: c }).catch(err =>
        console.error('[Persistence] Theme save error:', err)
    );
}
}

/* FONT */
function setFont(v){
chatBox.style.fontSize=v+"px";
localStorage.setItem("mi_font_size", v);

// Auto-save to Firestore if authenticated
if (isAuthenticated() && window.firestorePersistence && window.miFirebaseUser) {
    window.firestorePersistence.saveSettings({ fontSize: parseInt(v) }).catch(err =>
        console.error('[Persistence] Font size save error:', err)
    );
}
}

/* CUSTOMER SUPPORT */

function customerSupport(){

let box=document.createElement("div");
box.id = "supportOverlay";

box.style.position="fixed";
box.style.left="50%";
box.style.top="50%";
box.style.transform="translate(-50%,-50%)";
box.style.background="rgba(17,26,43,0.95)";
box.style.backdropFilter="blur(15px)";
box.style.padding="25px";
box.style.borderRadius="20px";
box.style.zIndex="9999";
box.style.width="280px";
box.style.textAlign="center";
box.style.boxShadow="0 0 25px #ff7a18";


box.innerHTML=sanitizeUiText(`

<h3>📧 Customer Support</h3>

<p>📧 Email</p>

<button onclick="openEmail()">
REQUEST VIA EMAIL
</button>





<p>💬 WhatsApp</p>

<button onclick="openWhatsApp()">
VIA WHATSAPP
</button>


<button onclick="this.parentElement.remove()">
✕ Close
</button>

`;

document.body.appendChild(box);

}



/* EMAIL */

function openEmail(){

window.open(
"https://mail.google.com/mail/?view=cm&fs=1&to=miai.customerservice@gmail.com&su=MI%20AI%20Customer%20Support",
"_blank"
);

}



/* WHATSAPP */

function openWhatsApp(){

location.href="https://wa.me/94756390621";
}

function openLogin(){
  const box = document.getElementById('loginBox');
  if (!box) return;
  box.style.display = box.style.display === 'block' ? 'none' : 'block';
  if (box.style.display === 'block') {
    setAuthMode(authMode);
  }
  closeMobileMenu();
}

function toggleMobileMenu() {
  const sidebar = document.getElementById('sidebar');
  const backdrop = document.getElementById('mobileMenuBackdrop');
  const toggle = document.getElementById('mobileMenuToggle');
  if (!sidebar || !backdrop) return;

  const shouldOpen = !sidebar.classList.contains('mobile-open');
  sidebar.classList.toggle('mobile-open', shouldOpen);
  backdrop.classList.toggle('mobile-open', shouldOpen);
  document.body.style.overflow = shouldOpen ? 'hidden' : '';
  if (toggle) toggle.setAttribute('aria-expanded', shouldOpen ? 'true' : 'false');
}

function closeMobileMenu() {
  const sidebar = document.getElementById('sidebar');
  const backdrop = document.getElementById('mobileMenuBackdrop');
  const toggle = document.getElementById('mobileMenuToggle');
  if (!sidebar || !backdrop) return;
  sidebar.classList.remove('mobile-open');
  backdrop.classList.remove('mobile-open');
  document.body.style.overflow = '';
  if (toggle) toggle.setAttribute('aria-expanded', 'false');
}

function shouldForceMobileLayout() {
  const ua = navigator.userAgent || '';
  const platform = navigator.platform || '';
  const maxTouchPoints = navigator.maxTouchPoints || 0;
  const isTouchDevice = 'ontouchstart' in window || maxTouchPoints > 0 || window.matchMedia('(pointer: coarse)').matches;
  const isMobilePhoneUA = /(android|iphone|ipod|windows phone|mobile|opera mini|blackberry)/i.test(ua);
  const isMobilePlatform = /(android|iphone|ipod)/i.test(platform);
  const isSmallViewport = window.innerWidth <= 900 || window.screen.width <= 900 || window.innerHeight <= 900;
  const isTabletLike = /(ipad|tablet)/i.test(ua) && maxTouchPoints > 1;

  if (isMobilePhoneUA || isMobilePlatform) {
    return true;
  }

  return Boolean(isTouchDevice && isSmallViewport && !isTabletLike);
}

function applyForcedLayout() {
  const shouldUseMobile = shouldForceMobileLayout();
  document.body.classList.toggle('force-mobile-layout', shouldUseMobile);
  document.documentElement.classList.toggle('force-mobile-layout', shouldUseMobile);
  if (!shouldUseMobile) {
    closeMobileMenu();
  }
}


(function () {
    "use strict";

    let miStartupStarted = false;

    async function miStartApplication() {
        if (miStartupStarted) {
            return;
        }

        miStartupStarted = true;

        try {
            applyForcedLayout();
        } catch (error) {
            console.error("[MI AI] Layout startup failed:", error);
        }

        try {
            populateLanguageSelector();
        } catch (error) {
            console.error("[MI AI] Language selector startup failed:", error);
        }

        try {
            await applyLanguage("en", false);
        } catch (error) {
            console.error("[MI AI] Language startup failed:", error);
        }

        try {
            await initChat();
        } catch (error) {
            console.error("[MI AI] Chat startup failed:", error);
        }

        document.documentElement.classList.remove(
            "loading",
            "is-loading",
            "app-loading",
            "mi-app-booting",
            "mi-smooth-loading"
        );

        if (document.body) {
            document.body.classList.remove(
                "loading",
                "is-loading",
                "app-loading",
                "mi-app-booting",
                "mi-smooth-loading"
            );

            document.body.removeAttribute("aria-busy");
        }

        window.dispatchEvent(
            new CustomEvent("mi-ai-startup-complete")
        );
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            miStartApplication,
            { once: true }
        );
    } else {
        miStartApplication();
    }

    window.setTimeout(miStartApplication, 1500);
})();


window.addEventListener('beforeunload', persistChats);
window.addEventListener('pagehide', persistChats);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    persistChats();
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    closeMobileMenu();
  }
});

function setAuthMode(mode) {
  authMode = mode;
  const signInTab = document.getElementById('signInTab');
  const registerTab = document.getElementById('registerTab');
  const form = document.getElementById('authForm');
  const message = document.getElementById('authMessage');
  const signInText = t('auth.signIn', 'Sign In');
  const registerText = t('auth.register', 'Register');
  const fullNamePlaceholder = t('auth.fullName', 'Full Name');
  const agePlaceholder = t('auth.age', 'Age');
  const emailPlaceholder = t('auth.emailAddress', 'Email Address');
  const newPasswordPlaceholder = t('auth.newPassword', 'New Password');
  const confirmPasswordPlaceholder = t('auth.confirmPassword', 'Confirm Password');
  const loginEmailPlaceholder = t('auth.email', 'Email');
  const loginPasswordPlaceholder = t('auth.password', 'Password');
  const resetPasswordText = t('auth.resetPassword', 'Reset password');
  const registerButtonText = t('auth.register', 'Register');
  const signInButtonText = t('auth.signIn', 'Sign In');

  if (signInTab && registerTab) {
    signInTab.style.background = mode === 'signin' ? '#38bdf8' : 'rgba(255,255,255,0.08)';
    signInTab.style.color = mode === 'signin' ? '#0f172a' : '#cbd5e1';
    registerTab.style.background = mode === 'register' ? '#38bdf8' : 'rgba(255,255,255,0.08)';
    registerTab.style.color = mode === 'register' ? '#0f172a' : '#cbd5e1';
    signInTab.textContent = signInText;
    registerTab.textContent = registerText;
  }

  if (!form) return;
  if (message) message.textContent = '';

  if (mode === 'register') {
    form.innerHTML = `
      <div style="margin-bottom:12px;">
        <input id="fullName" placeholder="${fullNamePlaceholder}" style="width:100%;padding:10px;margin:5px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:#fff;" />
        <input id="age" type="number" placeholder="${agePlaceholder}" style="width:100%;padding:10px;margin:5px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:#fff;" />
        <input id="registerEmail" type="email" placeholder="${emailPlaceholder}" style="width:100%;padding:10px;margin:5px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:#fff;" />
        <input id="registerPassword" type="password" placeholder="${newPasswordPlaceholder}" style="width:100%;padding:10px;margin:5px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:#fff;" />
        <input id="confirmPassword" type="password" placeholder="${confirmPasswordPlaceholder}" style="width:100%;padding:10px;margin:5px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:#fff;" />
      </div>
      <button onclick="handleRegister()" style="width:100%;padding:12px;border:none;border-radius:14px;background:#38bdf8;color:#0f172a;font-weight:700;">${registerButtonText}</button>
    `;
  } else {
    form.innerHTML = `
      <div style="margin-bottom:12px;">
        <input id="loginEmail" type="email" placeholder="${loginEmailPlaceholder}" style="width:100%;padding:10px;margin:5px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:#fff;" />
        <input id="loginPassword" type="password" placeholder="${loginPasswordPlaceholder}" style="width:100%;padding:10px;margin:5px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:#fff;" />
        <div style="text-align:right;margin-top:4px;">
          <button type="button" onclick="handlePasswordReset()" style="background:none;border:none;color:#7dd3fc;padding:0;font-size:12px;cursor:pointer;">${resetPasswordText}</button>
        </div>
      </div>
      <button onclick="handleSignIn()" style="width:100%;padding:12px;border:none;border-radius:14px;background:#38bdf8;color:#0f172a;font-weight:700;">${signInButtonText}</button>
    `;
  }

  updateTranslatedUi();
}

function handleSignIn() {
    loginEmail();
}

function handleRegister() {
    registerEmail();
}

async function handlePasswordReset() {
  const email = document.getElementById('loginEmail')?.value.trim().toLowerCase();
  if (!email) {
    setAuthMessage(t('auth.reset.enterEmail', 'Please enter your email address first.'), true);
    return;
  }

  try {
    const auth = await initFirebase();
    await auth.sendPasswordResetEmail(email, {
      url: window.location.origin || window.location.href,
    });
    document.getElementById('loginPassword').value = '';
    setAuthMessage(t('auth.reset.sent', 'A password reset email has been sent. Open it and choose a new password.'), false);
  } catch (error) {
    const message = error?.message || t('auth.reset.failed', 'Unable to send the reset email.');
    setAuthMessage(message, true);
  }
}

function setAuthMessage(text, isError = true) {
  const message = document.getElementById('authMessage');
  if (!message) return;
  message.textContent = text;
  message.style.color = isError ? '#fda4af' : '#86efac';
}

function validateRegisterForm() {
  const fullName = document.getElementById('fullName')?.value.trim() || '';
  const ageValue = document.getElementById('age')?.value.trim() || '';
  const email = document.getElementById('registerEmail')?.value.trim() || '';
  const password = document.getElementById('registerPassword')?.value || '';
  const confirmPassword = document.getElementById('confirmPassword')?.value || '';

  if (!fullName) return t('auth.validation.fullName', 'Full Name cannot be empty.');
  if (!ageValue) return t('auth.validation.ageRequired', 'Age is required.');
  const age = Number(ageValue);
  if (!Number.isInteger(age) || 100 < age || age < 1) return t('auth.validation.ageInvalid', 'Age must be a valid number.');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return t('auth.validation.email', 'Please enter a valid email address.');
  if (!password) return t('auth.validation.password', 'Password cannot be empty.');
  if (!confirmPassword) return t('auth.validation.confirmPassword', 'Confirm Password cannot be empty.');
  if (password !== confirmPassword) return t('auth.validation.passwordMismatch', 'Passwords do not match.');
  return '';
}

async function registerEmail() {
  setAuthMessage('');
  const validation = validateRegisterForm();
  if (validation) {
    setAuthMessage(validation, true);
    return;
  }

  const fullName = document.getElementById('fullName')?.value.trim();
  const age = Number(document.getElementById('age')?.value.trim());
  const email = document.getElementById('registerEmail')?.value.trim().toLowerCase();
  const password = document.getElementById('registerPassword')?.value;

  try {
    const auth = await initFirebase();

    // Create Firebase user
    const result = await auth.createUserWithEmailAndPassword(email, password);
    const firebaseUser = result.user;

    // Send verification email
    await firebaseUser.sendEmailVerification();

    // Sign out the user immediately
    await auth.signOut();

    // Clear any stored auth data
    user = null;
    localStorage.removeItem('mi_supabase_token');
    localStorage.removeItem('mi_user_id');
    localStorage.removeItem('mi_user_email');

    // Show success message
    setAuthMessage(t('auth.registerSuccess', 'Registration successful! A verification email has been sent. Please check your spam folder or inbox and verify your email before signing in.'), false);

    // Switch to sign in mode after a brief delay
    setTimeout(() => {
      setAuthMode('signin');
    }, 2000);
  } catch (error) {
    const message = error?.message || 'Authentication failed.';
    const normalized = String(message || '').toLowerCase();
    const duplicateMessage = 'YOUR ACCOUNT WAS ALREADY REGISTERED BY GOOGLE.SO GO TO SIGN IN AND CREATE NEW PASSWORD AND CONFIRM ACCOUNT.';
    const invalidCredentialMessage = 'INVALID EMAIL OR PASSWORD. TRY AGAIN.';

    if (normalized.includes('email-already-in-use') || normalized.includes('already in use')) {
      setAuthMessage(t('auth.errors.alreadyRegistered', duplicateMessage), true);
    } else if (normalized.includes('invalid-credential') || normalized.includes('invalid email') || normalized.includes('wrong-password')) {
      setAuthMessage(t('auth.errors.invalidCredentials', invalidCredentialMessage), true);
    } else {
      setAuthMessage(message, true);
    }
  }
}

async function loginEmail() {
  setAuthMessage('');

  const email = document.getElementById('loginEmail').value.trim().toLowerCase();
  const password = document.getElementById('loginPassword').value;

  if (!email || !password) {
    setAuthMessage(t('auth.validation.signInRequired', 'Please enter your email and password.'));
    return;
  }

  try {
    const auth = await initFirebase();

    // Sign in with Firebase
    const result = await auth.signInWithEmailAndPassword(email, password);
    const firebaseUser = result.user;

    // Check if email is verified
    if (!firebaseUser.emailVerified) {
      // Email not verified - send verification email and sign out
      await firebaseUser.sendEmailVerification();
      await auth.signOut();

      // Clear any stored auth data
      user = null;
      localStorage.removeItem('mi_supabase_token');
      localStorage.removeItem('mi_user_id');
      localStorage.removeItem('mi_user_email');

      setAuthMessage(t('auth.unverifiedEmail', 'Your email is not verified. A new verification email has been sent. Please verify your email first. Please check your spam folder or inbox.'), true);
      return;
    }

    // Email is verified - continue with login
    user = {
      id: firebaseUser.uid,
      email: firebaseUser.email
    };

    const idToken = await firebaseUser.getIdToken();
    localStorage.setItem('mi_supabase_token', idToken);
    localStorage.setItem('mi_user_id', firebaseUser.uid);
    localStorage.setItem('mi_user_email', firebaseUser.email || '');
    window.dispatchEvent(new Event('mi-chat-user-changed'));

    await applyLanguage(getStoredLanguageCode(), false);
    updateAuthControls();
    const loginBox = document.getElementById('loginBox');
    if (loginBox) loginBox.style.display = 'none';
    setAuthMessage(t('auth.signInSuccess', 'Signed in successfully.'), false);

    window.dispatchEvent(
      new CustomEvent(
        'mi-login-success',
        {
          detail: {
            email: firebaseUser.email || '',
            user: firebaseUser
          }
        }
      )
    );
await loadUserChats();
  } catch (err) {
    const message = err?.message || 'Authentication failed.';
    const normalized = String(message || '').toLowerCase();
    const invalidCredentialMessage = 'INVALID EMAIL OR PASSWORD. TRY AGAIN.';

    if (normalized.includes('invalid-credential') || normalized.includes('invalid email') || normalized.includes('wrong-password')) {
      setAuthMessage(t('auth.errors.invalidCredentials', invalidCredentialMessage), true);
    } else {
      setAuthMessage(message, true);
    }
  }
}

