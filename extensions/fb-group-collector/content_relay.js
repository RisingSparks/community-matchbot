// Runs in ISOLATED world - can use chrome.storage API
// Listens for CustomEvents dispatched by content_main.js

const MSG = {
  CAPTURE_WRITE_FAILED: 'capture_write_failed',
  ENSURE_NEW_POSTS_SORT: 'ensure_new_posts_sort',
};

const STORE = {
  CAPTURING: 'fbgc_capturing',
};

const META = {
  RESPONSE_COUNT: 'fbgc_response_count',
  BYTES_USED: 'fbgc_bytes_used',
  NEXT_SEQ: 'fbgc_next_seq',
};

const DB_NAME = 'fbgc_capture';
const DB_VERSION = 1;
const RESPONSES_STORE = 'responses';

let pendingResponses = [];
let flushPromise = null;
let extensionContextValid = true;
let captureDbPromise = null;
let appendQueue = Promise.resolve();
const SORT_CONTROL_TIMEOUT_MS = 10000;
const SORT_MENU_TIMEOUT_MS = 5000;
const SORT_POLL_MS = 200;

const log = (...args) => console.info('FBGC[relay]:', ...args);
const warn = (...args) => console.warn('FBGC[relay]:', ...args);
const errorLog = (...args) => console.error('FBGC[relay]:', ...args);

function isContextInvalidated(err) {
  const message = String(err?.message ?? err ?? '');
  return message.includes('Extension context invalidated')
    || message.includes('context invalidated');
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function notifyBridgeOffline() {
  document.dispatchEvent(new CustomEvent('_fbgc_bridge_offline'));
}

function textContentOf(element) {
  return String(element?.textContent ?? '').replace(/\s+/g, ' ').trim();
}

function findSortControl() {
  const buttons = Array.from(document.querySelectorAll('[role="button"]'));
  return buttons.find((button) => {
    const text = textContentOf(button).toLowerCase();
    return text.includes('sort group feed by');
  }) ?? null;
}

function isNewPostsSelected(control) {
  return textContentOf(control).toLowerCase().includes('new posts');
}

function findNewPostsOption() {
  const menuItems = Array.from(document.querySelectorAll('[role="menuitem"], [role="option"], [role="button"]'));
  return menuItems.find((item) => {
    const text = textContentOf(item).toLowerCase();
    return text === 'new posts' || text.endsWith(' new posts') || text.includes('\nnew posts');
  }) ?? null;
}

async function waitForElement(getter, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const element = getter();
    if (element) {
      return element;
    }
    await sleep(SORT_POLL_MS);
  }
  return null;
}

async function ensureNewPostsSort() {
  const sortControl = await waitForElement(findSortControl, SORT_CONTROL_TIMEOUT_MS);
  if (!sortControl) {
    throw new Error('Could not find the Facebook group sort control.');
  }

  if (isNewPostsSelected(sortControl)) {
    log('Feed sort already set to New posts');
    return {changed: false};
  }

  sortControl.click();
  const option = await waitForElement(findNewPostsOption, SORT_MENU_TIMEOUT_MS);
  if (!option) {
    throw new Error('Opened the sort menu, but could not find the New posts option.');
  }

  option.click();
  await sleep(750);

  const refreshedControl = findSortControl();
  if (!refreshedControl || !isNewPostsSelected(refreshedControl)) {
    throw new Error('Clicked New posts, but the feed sort did not update.');
  }

  log('Feed sort changed to New posts');
  return {changed: true};
}

async function getSessionValues(keys) {
  if (!extensionContextValid) {
    return null;
  }
  try {
    return await chrome.storage.session.get(keys);
  } catch (err) {
    if (isContextInvalidated(err)) {
      extensionContextValid = false;
      notifyBridgeOffline();
      warn('Extension context invalidated; reload the extension and refresh the page');
      return null;
    }
    errorLog('chrome.storage.session unavailable in this content-script context', err);
    return null;
  }
}

// Write directly to IndexedDB from the content script, bypassing the background
// service worker. MV3 service workers are terminated after ~30s of inactivity,
// which causes "The message port closed before a response was received" when the
// content script tries to send APPEND_RESPONSES messages.
function openCaptureDb() {
  if (captureDbPromise) {
    return captureDbPromise;
  }
  captureDbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(RESPONSES_STORE)) {
        db.createObjectStore(RESPONSES_STORE, {keyPath: 'seq'});
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('Failed to open capture DB'));
  });
  return captureDbPromise;
}

function waitForTransaction(tx) {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onabort = () => reject(tx.error || new Error('IndexedDB transaction aborted'));
    tx.onerror = () => reject(tx.error || new Error('IndexedDB transaction failed'));
  });
}

function byteSizeOfRecord(record) {
  return JSON.stringify(record).length;
}

function enqueueAppend(operation) {
  const run = appendQueue.then(operation, operation);
  appendQueue = run.catch(() => {});
  return run;
}

async function appendResponsesDirect(responses) {
  const validRecords = responses.flatMap((response) => {
    if (typeof response === 'string' && response.length > 0) {
      return [{text: response, pageTitle: '', pageUrl: ''}];
    }
    if (response && typeof response === 'object' && typeof response.text === 'string' && response.text.length > 0) {
      return [{
        text: response.text,
        pageTitle: typeof response.pageTitle === 'string' ? response.pageTitle : '',
        pageUrl: typeof response.pageUrl === 'string' ? response.pageUrl : '',
      }];
    }
    return [];
  });
  if (validRecords.length === 0) {
    return {written: 0};
  }

  return enqueueAppend(async () => {
    const meta = await chrome.storage.local.get([
      META.RESPONSE_COUNT,
      META.BYTES_USED,
      META.NEXT_SEQ,
    ]);
    const nextSeq = Number.isFinite(meta[META.NEXT_SEQ]) ? meta[META.NEXT_SEQ] : 1;
    const timestamp = new Date().toISOString();
    const records = validRecords.map((response, index) => ({
      seq: nextSeq + index,
      capturedAt: timestamp,
      text: response.text,
      pageTitle: response.pageTitle,
      pageUrl: response.pageUrl,
    }));

    const db = await openCaptureDb();
    const tx = db.transaction(RESPONSES_STORE, 'readwrite');
    const store = tx.objectStore(RESPONSES_STORE);
    for (const record of records) {
      store.put(record);
    }
    await waitForTransaction(tx);

    const bytesAdded = records.reduce((sum, record) => sum + byteSizeOfRecord(record), 0);
    await chrome.storage.local.set({
      [META.RESPONSE_COUNT]: (meta[META.RESPONSE_COUNT] ?? 0) + records.length,
      [META.BYTES_USED]: (meta[META.BYTES_USED] ?? 0) + bytesAdded,
      [META.NEXT_SEQ]: nextSeq + records.length,
    });

    return {written: records.length, bytesAdded};
  });
}

async function notifyWriteFailed(unsavedCount, error) {
  if (!extensionContextValid) {
    return;
  }
  try {
    chrome.runtime.sendMessage({
      type: MSG.CAPTURE_WRITE_FAILED,
      unsavedCount,
      error,
    });
  } catch (_err) {
    // Best-effort; background may be asleep, but the important thing is we stop capturing.
  }
  // Stop capture directly via session storage so the UI reflects the error even
  // if the background worker is unavailable.
  try {
    await chrome.storage.session.set({[STORE.CAPTURING]: false});
  } catch (_err) {
    // ignore
  }
}

async function flushResponses() {
  if (flushPromise) {
    return flushPromise;
  }

  flushPromise = (async () => {
    while (pendingResponses.length > 0) {
      const batch = pendingResponses;
      pendingResponses = [];

      const result = await getSessionValues([STORE.CAPTURING]);
      if (!result) {
        return;
      }
      if (!result[STORE.CAPTURING]) {
        return;
      }

      try {
        await appendResponsesDirect(batch);
      } catch (err) {
        if (isContextInvalidated(err)) {
          extensionContextValid = false;
          notifyBridgeOffline();
          warn('Extension context invalidated during direct DB append');
          return;
        }
        errorLog('Failed to persist captured responses', err);
        await notifyWriteFailed(batch.length, 'Capture stopped because IndexedDB writes failed.');
        return;
      }
    }
  })().finally(() => {
    flushPromise = null;
    if (pendingResponses.length > 0) {
      void flushResponses();
    }
  });

  return flushPromise;
}

document.addEventListener('_fbgc', async (e) => {
  if (!extensionContextValid) {
    return;
  }

  const result = await getSessionValues(STORE.CAPTURING);
  if (!result) {
    return;
  }
  if (!result[STORE.CAPTURING]) {
    return;
  }

  pendingResponses.push(e.detail);
  void flushResponses().catch((err) => {
    if (isContextInvalidated(err)) {
      extensionContextValid = false;
      notifyBridgeOffline();
      warn('Extension context invalidated during flush');
      return;
    }
    errorLog('Flush failed', err);
  });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== MSG.ENSURE_NEW_POSTS_SORT) {
    return false;
  }

  void (async () => {
    try {
      const result = await ensureNewPostsSort();
      sendResponse({ok: true, ...result});
    } catch (err) {
      warn('Failed to set feed sort to New posts', err);
      sendResponse({ok: false, error: String(err?.message ?? err)});
    }
  })();

  return true;
});

log('Relay listener installed');
