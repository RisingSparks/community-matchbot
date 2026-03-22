// Service worker, handles popup actions and capture state.
// Response bodies live in chrome.storage.session; small status metadata lives in chrome.storage.local.

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
  NEXT_SEQ: 'fbgc_next_seq',
};

const META = {
  QUOTA_EXCEEDED: 'fbgc_quota_exceeded',
  UNSAVED_RESPONSES: 'fbgc_unsaved_responses',
  LAST_ERROR: 'fbgc_last_error',
};

async function ensureStorageAccess() {
  if (chrome.storage?.session?.setAccessLevel) {
    await chrome.storage.session.setAccessLevel({
      accessLevel: 'TRUSTED_AND_UNTRUSTED_CONTEXTS',
    });
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
  if (Object.keys(metaDefaults).length > 0) {
    await chrome.storage.local.set(metaDefaults);
  }
}

async function initializeState() {
  await ensureStorageAccess();
  await ensureDefaults();
}

function buildFilename() {
  const iso = new Date().toISOString().replace(/[:]/g, '-');
  return `fb_posts_${iso}.json`;
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
        });
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
      })();
      break;

    case MSG.SET_CAPTURING:
      void (async () => {
        const response = {[STORE.CAPTURING]: !!msg.value};
        await chrome.storage.session.set(response);
        if (msg.value) {
          await resetMeta();
        }
        sendResponse({ok: true});
      })();
      return true;

    case MSG.DOWNLOAD:
      void (async () => {
        const result = await chrome.storage.session.get(STORE.RESPONSES);
        const responses = result[STORE.RESPONSES] ?? [];
        if (responses.length === 0) {
          sendResponse({ok: false, error: 'No data captured yet.'});
          return;
        }

        const payload = JSON.stringify(responses, null, 2);
        const downloadTarget = buildDownloadUrl(payload);
        chrome.downloads.download(
          {
            url: downloadTarget.url,
            filename: buildFilename(),
            saveAs: true,
          },
          (downloadId) => {
            const error = chrome.runtime.lastError?.message;
            if (downloadTarget.revoke) {
              setTimeout(() => URL.revokeObjectURL(downloadTarget.url), 60_000);
            }
            if (error) {
              sendResponse({ok: false, error});
              return;
            }
            sendResponse({ok: true, downloadId});
          },
        );
      })();
      return true;

    case MSG.CLEAR:
      void (async () => {
        await chrome.storage.session.set({
          [STORE.RESPONSES]: [],
          [STORE.NEXT_SEQ]: 1,
        });
        await resetMeta();
        sendResponse({ok: true});
      })();
      return true;

    default:
      break;
  }
});
