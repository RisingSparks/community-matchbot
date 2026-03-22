// Handles popup UI logic and communication with the background service worker.

const MSG = {
  GET_STATE: 'get_state',
  SET_CAPTURING: 'set_capturing',
  DOWNLOAD: 'download',
  CLEAR: 'clear',
};

const POLL_INTERVAL_MS = 1000;
const FLUSH_SETTLE_POLL_MS = 250;
const FLUSH_SETTLE_MAX_POLLS = 8;

const log = (...args) => console.info('FBGC[popup]:', ...args);
const warn = (...args) => console.warn('FBGC[popup]:', ...args);

let currentState = {
  capturing: false,
  count: 0,
  bytesUsed: 0,
  quotaExceeded: false,
  unsavedResponses: 0,
  lastError: '',
};

function sendMessage(message) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) {
        reject(chrome.runtime.lastError);
        return;
      }
      resolve(response);
    });
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function setStatus(message) {
  const el = document.getElementById('download_status');
  if (!message) {
    el.style.display = 'none';
    el.innerText = '';
    return;
  }
  el.style.display = 'block';
  el.innerText = message;
}

async function updateUI() {
  try {
    currentState = await sendMessage({type: MSG.GET_STATE});
  } catch {
    return;
  }

  document.getElementById('cap_status').innerText = currentState.capturing ? 'ON' : 'OFF';
  document.getElementById('cap_count').innerText = currentState.count;
  document.getElementById('cap_storage').innerText =
    `${(currentState.bytesUsed / 1024).toFixed(1)} KB`;
  document.getElementById('toggle').innerText = currentState.capturing
    ? 'Stop Capturing'
    : 'Start Capturing';
  document.getElementById('quota_warn').style.display =
    currentState.bytesUsed > 8 * 1024 * 1024 || currentState.quotaExceeded ? 'block' : 'none';

  const unsavedWarn = document.getElementById('unsaved_warn');
  if (currentState.unsavedResponses > 0 || currentState.lastError) {
    unsavedWarn.style.display = 'block';
    unsavedWarn.innerText = currentState.lastError
      || `Warning: ${currentState.unsavedResponses} response(s) were not persisted.`;
  } else {
    unsavedWarn.style.display = 'none';
    unsavedWarn.innerText = '';
  }
}

async function waitForSettledStorage() {
  let previousSignature = '';
  let stableReads = 0;

  for (let i = 0; i < FLUSH_SETTLE_MAX_POLLS; i += 1) {
    await sleep(FLUSH_SETTLE_POLL_MS);

    let state;
    try {
      state = await sendMessage({type: MSG.GET_STATE});
    } catch {
      return;
    }

    const signature = `${state.count}:${state.bytesUsed}:${state.unsavedResponses}:${state.lastError}`;
    if (signature === previousSignature) {
      stableReads += 1;
      if (stableReads >= 2) {
        currentState = state;
        return;
      }
    } else {
      previousSignature = signature;
      stableReads = 0;
    }
  }
}

document.getElementById('toggle').addEventListener('click', async () => {
  try {
    log(`Toggling capture ${currentState.capturing ? 'off' : 'on'}`);
    await sendMessage({type: MSG.SET_CAPTURING, value: !currentState.capturing});
  } catch {
    warn('Failed to change capture state');
    setStatus('Failed to change capture state.');
    return;
  }
  setStatus('');
  await updateUI();
});

document.getElementById('download').addEventListener('click', async () => {
  setStatus('');

  try {
    if (currentState.capturing) {
      log('Stopping capture before download');
      await sendMessage({type: MSG.SET_CAPTURING, value: false});
      await waitForSettledStorage();
    }

    const result = await sendMessage({type: MSG.DOWNLOAD});
    if (!result?.ok) {
      warn('Download failed to start', result?.error || 'unknown error');
      setStatus(result?.error || 'Download failed.');
      return;
    }
    log('Download started');
    setStatus('Download started. Clear storage after the file is saved.');
  } catch {
    warn('Download failed');
    setStatus('Download failed.');
    return;
  }

  await updateUI();
});

document.getElementById('clear').addEventListener('click', async () => {
  if (!confirm('Clear all captured data from storage?')) {
    return;
  }

  try {
    log('Clearing captured storage');
    await sendMessage({type: MSG.CLEAR});
  } catch {
    warn('Failed to clear storage');
    setStatus('Failed to clear storage.');
    return;
  }
  setStatus('');
  await updateUI();
});

setInterval(() => {
  void updateUI();
}, POLL_INTERVAL_MS);
void updateUI();
