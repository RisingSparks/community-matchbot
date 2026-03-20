// Service worker, handles popup actions and state
// chrome.storage.session persists for the browser session

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'get_state') {
    chrome.storage.session.get(['fbgc_capturing', 'fbgc_responses', 'fbgc_quota_exceeded'], (r) => {
      const responses = r.fbgc_responses ?? [];
      const bytesUsed = JSON.stringify(responses).length;
      sendResponse({
        capturing: !!r.fbgc_capturing,
        count: responses.length,
        bytesUsed,
        quotaExceeded: !!r.fbgc_quota_exceeded,
      });
    });
    return true; // async response
  }

  if (msg.type === 'quota_exceeded') {
    chrome.storage.session.set({fbgc_quota_exceeded: true});
  }

  if (msg.type === 'set_capturing') {
    chrome.storage.session.set({fbgc_capturing: msg.value});
  }

  if (msg.type === 'download') {
    chrome.storage.session.get('fbgc_responses', (r) => {
      sendResponse({data: r.fbgc_responses ?? []});
    });
    return true;
  }

  if (msg.type === 'clear') {
    chrome.storage.session.set({
      fbgc_responses: [],
      fbgc_quota_exceeded: false
    });
  }
});
