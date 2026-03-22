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

async function flushResponses() {
  if (flushPromise) {
    return flushPromise;
  }

  flushPromise = (async () => {
    while (pendingResponses.length > 0) {
      const batch = pendingResponses;
      pendingResponses = [];

      const result = await chrome.storage.session.get([
        STORE.RESPONSES,
        STORE.CAPTURING,
        STORE.NEXT_SEQ,
      ]);
      if (!result[STORE.CAPTURING]) {
        continue;
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
        // chrome.storage.session is capped at 10 MB. Stop capture immediately so we do not
        // keep silently discarding subsequent responses while the popup still says "ON".
        if (err?.name === 'QuotaExceededError' || err?.message?.includes('QuotaExceeded')) {
          pendingResponses = batch.concat(pendingResponses);
          chrome.runtime.sendMessage({type: MSG.QUOTA_EXCEEDED, unsavedCount: batch.length});
          return;
        } else {
          console.error('FBGC: failed to persist captured responses', err);
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
  const result = await chrome.storage.session.get(STORE.CAPTURING);
  if (!result[STORE.CAPTURING]) {
    return;
  }

  pendingResponses.push(e.detail);
  void flushResponses();
});
