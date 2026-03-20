// Service worker, handles popup actions and state
// chrome.storage.session persists for the browser session

const MSG = {
  GET_STATE: 'get_state',
  QUOTA_EXCEEDED: 'quota_exceeded',
  SET_CAPTURING: 'set_capturing',
  DOWNLOAD: 'download',
  CLEAR: 'clear',
};

const STORE = {
  CAPTURING: 'fbgc_capturing',
  RESPONSES: 'fbgc_responses',
  QUOTA_EXCEEDED: 'fbgc_quota_exceeded',
};

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  switch (msg.type) {
    case MSG.GET_STATE:
      chrome.storage.session.get(
        [STORE.CAPTURING, STORE.RESPONSES, STORE.QUOTA_EXCEEDED],
        (r) => {
          const responses = r[STORE.RESPONSES] ?? [];
          const bytesUsed = JSON.stringify(responses).length;
          sendResponse({
            capturing: !!r[STORE.CAPTURING],
            count: responses.length,
            bytesUsed,
            quotaExceeded: !!r[STORE.QUOTA_EXCEEDED],
          });
        },
      );
      return true;

    case MSG.QUOTA_EXCEEDED:
      chrome.storage.session.set({[STORE.QUOTA_EXCEEDED]: true});
      break;

    case MSG.SET_CAPTURING:
      chrome.storage.session.set({[STORE.CAPTURING]: msg.value});
      break;

    case MSG.DOWNLOAD:
      chrome.storage.session.get(STORE.RESPONSES, (r) => {
        sendResponse({data: r[STORE.RESPONSES] ?? []});
      });
      return true;

    case MSG.CLEAR:
      chrome.storage.session.set({
        [STORE.RESPONSES]: [],
        [STORE.QUOTA_EXCEEDED]: false,
      });
      break;

    default:
      break;
  }
});
