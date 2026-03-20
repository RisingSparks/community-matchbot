// Runs in ISOLATED world - can use chrome.storage API
// Listens for CustomEvents dispatched by content_main.js

const MSG = {
  QUOTA_EXCEEDED: 'quota_exceeded',
};

const STORE = {
  CAPTURING: 'fbgc_capturing',
  RESPONSES: 'fbgc_responses',
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

      const result = await chrome.storage.session.get([STORE.RESPONSES, STORE.CAPTURING]);
      if (!result[STORE.CAPTURING]) {
        continue;
      }

      const existing = result[STORE.RESPONSES] ?? [];
      try {
        await chrome.storage.session.set({[STORE.RESPONSES]: existing.concat(batch)});
      } catch (err) {
        // Quota exceeded (10MB) - notify background so popup can warn user
        if (err?.name === 'QuotaExceededError' || err?.message?.includes('QuotaExceeded')) {
          chrome.runtime.sendMessage({type: MSG.QUOTA_EXCEEDED});
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
