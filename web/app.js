'use strict';

const $ = id => document.getElementById(id);
const video = $('camera');
const overlay = $('overlay');
const cameraBox = video.parentElement;
const monitorPanel = cameraBox.parentElement;
const state = {
  stream: null, scanVersion: 0, scanning: false, cameraStarting: false,
  visionReady: false, connected: false, busy: false,
  samples: [], events: [], residents: [], trials: [], report: null, markdown: '',
};
const titles = {
  monitor: 'Live entry monitor', enroll: 'Enroll a resident', residents: 'Resident directory',
  logs: 'Entry event history', evaluation: 'Performance evaluation',
};

function status(message, error = false) {
  $('status').textContent = message;
  $('status').classList.toggle('error', error);
}

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) throw Error(result.error || 'The local request failed.');
  return result;
}

function cell(row, text) {
  const td = document.createElement('td');
  td.textContent = text;
  row.append(td);
  return td;
}

function updateControls() {
  const active = state.residents.some(r => r.active && r.samples);
  $('startScan').disabled = !state.connected || !state.visionReady || !state.stream || !active || state.busy || state.scanning;
  $('captureSample').disabled = !state.stream || state.busy || state.samples.length >= 5;
  $('saveResident').disabled = !state.connected || !state.visionReady || state.samples.length < 3 || state.busy;
  $('runEvaluation').disabled = !state.connected || !state.visionReady || !active || !state.trials.length || state.busy;
  for (const id of ['enrollPhotos', 'testPhotos', 'clearSamples', 'clearTrials', 'residentId', 'residentName', 'apartment', 'consent', 'heldOut']) {
    $(id).disabled = state.busy;
  }
  $('sampleCount').textContent = `${state.samples.length} / 5 samples captured · minimum 3`;
  $('trialCount').textContent = state.trials.length ? `${state.trials.length} test images selected` : 'No test images selected.';
}

function renderSamples() {
  $('samplePreview').replaceChildren();
  state.samples.forEach((image, index) => {
    const img = document.createElement('img');
    img.src = image;
    img.alt = `Enrollment sample ${index + 1}`;
    $('samplePreview').append(img);
  });
  updateControls();
}

function renderTrials() {
  $('trialRows').replaceChildren();
  state.trials.forEach((trial, index) => {
    const row = document.createElement('tr');
    cell(row, trial.filename);
    const select = document.createElement('select');
    select.setAttribute('aria-label', `Expected identity for ${trial.filename}`);
    select.append(new Option('Unknown visitor', ''));
    state.residents.filter(r => r.active).forEach(r => select.append(new Option(`${r.id} — ${r.name}`, r.id)));
    select.value = trial.expected_id || '';
    select.disabled = state.busy;
    select.onchange = () => { trial.expected_id = select.value || null; };
    cell(row, '').append(select);
    const remove = document.createElement('button');
    remove.textContent = 'Remove';
    remove.className = 'secondary';
    remove.disabled = state.busy;
    remove.onclick = () => { state.trials.splice(index, 1); renderTrials(); };
    cell(row, '').append(remove);
    $('trialRows').append(row);
  });
  updateControls();
}

async function refresh() {
  try {
    const data = await api('/api/status');
    state.connected = true;
    state.visionReady = data.vision_ready;
    state.residents = data.residents;
    state.events = data.events;
    $('residentCount').textContent = data.active_count;
    $('eventCount').textContent = data.event_count;
    $('backendNotice').classList.toggle('ready', state.visionReady);
    $('backendNotice').textContent = state.visionReady
      ? 'Recognition backend ready. Enroll residents, start your camera, then start recognition.'
      : 'Recognition backend unavailable. OpenCV / dlib dependencies must be installed before face enrollment, recognition, or evaluation can run.';
    $('residentRows').replaceChildren();
    $('noResidents').hidden = !!state.residents.length;
    for (const resident of state.residents) {
      const row = document.createElement('tr');
      [resident.id, resident.name, resident.apartment, resident.samples, resident.active ? 'Active' : 'Inactive'].forEach(v => cell(row, v));
      const button = document.createElement('button');
      button.className = 'secondary';
      button.textContent = resident.active ? 'Deactivate' : 'Activate';
      button.disabled = state.busy;
      button.onclick = async () => {
        pauseScan();
        try {
          await api('/api/resident-status', {id: resident.id, active: !resident.active});
          await refresh();
          status(`Access updated for ${resident.id}.`);
        } catch (error) { status(error.message, true); }
      };
      cell(row, '').append(button);
      $('residentRows').append(row);
    }
    $('logRows').replaceChildren();
    $('noLogs').hidden = !!state.events.length;
    for (const event of state.events) {
      const row = document.createElement('tr');
      [new Date(event.timestamp).toLocaleString(), event.resident_id || 'Unknown', event.decision,
        event.distance == null ? '—' : event.distance.toFixed(3), event.reason].forEach(v => cell(row, v));
      $('logRows').append(row);
    }
    updateControls();
    return true;
  } catch (error) {
    state.connected = false;
    updateControls();
    status(`Cannot reach the local server: ${error.message}`, true);
    return false;
  }
}

function pauseScan() {
  state.scanning = false;
  state.scanVersion += 1;
  overlay.getContext('2d').clearRect(0, 0, overlay.width, overlay.height);
  updateControls();
}

document.querySelectorAll('[data-tab]').forEach(button => {
  button.onclick = async () => {
    pauseScan();
    const tab = button.dataset.tab;
    document.querySelectorAll('main > section').forEach(section => { section.hidden = section.id !== tab; });
    document.querySelectorAll('[data-tab]').forEach(item => item.classList.toggle('active', item === button));
    $('pageTitle').textContent = titles[tab];
    if (tab === 'enroll') $('enrollSlot').append(cameraBox);
    else monitorPanel.insertBefore(cameraBox, monitorPanel.querySelector('.controls'));
    await refresh();
    if (tab === 'evaluation') renderTrials();
  };
});

async function startCamera() {
  if (state.cameraStarting) return;
  state.cameraStarting = true;
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw Error('Use localhost in a browser that supports camera access.');
    if (!state.stream) {
      state.stream = await navigator.mediaDevices.getUserMedia({video: {width: {ideal: 640}, height: {ideal: 480}}, audio: false});
      video.srcObject = state.stream;
      await video.play();
      state.stream.getVideoTracks()[0].addEventListener('ended', stopCamera, {once: true});
    }
    $('cameraEmpty').style.display = 'none';
    $('cameraState').textContent = 'Live';
    status('Camera is live. Images are processed only on this laptop.');
    await refresh();
  } catch (error) {
    stopCamera();
    status(`Camera could not start: ${error.message}`, true);
  } finally { state.cameraStarting = false; }
}

function stopCamera() {
  pauseScan();
  const stream = state.stream;
  state.stream = null;
  if (stream) stream.getTracks().forEach(track => track.stop());
  video.srcObject = null;
  $('cameraEmpty').style.display = 'grid';
  $('cameraState').textContent = 'Standby';
  showDecision([]);
  updateControls();
}

function currentFrame() {
  if (!state.stream || !video.videoWidth) throw Error('Start your camera first.');
  const canvas = document.createElement('canvas');
  canvas.width = 640;
  canvas.height = Math.round(video.videoHeight / video.videoWidth * 640);
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.85);
}

async function readPhoto(file) {
  if (!['image/jpeg', 'image/png'].includes(file.type) || file.size > 10_000_000) {
    throw Error('Choose JPEG or PNG photos below 10 MB each.');
  }
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    if (image.width * image.height > 30_000_000) throw Error('Choose photos below 30 megapixels.');
    const scale = Math.min(1, 960 / Math.max(image.width, image.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(image.width * scale));
    canvas.height = Math.max(1, Math.round(image.height * scale));
    canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', 0.85);
  } finally { URL.revokeObjectURL(url); }
}

$('startCamera').onclick = startCamera;
$('enrollCamera').onclick = startCamera;
for (const id of ['stopCamera', 'enrollStop']) $(id).onclick = () => { stopCamera(); status('Camera stopped.'); };
$('captureSample').onclick = () => {
  try {
    if (state.samples.length >= 5) throw Error('Five samples captured. Save or clear samples.');
    state.samples.push(currentFrame());
    renderSamples();
    status('Sample captured. Change your pose slightly for the next sample.');
  } catch (error) { status(error.message, true); }
};
function clearSamples() { state.samples = []; $('enrollPhotos').value = ''; renderSamples(); }
$('clearSamples').onclick = clearSamples;
for (const id of ['residentId', 'residentName', 'apartment']) $(id).addEventListener('input', () => {
  if (state.samples.length) { clearSamples(); status('Details changed. Capture or select fresh samples for this resident.'); }
});
$('enrollPhotos').onchange = async event => {
  try {
    const files = Array.from(event.target.files);
    if (state.samples.length + files.length > 5) throw Error('Use at most five enrollment images. Clear samples to start again.');
    const images = [];
    for (const file of files) images.push(await readPhoto(file));
    state.samples.push(...images);
    renderSamples();
    status('Photos loaded. Confirm details and consent, then save the resident.');
  } catch (error) { status(error.message, true); }
  event.target.value = '';
};
$('enrollForm').onsubmit = async event => {
  event.preventDefault();
  if (state.busy) return;
  state.busy = true;
  pauseScan();
  status('Checking enrollment faces…');
  try {
    const result = await api('/api/enroll', {
      id: $('residentId').value.trim(), name: $('residentName').value.trim(), apartment: $('apartment').value.trim(),
      consent: $('consent').checked, images: state.samples,
    });
    clearSamples();
    $('enrollForm').reset();
    status(`Resident saved with ${result.samples} samples.`);
  } catch (error) { status(error.message, true); }
  finally { state.busy = false; await refresh(); }
};

function showDecision(faces) {
  $('decision').replaceChildren();
  overlay.getContext('2d').clearRect(0, 0, overlay.width, overlay.height);
  if (!faces.length) {
    const strong = document.createElement('strong');
    strong.textContent = state.stream ? 'Waiting for a face' : 'Camera is on standby';
    $('decision').append(strong);
  }
  for (const face of faces) {
    const [top, right, bottom, left] = face.box;
    const color = face.decision === 'ALLOWED' ? '#61e8ad' : '#ff8895';
    const context = overlay.getContext('2d');
    context.strokeStyle = color;
    context.lineWidth = 3;
    context.strokeRect(left, top, right - left, bottom - top);
    context.fillStyle = color;
    context.font = '16px sans-serif';
    context.fillText(`Entry ${face.decision}`, left, Math.max(20, top - 10));
    const title = document.createElement('strong');
    title.textContent = `Entry ${face.decision} · ${face.name}`;
    title.style.color = color;
    const detail = document.createElement('p');
    detail.className = 'muted';
    detail.textContent = face.reason;
    $('decision').append(title, detail);
  }
}

$('startScan').onclick = async () => {
  if (state.scanning) return;
  const threshold = Number($('threshold').value);
  if (!Number.isFinite(threshold) || threshold <= 0 || threshold >= 1) return status('Use a threshold between 0 and 1.', true);
  state.scanning = true;
  const version = ++state.scanVersion;
  updateControls();
  status('Recognition is active.');
  while (state.scanning && state.stream && version === state.scanVersion) {
    try {
      const result = await api('/api/recognize', {image: currentFrame(), threshold});
      if (!state.scanning || version !== state.scanVersion) break;
      overlay.width = result.width;
      overlay.height = result.height;
      showDecision(result.faces);
      if (!await refresh()) { pauseScan(); break; }
    } catch (error) {
      if (version === state.scanVersion) { pauseScan(); status(error.message, true); }
      break;
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
};

function download(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('exportLogs').onclick = () => {
  const columns = ['timestamp', 'resident_id', 'decision', 'distance', 'reason'];
  const quote = value => '"' + String(value ?? '').replaceAll('"', '""') + '"';
  const csv = [columns.join(','), ...state.events.map(event => columns.map(key => quote(event[key])).join(','))].join('\r\n');
  download('entry_logs.csv', csv, 'text/csv');
};
$('testPhotos').onchange = async event => {
  try {
    const files = Array.from(event.target.files);
    if (files.length + state.trials.length > 30) throw Error('Use at most 30 test images per evaluation.');
    const trials = [];
    for (const file of files) trials.push({filename: file.name, expected_id: null, image: await readPhoto(file)});
    state.trials.push(...trials);
    renderTrials();
    status('Set each image’s expected identity, then run evaluation.');
  } catch (error) { status(error.message, true); }
  event.target.value = '';
};
$('clearTrials').onclick = () => { state.trials = []; renderTrials(); };
$('runEvaluation').onclick = async () => {
  if (state.busy) return;
  if (!$('heldOut').checked) return status('Confirm the test images were held out from enrollment and tuning.', true);
  state.busy = true;
  pauseScan();
  renderTrials();
  status('Evaluating images. This may take a moment…');
  try {
    const result = await api('/api/evaluate', {threshold: Number($('threshold').value), held_out: true, trials: state.trials});
    state.report = result.report;
    state.markdown = result.markdown;
    $('evaluationResults').textContent = result.markdown;
    $('downloadJSON').disabled = false;
    $('downloadMD').disabled = false;
    status('Evaluation complete. Measured reports saved locally and available to download.');
  } catch (error) { status(error.message, true); }
  finally { state.busy = false; renderTrials(); }
};
$('downloadJSON').onclick = () => download('evaluation.json', JSON.stringify(state.report, null, 2), 'application/json');
$('downloadMD').onclick = () => download('evaluation.md', state.markdown, 'text/markdown');
window.addEventListener('beforeunload', () => state.stream?.getTracks().forEach(track => track.stop()));
refresh().then(connected => { if (connected) status('Connected to your local SQLite database.'); });
