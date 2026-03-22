// Runs in ISOLATED world - can use chrome.storage API
// Listens for CustomEvents dispatched by content_main.js

const MSG = {
  ENSURE_NEW_POSTS_SORT: 'ensure_new_posts_sort',
  QUOTA_EXCEEDED: 'quota_exceeded',
};

const STORE = {
  CAPTURING: 'fbgc_capturing',
  RESPONSES: 'fbgc_responses',
  NEXT_SEQ: 'fbgc_next_seq',
};

let pendingResponses = [];
let flushPromise = null;
let extensionContextValid = true;
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
      warn('Extension context invalidated; reload the extension and refresh the page');
      return null;
    }
    errorLog('chrome.storage.session unavailable in this content-script context', err);
    return null;
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

      const result = await getSessionValues([STORE.RESPONSES, STORE.NEXT_SEQ]);
      if (!result) {
        return;
      }

      const existing = result[STORE.RESPONSES] ?? [];
      const nextSeq = Number.isFinite(result[STORE.NEXT_SEQ])
        ? result[STORE.NEXT_SEQ]
        : existing.length + 1;
      const timestamp = new Date().toISOString();
      const records = batch.map((text, index) => ({
        seq: nextSeq + index,
        capturedAt: timestamp,
        text,
      }));
      try {
        await chrome.storage.session.set({
          [STORE.RESPONSES]: existing.concat(records),
          [STORE.NEXT_SEQ]: nextSeq + records.length,
        });
      } catch (err) {
        if (isContextInvalidated(err)) {
          extensionContextValid = false;
          warn('Extension context invalidated during storage write');
          return;
        }
        // chrome.storage.session is capped at 10 MB. Stop capture immediately so we do not
        // keep silently discarding subsequent responses while the popup still says "ON".
        if (err?.name === 'QuotaExceededError' || err?.message?.includes('QuotaExceeded')) {
          pendingResponses = batch.concat(pendingResponses);
          warn('Storage quota exceeded; stopping capture with unsaved responses', batch.length);
          try {
            chrome.runtime.sendMessage({type: MSG.QUOTA_EXCEEDED, unsavedCount: batch.length});
          } catch (sendErr) {
            if (isContextInvalidated(sendErr)) {
              extensionContextValid = false;
              warn('Extension context invalidated while notifying background about quota overflow');
              return;
            }
            errorLog('Failed to notify background about quota overflow', sendErr);
          }
          return;
        } else {
          errorLog('Failed to persist captured responses', err);
        }
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
