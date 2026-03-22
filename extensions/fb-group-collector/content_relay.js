// Runs in ISOLATED world - can use chrome.storage API
// Listens for CustomEvents dispatched by content_main.js

const MSG = {
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

const log = (...args) => console.info('FBGC[relay]:', ...args);
const warn = (...args) => console.warn('FBGC[relay]:', ...args);
const errorLog = (...args) => console.error('FBGC[relay]:', ...args);

function isContextInvalidated(err) {
  const message = String(err?.message ?? err ?? '');
  return message.includes('Extension context invalidated')
    || message.includes('context invalidated');
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

log('Relay listener installed');
