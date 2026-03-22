// Service worker, handles popup actions and capture state.
// Response bodies live in chrome.storage.session; small status metadata lives in chrome.storage.local.

const MSG = {
  ENSURE_NEW_POSTS_SORT: 'ensure_new_posts_sort',
  GET_STATE: 'get_state',
  GET_GROUPS: 'get_groups',
  SAVE_GROUPS: 'save_groups',
  OPEN_GROUPS: 'open_groups',
  QUOTA_EXCEEDED: 'quota_exceeded',
  SET_CAPTURING: 'set_capturing',
  DOWNLOAD: 'download',
  CLEAR: 'clear',
  SET_DOWNLOAD_CONFIG: 'set_download_config',
};

const STORE = {
  CAPTURING: 'fbgc_capturing',
  RESPONSES: 'fbgc_responses',
  NEXT_SEQ: 'fbgc_next_seq',
};

const META = {
  QUOTA_EXCEEDED: 'fbgc_quota_exceeded',
  UNSAVED_RESPONSES: 'fbgc_unsaved_responses',
  LAST_ERROR: 'fbgc_last_error',
  DOWNLOAD_DIR: 'fbgc_download_dir',
  GROUP_URLS: 'fbgc_group_urls',
};

const DEFAULT_DOWNLOAD_DIR = 'burning-man-matchbot/data/raw/facebook';
const TAB_LOAD_TIMEOUT_MS = 20000;

const log = (...args) => console.info('FBGC[background]:', ...args);
const warn = (...args) => console.warn('FBGC[background]:', ...args);
const errorLog = (...args) => console.error('FBGC[background]:', ...args);

async function ensureStorageAccess() {
  if (chrome.storage?.session?.setAccessLevel) {
    await chrome.storage.session.setAccessLevel({
      accessLevel: 'TRUSTED_AND_UNTRUSTED_CONTEXTS',
    });
    log('Enabled session storage access for content scripts');
  }
}

async function resetMeta() {
  await chrome.storage.local.set({
    [META.QUOTA_EXCEEDED]: false,
    [META.UNSAVED_RESPONSES]: 0,
    [META.LAST_ERROR]: '',
  });
}

async function resetSession() {
  await chrome.storage.session.set({
    [STORE.CAPTURING]: false,
    [STORE.RESPONSES]: [],
    [STORE.NEXT_SEQ]: 1,
  });
}

async function ensureDefaults() {
  const sessionState = await chrome.storage.session.get([
    STORE.CAPTURING,
    STORE.RESPONSES,
    STORE.NEXT_SEQ,
  ]);
  const localState = await chrome.storage.local.get([
    META.QUOTA_EXCEEDED,
    META.UNSAVED_RESPONSES,
    META.LAST_ERROR,
    META.DOWNLOAD_DIR,
    META.GROUP_URLS,
  ]);

  const sessionDefaults = {};
  if (typeof sessionState[STORE.CAPTURING] !== 'boolean') {
    sessionDefaults[STORE.CAPTURING] = false;
  }
  if (!Array.isArray(sessionState[STORE.RESPONSES])) {
    sessionDefaults[STORE.RESPONSES] = [];
  }
  if (!Number.isFinite(sessionState[STORE.NEXT_SEQ])) {
    const existing = Array.isArray(sessionState[STORE.RESPONSES]) ? sessionState[STORE.RESPONSES] : [];
    sessionDefaults[STORE.NEXT_SEQ] = existing.length + 1;
  }
  if (Object.keys(sessionDefaults).length > 0) {
    await chrome.storage.session.set(sessionDefaults);
  }

  const metaDefaults = {};
  if (typeof localState[META.QUOTA_EXCEEDED] !== 'boolean') {
    metaDefaults[META.QUOTA_EXCEEDED] = false;
  }
  if (!Number.isFinite(localState[META.UNSAVED_RESPONSES])) {
    metaDefaults[META.UNSAVED_RESPONSES] = 0;
  }
  if (typeof localState[META.LAST_ERROR] !== 'string') {
    metaDefaults[META.LAST_ERROR] = '';
  }
  if (typeof localState[META.DOWNLOAD_DIR] !== 'string' || !localState[META.DOWNLOAD_DIR].trim()) {
    metaDefaults[META.DOWNLOAD_DIR] = DEFAULT_DOWNLOAD_DIR;
  }
  if (!Array.isArray(localState[META.GROUP_URLS])) {
    metaDefaults[META.GROUP_URLS] = [];
  }
  if (Object.keys(metaDefaults).length > 0) {
    await chrome.storage.local.set(metaDefaults);
  }
}

async function initializeState() {
  await ensureStorageAccess();
  await ensureDefaults();
  log('Background state initialized');
}

function sanitizePathSegment(value) {
  return String(value ?? '')
    .toLowerCase()
    .replace(/https?:\/\//g, '')
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 80);
}

function inferGroupSlug(tabInfo) {
  const url = String(tabInfo?.url ?? '');
  const title = String(tabInfo?.title ?? '');

  const groupsMatch = url.match(/facebook\.com\/groups\/([^/?#]+)/i);
  if (groupsMatch?.[1]) {
    return sanitizePathSegment(groupsMatch[1]);
  }

  const cleanedTitle = title
    .replace(/\s*\|\s*Facebook\s*$/i, '')
    .replace(/\s*-\s*Facebook\s*$/i, '')
    .trim();
  const titleSlug = sanitizePathSegment(cleanedTitle);
  if (titleSlug) {
    return titleSlug;
  }

  return 'facebook-group';
}

function sanitizeRelativeDir(value) {
  const normalized = String(value ?? '')
    .replace(/\\/g, '/')
    .replace(/^\/+/, '')
    .split('/')
    .map((segment) => sanitizePathSegment(segment))
    .filter(Boolean)
    .join('/');
  return normalized || DEFAULT_DOWNLOAD_DIR;
}

function normalizeGroupUrl(value) {
  const raw = String(value ?? '').trim();
  if (!raw) {
    return null;
  }

  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return null;
  }

  if (!/(^|\.)facebook\.com$/i.test(parsed.hostname)) {
    return null;
  }

  const match = parsed.pathname.match(/^\/groups\/([^/?#]+)/i);
  if (!match?.[1]) {
    return null;
  }

  return `https://www.facebook.com/groups/${match[1]}/`;
}

function normalizeGroupUrlList(values) {
  const saved = [];
  const seen = new Set();
  let invalidCount = 0;
  let duplicateCount = 0;

  for (const value of values) {
    const normalized = normalizeGroupUrl(value);
    if (!normalized) {
      invalidCount += 1;
      continue;
    }
    if (seen.has(normalized)) {
      duplicateCount += 1;
      continue;
    }
    seen.add(normalized);
    saved.push(normalized);
  }

  return {
    saved,
    invalidCount,
    duplicateCount,
  };
}

function getCurrentWindowId() {
  return new Promise((resolve, reject) => {
    chrome.windows.getCurrent((window) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve(window?.id);
    });
  });
}

function createTab(url, windowId) {
  return new Promise((resolve, reject) => {
    chrome.tabs.create({url, active: false, windowId}, (tab) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve(tab);
    });
  });
}

function waitForTabComplete(tabId, timeoutMs = TAB_LOAD_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(handleUpdated);
      reject(new Error('Timed out waiting for the group tab to finish loading.'));
    }, timeoutMs);

    function handleUpdated(updatedTabId, changeInfo) {
      if (updatedTabId !== tabId || changeInfo.status !== 'complete') {
        return;
      }
      clearTimeout(timeoutId);
      chrome.tabs.onUpdated.removeListener(handleUpdated);
      resolve();
    }

    chrome.tabs.get(tabId, (tab) => {
      if (chrome.runtime.lastError) {
        clearTimeout(timeoutId);
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (tab?.status === 'complete') {
        clearTimeout(timeoutId);
        resolve();
        return;
      }
      chrome.tabs.onUpdated.addListener(handleUpdated);
    });
  });
}

function sendTabMessage(tabId, message) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, message, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve(response);
    });
  });
}

async function prepareGroupTab(url, windowId) {
  const tab = await createTab(url, windowId);
  const result = {
    url,
    tabId: tab?.id ?? null,
    opened: true,
    prepared: false,
    error: '',
  };

  try {
    if (!tab?.id) {
      throw new Error('Chrome created the tab without an id.');
    }
    await waitForTabComplete(tab.id);
    const prep = await sendTabMessage(tab.id, {type: MSG.ENSURE_NEW_POSTS_SORT});
    if (!prep?.ok) {
      throw new Error(prep?.error || 'Failed to set the feed sort to New posts.');
    }
    result.prepared = true;
  } catch (err) {
    result.error = String(err?.message ?? err);
  }

  return result;
}

function buildFilename(tabInfo, downloadDir) {
  const iso = new Date().toISOString().replace(/[:]/g, '-');
  const groupSlug = inferGroupSlug(tabInfo);
  const baseDir = sanitizeRelativeDir(downloadDir);
  return `${baseDir}/${groupSlug}_fb_posts_${iso}.json`;
}

function buildDownloadUrl(payload) {
  if (typeof URL.createObjectURL === 'function') {
    const blob = new Blob([payload], {type: 'application/json'});
    return {
      url: URL.createObjectURL(blob),
      revoke: true,
    };
  }

  return {
    url: `data:application/json;charset=utf-8,${encodeURIComponent(payload)}`,
    revoke: false,
  };
}

chrome.runtime.onInstalled.addListener(() => {
  void initializeState();
});

chrome.runtime.onStartup.addListener(() => {
  void initializeState();
});

void ensureStorageAccess();

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  switch (msg.type) {
    case MSG.GET_STATE:
      void (async () => {
        const [sessionState, metaState] = await Promise.all([
          chrome.storage.session.get([STORE.CAPTURING, STORE.RESPONSES]),
          chrome.storage.local.get([
            META.QUOTA_EXCEEDED,
            META.UNSAVED_RESPONSES,
            META.LAST_ERROR,
            META.GROUP_URLS,
          ]),
        ]);
        const responses = sessionState[STORE.RESPONSES] ?? [];
        const bytesUsed = JSON.stringify(responses).length;
        sendResponse({
          capturing: !!sessionState[STORE.CAPTURING],
          count: responses.length,
          bytesUsed,
          quotaExceeded: !!metaState[META.QUOTA_EXCEEDED],
          unsavedResponses: metaState[META.UNSAVED_RESPONSES] ?? 0,
          lastError: metaState[META.LAST_ERROR] ?? '',
          downloadDir: metaState[META.DOWNLOAD_DIR] ?? DEFAULT_DOWNLOAD_DIR,
          groupUrls: metaState[META.GROUP_URLS] ?? [],
        });
      })();
      return true;

    case MSG.GET_GROUPS:
      void (async () => {
        const state = await chrome.storage.local.get(META.GROUP_URLS);
        sendResponse({
          ok: true,
          groupUrls: state[META.GROUP_URLS] ?? [],
        });
      })();
      return true;

    case MSG.SAVE_GROUPS:
      void (async () => {
        const normalized = normalizeGroupUrlList(msg.groupUrls ?? []);
        await chrome.storage.local.set({
          [META.GROUP_URLS]: normalized.saved,
        });
        sendResponse({
          ok: true,
          groupUrls: normalized.saved,
          savedCount: normalized.saved.length,
          invalidCount: normalized.invalidCount,
          duplicateCount: normalized.duplicateCount,
        });
      })();
      return true;

    case MSG.OPEN_GROUPS:
      void (async () => {
        try {
          const state = await chrome.storage.local.get(META.GROUP_URLS);
          const normalized = normalizeGroupUrlList(state[META.GROUP_URLS] ?? []);
          const groupUrls = normalized.saved;
          if (groupUrls.length === 0) {
            sendResponse({
              ok: false,
              error: 'No saved Facebook group URLs. Save at least one group first.',
            });
            return;
          }

          const windowId = await getCurrentWindowId();
          const results = await Promise.all(groupUrls.map((url) => prepareGroupTab(url, windowId)));
          const preparedFailures = results.filter((result) => !result.prepared).length;
          sendResponse({
            ok: true,
            groupUrls,
            results,
            opened: results.filter((result) => result.opened).length,
            prepared: results.filter((result) => result.prepared).length,
            failed: preparedFailures,
            skipped: 0,
            invalidCount: normalized.invalidCount,
            duplicateCount: normalized.duplicateCount,
          });
        } catch (err) {
          sendResponse({
            ok: false,
            error: String(err?.message ?? err),
          });
        }
      })();
      return true;

    case MSG.QUOTA_EXCEEDED:
      void (async () => {
        const current = await chrome.storage.local.get(META.UNSAVED_RESPONSES);
        await chrome.storage.session.set({[STORE.CAPTURING]: false});
        await chrome.storage.local.set({
          [META.QUOTA_EXCEEDED]: true,
          [META.UNSAVED_RESPONSES]:
            (current[META.UNSAVED_RESPONSES] ?? 0) + (msg.unsavedCount ?? 0),
          [META.LAST_ERROR]:
            'Capture stopped because extension storage is full. Download now, then clear before continuing.',
        });
        warn('Capture stopped because storage quota was exceeded');
      })();
      break;

    case MSG.SET_CAPTURING:
      void (async () => {
        const response = {[STORE.CAPTURING]: !!msg.value};
        await chrome.storage.session.set(response);
        if (msg.value) {
          await resetMeta();
        }
        log(`Capture ${msg.value ? 'enabled' : 'disabled'}`);
        sendResponse({ok: true});
      })();
      return true;

    case MSG.DOWNLOAD:
      void (async () => {
        const [result, metaState] = await Promise.all([
          chrome.storage.session.get(STORE.RESPONSES),
          chrome.storage.local.get(META.DOWNLOAD_DIR),
        ]);
        const responses = result[STORE.RESPONSES] ?? [];
        if (responses.length === 0) {
          warn('Download requested with no captured responses');
          sendResponse({ok: false, error: 'No data captured yet.'});
          return;
        }

        const payload = JSON.stringify(responses, null, 2);
        const downloadTarget = buildDownloadUrl(payload);
        const filename = buildFilename(msg.tabInfo, metaState[META.DOWNLOAD_DIR]);
        log(`Starting download for ${responses.length} captured response(s)`);
        chrome.downloads.download(
          {
            url: downloadTarget.url,
            filename,
            saveAs: false,
          },
          (downloadId) => {
            const error = chrome.runtime.lastError?.message;
            if (downloadTarget.revoke) {
              setTimeout(() => URL.revokeObjectURL(downloadTarget.url), 60_000);
            }
            if (error) {
              errorLog('Download failed', error);
              sendResponse({ok: false, error});
              return;
            }
            log(`Download started (id=${downloadId}, filename=${filename})`);
            sendResponse({ok: true, downloadId, filename});
          },
        );
      })();
      return true;

    case MSG.SET_DOWNLOAD_CONFIG:
      void (async () => {
        const dir = sanitizeRelativeDir(msg.downloadDir);
        await chrome.storage.local.set({
          [META.DOWNLOAD_DIR]: dir,
        });
        log(`Download directory set to ${dir}`);
        sendResponse({ok: true, downloadDir: dir});
      })();
      return true;

    case MSG.CLEAR:
      void (async () => {
        await chrome.storage.session.set({
          [STORE.RESPONSES]: [],
          [STORE.NEXT_SEQ]: 1,
        });
        await resetMeta();
        log('Cleared captured responses');
        sendResponse({ok: true});
      })();
      return true;

    default:
      break;
  }
});
