// Handles popup UI logic and communication with background script

const MSG = {
  GET_STATE: 'get_state',
  SET_CAPTURING: 'set_capturing',
  DOWNLOAD: 'download',
  CLEAR: 'clear',
};

let currentState = {
  capturing: false,
  count: 0,
  bytesUsed: 0,
  quotaExceeded: false,
};

function requestState() {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({type: MSG.GET_STATE}, (response) => {
      if (chrome.runtime.lastError) {
        reject(chrome.runtime.lastError);
        return;
      }
      resolve(response);
    });
  });
}

async function updateUI() {
  try {
    currentState = await requestState();
  } catch {
    return;
  }

  document.getElementById('cap_status').innerText = currentState.capturing ? 'ON' : 'OFF';
  document.getElementById('cap_count').innerText = currentState.count;
  document.getElementById('cap_storage').innerText = `${(currentState.bytesUsed / 1024).toFixed(1)} KB`;
  document.getElementById('toggle').innerText = currentState.capturing
    ? 'Stop Capturing'
    : 'Start Capturing';
  document.getElementById('quota_warn').style.display =
    currentState.bytesUsed > 8 * 1024 * 1024 || currentState.quotaExceeded ? 'block' : 'none';
}

document.getElementById('toggle').addEventListener('click', async () => {
  let state;
  try {
    state = await requestState();
  } catch {
    return;
  }

  chrome.runtime.sendMessage({type: MSG.SET_CAPTURING, value: !state.capturing}, updateUI);
});

document.getElementById('download').addEventListener('click', () => {
  chrome.runtime.sendMessage({type: MSG.DOWNLOAD}, (r) => {
    if (!r.data || r.data.length === 0) {
      alert('No data captured yet.');
      return;
    }
    const blob = new Blob([JSON.stringify(r.data, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'fb_posts_' + new Date().toISOString().split('T')[0] + '.json';
    a.click();
    URL.revokeObjectURL(url);
  });
});

document.getElementById('clear').addEventListener('click', () => {
  if (confirm('Clear all captured data from storage?')) {
    chrome.runtime.sendMessage({type: MSG.CLEAR}, updateUI);
  }
});

// Refresh UI every second while popup is open
setInterval(updateUI, 1000);
updateUI();
