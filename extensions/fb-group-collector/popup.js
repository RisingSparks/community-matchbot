// Handles popup UI logic and communication with background script

function updateUI() {
  chrome.runtime.sendMessage({type: 'get_state'}, (r) => {
    if (chrome.runtime.lastError) return;
    document.getElementById('cap_status').innerText = r.capturing ? 'ON' : 'OFF';
    document.getElementById('cap_count').innerText = r.count;
    document.getElementById('cap_storage').innerText = (r.bytesUsed / 1024).toFixed(1) + ' KB';
    document.getElementById('toggle').innerText = r.capturing ? 'Stop Capturing' : 'Start Capturing';
    document.getElementById('quota_warn').style.display = (r.bytesUsed > 8 * 1024 * 1024 || r.quotaExceeded) ? 'block' : 'none';
  });
}

document.getElementById('toggle').addEventListener('click', () => {
  const isCapturing = document.getElementById('cap_status').innerText === 'ON';
  chrome.runtime.sendMessage({type: 'set_capturing', value: !isCapturing}, updateUI);
});

document.getElementById('download').addEventListener('click', () => {
  chrome.runtime.sendMessage({type: 'download'}, (r) => {
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
    chrome.runtime.sendMessage({type: 'clear'}, updateUI);
  }
});

// Refresh UI every second while popup is open
setInterval(updateUI, 1000);
updateUI();
