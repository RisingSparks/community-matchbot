// Runs in ISOLATED world - can use chrome.storage API
// Listens for CustomEvents dispatched by content_main.js

document.addEventListener('_fbgc', async (e) => {
  const result = await chrome.storage.session.get(['fbgc_responses', 'fbgc_capturing']);
  if (!result.fbgc_capturing) return;

  const existing = result.fbgc_responses ?? [];
  existing.push(e.detail);

  try {
    await chrome.storage.session.set({fbgc_responses: existing});
  } catch (err) {
    // Quota exceeded (10MB) - notify background so popup can warn user
    if (err.message.includes('QuotaExceeded')) {
      chrome.runtime.sendMessage({type: 'quota_exceeded'});
    }
  }
});
