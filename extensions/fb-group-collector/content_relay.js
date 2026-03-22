// Runs in ISOLATED world - can use chrome.storage API
// Listens for CustomEvents dispatched by content_main.js

const MSG = {
  APPEND_RESPONSES: 'append_responses',
  CAPTURE_WRITE_FAILED: 'capture_write_failed',
  ENSURE_NEW_POSTS_SORT: 'ensure_new_posts_sort',
};

const STORE = {
  CAPTURING: 'fbgc_capturing',
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

async function sendRuntimeMessage(message) {
  if (!extensionContextValid) {
    return null;
  }

  try {
    return await new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(message, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        resolve(response);
      });
    });
  } catch (err) {
    if (isContextInvalidated(err)) {
      extensionContextValid = false;
      notifyBridgeOffline();
      warn('Extension context invalidated while messaging the background worker');
      return null;
    }
    throw err;
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
        const appendResult = await sendRuntimeMessage({
          type: MSG.APPEND_RESPONSES,
          responses: batch,
        });
        if (!appendResult) {
          return;
        }
        if (!appendResult.ok) {
          await sendRuntimeMessage({
            type: MSG.CAPTURE_WRITE_FAILED,
            unsavedCount: batch.length,
            error: appendResult.error || 'Capture stopped because IndexedDB writes failed.',
          });
          warn('Stopping capture because the background worker rejected an append batch');
          return;
        }
      } catch (err) {
        if (isContextInvalidated(err)) {
          extensionContextValid = false;
          notifyBridgeOffline();
          warn('Extension context invalidated during background append');
          return;
        }
        errorLog('Failed to persist captured responses', err);
        await sendRuntimeMessage({
          type: MSG.CAPTURE_WRITE_FAILED,
          unsavedCount: batch.length,
          error: 'Capture stopped because IndexedDB writes failed.',
        });
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
