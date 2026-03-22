// Handles popup UI logic and communication with the background service worker.

const MSG = {
  ENSURE_NEW_POSTS_SORT: 'ensure_new_posts_sort',
  GET_STATE: 'get_state',
  GET_GROUPS: 'get_groups',
  SAVE_GROUPS: 'save_groups',
  OPEN_GROUPS: 'open_groups',
  SET_CAPTURING: 'set_capturing',
  DOWNLOAD: 'download',
  CLEAR: 'clear',
  SET_DOWNLOAD_CONFIG: 'set_download_config',
};

const POLL_INTERVAL_MS = 1000;
const FLUSH_SETTLE_POLL_MS = 250;
const FLUSH_SETTLE_MAX_POLLS = 8;
const URL_FILE_DB_NAME = 'fbgc_popup';
const URL_FILE_DB_VERSION = 1;
const URL_FILE_STORE = 'config';
const URL_FILE_HANDLE_KEY = 'group_urls_file_handle';

const log = (...args) => console.info('FBGC[popup]:', ...args);
const warn = (...args) => console.warn('FBGC[popup]:', ...args);

let currentState = {
  capturing: false,
  count: 0,
  bytesUsed: 0,
  largeCapture: false,
  unsavedResponses: 0,
  lastError: '',
  downloadDir: '',
  groupUrls: [],
};

let activeTabInfo = {
  title: '',
  url: '',
};

let groupsStatusMessage = '';
let groupsStatusWarning = false;
let urlFileHandle = null;

function supportsGroupUrlFileAccess() {
  return typeof window.showSaveFilePicker === 'function';
}

function openUrlFileDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(URL_FILE_DB_NAME, URL_FILE_DB_VERSION);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(URL_FILE_STORE)) {
        db.createObjectStore(URL_FILE_STORE);
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('Failed to open the popup config database.'));
  });
}

function requestToPromise(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('IndexedDB request failed.'));
  });
}

function waitForTransaction(tx) {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onabort = () => reject(tx.error || new Error('IndexedDB transaction aborted.'));
    tx.onerror = () => reject(tx.error || new Error('IndexedDB transaction failed.'));
  });
}

async function readStoredUrlFileHandle() {
  const db = await openUrlFileDb();
  const tx = db.transaction(URL_FILE_STORE, 'readonly');
  const handle = await requestToPromise(tx.objectStore(URL_FILE_STORE).get(URL_FILE_HANDLE_KEY));
  await waitForTransaction(tx);
  return handle ?? null;
}

async function writeStoredUrlFileHandle(handle) {
  const db = await openUrlFileDb();
  const tx = db.transaction(URL_FILE_STORE, 'readwrite');
  tx.objectStore(URL_FILE_STORE).put(handle, URL_FILE_HANDLE_KEY);
  await waitForTransaction(tx);
}

async function getFilePermissionState(handle, write = false) {
  if (!handle?.queryPermission) {
    return 'denied';
  }
  return handle.queryPermission({mode: write ? 'readwrite' : 'read'});
}

async function ensureFilePermission(handle, write = false) {
  if (!handle?.requestPermission) {
    return false;
  }
  const granted = await handle.requestPermission({mode: write ? 'readwrite' : 'read'});
  return granted === 'granted';
}

async function readGroupUrlsFile(handle) {
  const file = await handle.getFile();
  return file.text();
}

async function writeGroupUrlsFile(handle, groupUrls) {
  const writable = await handle.createWritable();
  const content = `${groupUrls.join('\n')}${groupUrls.length > 0 ? '\n' : ''}`;
  await writable.write(content);
  await writable.close();
}

async function syncGroupsFromFile(handle) {
  const content = await readGroupUrlsFile(handle);
  const result = await sendMessage({
    type: MSG.SAVE_GROUPS,
    groupUrls: parseGroupLines(content),
  });
  currentState.groupUrls = result.groupUrls || [];
  document.getElementById('group_urls').value = currentState.groupUrls.join('\n');
  updateGroupsSummary();
  const notes = [`Loaded ${result.savedCount} group${result.savedCount === 1 ? '' : 's'} from the URL file.`];
  if (result.invalidCount > 0) {
    notes.push(`Ignored ${result.invalidCount} invalid entr${result.invalidCount === 1 ? 'y' : 'ies'}.`);
  }
  if (result.duplicateCount > 0) {
    notes.push(`Skipped ${result.duplicateCount} duplicate entr${result.duplicateCount === 1 ? 'y' : 'ies'}.`);
  }
  setGroupsOperationStatus(notes.join(' '), result.invalidCount > 0);
}

async function maybeLoadGroupsFromFile() {
  if (!supportsGroupUrlFileAccess()) {
    return;
  }

  try {
    urlFileHandle = await readStoredUrlFileHandle();
    if (!urlFileHandle) {
      return;
    }

    const permission = await getFilePermissionState(urlFileHandle, false);
    if (permission !== 'granted') {
      setGroupsOperationStatus('Group URL file is configured, but Chrome needs you to reselect it before auto-loading.', true);
      return;
    }

    await syncGroupsFromFile(urlFileHandle);
  } catch (err) {
    warn('Failed to auto-load groups from file', err);
    setGroupsOperationStatus('Configured URL file could not be loaded. Re-select it if needed.', true);
  }
}

async function persistGroupsToFile(groupUrls) {
  if (!urlFileHandle) {
    return false;
  }

  const permission = await getFilePermissionState(urlFileHandle, true);
  const hasAccess = permission === 'granted' || await ensureFilePermission(urlFileHandle, true);
  if (!hasAccess) {
    throw new Error('Chrome no longer has write access to the configured URL file.');
  }

  await writeGroupUrlsFile(urlFileHandle, groupUrls);
  return true;
}

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

async function sendTabMessage(tabId, message) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, message, (response) => {
      if (chrome.runtime.lastError) {
        const runtimeMessage = String(chrome.runtime.lastError.message || '');
        if (
          runtimeMessage.includes('Receiving end does not exist')
          || runtimeMessage.includes('message port closed')
        ) {
          reject(new Error('Reload the extension and refresh the Facebook group tab, then try again.'));
          return;
        }
        reject(chrome.runtime.lastError);
        return;
      }
      resolve(response);
    });
  });
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

function parseGroupLines(value) {
  return String(value ?? '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function normalizeGroupUrl(value) {
  const raw = String(value ?? '').trim();
  if (!raw) {
    return null;
  }

  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return null;
  }

  if (!/(^|\.)facebook\.com$/i.test(parsed.hostname)) {
    return null;
  }

  const match = parsed.pathname.match(/^\/groups\/([^/?#]+)/i);
  if (!match?.[1]) {
    return null;
  }

  return `https://www.facebook.com/groups/${match[1]}/`;
}

function summarizeGroupInput(value) {
  const lines = parseGroupLines(value);
  const seen = new Set();
  let validCount = 0;
  let invalidCount = 0;
  let duplicateCount = 0;

  for (const line of lines) {
    const normalized = normalizeGroupUrl(line);
    if (!normalized) {
      invalidCount += 1;
      continue;
    }
    if (seen.has(normalized)) {
      duplicateCount += 1;
      continue;
    }
    seen.add(normalized);
    validCount += 1;
  }

  return {
    validCount,
    invalidCount,
    duplicateCount,
    lines,
  };
}

function setGroupsStatus(message, isWarning = false) {
  const el = document.getElementById('groups_status');
  el.className = isWarning ? 'warning' : 'info';
  el.innerText = message;
}

function renderGroupsStatus() {
  setGroupsStatus(groupsStatusMessage, groupsStatusWarning);
}

function setGroupsOperationStatus(message, isWarning = false) {
  groupsStatusMessage = message;
  groupsStatusWarning = isWarning;
  renderGroupsStatus();
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
    currentState.largeCapture ? 'block' : 'none';

  const unsavedWarn = document.getElementById('unsaved_warn');
  if (currentState.unsavedResponses > 0 || currentState.lastError) {
    unsavedWarn.style.display = 'block';
    unsavedWarn.innerText = currentState.lastError
      || `Warning: ${currentState.unsavedResponses} response(s) were not persisted.`;
  } else {
    unsavedWarn.style.display = 'none';
    unsavedWarn.innerText = '';
  }

  const downloadDirInput = document.getElementById('download_dir');
  if (document.activeElement !== downloadDirInput) {
    downloadDirInput.value = currentState.downloadDir || '';
  }

  const groupUrlsInput = document.getElementById('group_urls');
  if (document.activeElement !== groupUrlsInput) {
    groupUrlsInput.value = (currentState.groupUrls || []).join('\n');
  }
  updateGroupsSummary();
}

async function loadActiveTabInfo() {
  try {
    const tabs = await chrome.tabs.query({active: true, currentWindow: true});
    const tab = tabs[0];
    activeTabInfo = {
      title: tab?.title || '',
      url: tab?.url || '',
    };
  } catch {
    activeTabInfo = {
      title: '',
      url: '',
    };
  }
}

async function getActiveFacebookGroupTab() {
  const tabs = await chrome.tabs.query({active: true, currentWindow: true});
  const tab = tabs[0];
  if (!tab?.id) {
    return null;
  }
  if (!String(tab.url || '').includes('facebook.com/groups/')) {
    return null;
  }
  return tab;
}

function updateGroupsSummary() {
  const groupUrlsInput = document.getElementById('group_urls');
  const summary = summarizeGroupInput(groupUrlsInput.value);
  const helpEl = document.getElementById('groups_help');

  if (summary.lines.length === 0) {
    helpEl.className = 'info';
    helpEl.innerText = 'Paste one Facebook group URL per line, then save them.';
    return;
  }

  const parts = [`${summary.validCount} valid`];
  if (summary.invalidCount > 0) {
    parts.push(`${summary.invalidCount} invalid`);
  }
  if (summary.duplicateCount > 0) {
    parts.push(`${summary.duplicateCount} duplicate`);
  }
  helpEl.className = summary.invalidCount > 0 ? 'warning' : 'info';
  helpEl.innerText = parts.join(', ');
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

document.getElementById('group_urls').addEventListener('input', () => {
  updateGroupsSummary();
});

document.getElementById('choose_groups_file').addEventListener('click', async () => {
  if (!supportsGroupUrlFileAccess()) {
    setGroupsOperationStatus('This Chrome build does not support choosing a writable URL file from the popup.', true);
    return;
  }

  try {
    const [handle] = await window.showSaveFilePicker({
      suggestedName: 'fb_group_urls.txt',
      types: [{
        description: 'Text files',
        accept: {'text/plain': ['.txt', '.md']},
      }],
    });
    if (!handle) {
      return;
    }

    urlFileHandle = handle;
    await writeStoredUrlFileHandle(handle);

    const permission = await getFilePermissionState(handle, false);
    const canRead = permission === 'granted' || await ensureFilePermission(handle, false);
    if (!canRead) {
      throw new Error('Chrome could not read the selected URL file.');
    }

    const existingContent = await readGroupUrlsFile(handle);
    if (existingContent.trim()) {
      await syncGroupsFromFile(handle);
      return;
    }

    await persistGroupsToFile(currentState.groupUrls || []);
    setGroupsOperationStatus('Configured the URL file. Future group saves will write to it automatically.');
  } catch (err) {
    if (err?.name === 'AbortError') {
      return;
    }
    warn('Failed to configure group URL file', err);
    setGroupsOperationStatus(String(err?.message || 'Failed to configure the URL file.'), true);
  }
});

document.getElementById('save_groups').addEventListener('click', async () => {
  const groupUrlsInput = document.getElementById('group_urls');
  const groupUrls = parseGroupLines(groupUrlsInput.value);

  try {
    const result = await sendMessage({type: MSG.SAVE_GROUPS, groupUrls});
    currentState.groupUrls = result.groupUrls || [];
    groupUrlsInput.value = currentState.groupUrls.join('\n');
    const notes = [`Saved ${result.savedCount} group${result.savedCount === 1 ? '' : 's'}.`];
    let savedToFile = false;
    if (urlFileHandle) {
      savedToFile = await persistGroupsToFile(currentState.groupUrls);
    }
    if (result.invalidCount > 0) {
      notes.push(`Ignored ${result.invalidCount} invalid entr${result.invalidCount === 1 ? 'y' : 'ies'}.`);
    }
    if (result.duplicateCount > 0) {
      notes.push(`Skipped ${result.duplicateCount} duplicate entr${result.duplicateCount === 1 ? 'y' : 'ies'}.`);
    }
    if (savedToFile) {
      notes.push('Updated the URL file.');
    }
    setGroupsOperationStatus(notes.join(' '), result.invalidCount > 0);
  } catch (err) {
    warn('Failed to save groups', err);
    setGroupsOperationStatus(String(err?.message || 'Failed to save groups.'), true);
  }
});

document.getElementById('open_groups').addEventListener('click', async () => {
  setStatus('');
  setGroupsOperationStatus('Opening group tabs and setting each feed to New posts...');
  try {
    const result = await sendMessage({type: MSG.OPEN_GROUPS});
    if (!result?.ok) {
      setGroupsOperationStatus(result?.error || 'Failed to open the saved groups.', true);
      return;
    }

    currentState.groupUrls = result.groupUrls || currentState.groupUrls;
    const parts = [
      `Opened ${result.opened}`,
      `prepared ${result.prepared}`,
    ];
    if (result.failed > 0) {
      parts.push(`failed ${result.failed}`);
    }
    setGroupsOperationStatus(parts.join(', ') + '.', result.failed > 0);
  } catch (err) {
    warn('Failed to open groups', err);
    setGroupsOperationStatus(String(err?.message || 'Failed to open groups.'), true);
  }
});

document.getElementById('toggle').addEventListener('click', async () => {
  try {
    const enabling = !currentState.capturing;
    log(`Toggling capture ${currentState.capturing ? 'off' : 'on'}`);
    if (enabling) {
      const tab = await getActiveFacebookGroupTab();
      if (tab?.id) {
        setStatus('Setting group feed sort to New posts...');
        const sortResult = await sendTabMessage(tab.id, {type: MSG.ENSURE_NEW_POSTS_SORT});
        if (!sortResult?.ok) {
          throw new Error(sortResult?.error || 'Failed to set the feed sort to New posts.');
        }
      }
    }
    await sendMessage({type: MSG.SET_CAPTURING, value: !currentState.capturing});
  } catch (err) {
    warn('Failed to change capture state', err);
    setStatus(String(err?.message || 'Failed to change capture state.'));
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

    const result = await sendMessage({type: MSG.DOWNLOAD, tabInfo: activeTabInfo});
    if (!result?.ok) {
      warn('Download failed to start', result?.error || 'unknown error');
      setStatus(result?.error || 'Download failed.');
      return;
    }
    log('Download started');
    setStatus(`Saved to ${result.filename}. Clear storage after the file is saved.`);
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

document.getElementById('download_dir').addEventListener('change', async (event) => {
  const value = event.target.value;
  try {
    const result = await sendMessage({type: MSG.SET_DOWNLOAD_CONFIG, downloadDir: value});
    currentState.downloadDir = result.downloadDir;
    event.target.value = result.downloadDir;
    setStatus('');
  } catch {
    warn('Failed to save download directory');
    setStatus('Failed to save download directory.');
  }
});

setInterval(() => {
  void updateUI();
}, POLL_INTERVAL_MS);
void Promise.all([
  updateUI(),
  loadActiveTabInfo(),
  sendMessage({type: MSG.GET_GROUPS}).then((result) => {
    currentState.groupUrls = result.groupUrls || [];
  }).catch(() => {}),
  maybeLoadGroupsFromFile(),
]).finally(() => {
  renderGroupsStatus();
  void updateUI();
});
