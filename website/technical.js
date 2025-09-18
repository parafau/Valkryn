/* app.js
 Plain-HTML prototype for door-security frontend.
 - uses webcam (getUserMedia) for live feed
 - overlay canvas for boxes
 - mock "detections" generated periodically
 - enrolls known faces in localStorage
*/

// ----- helpers -----
const $ = id => document.getElementById(id);
const formatTS = ts => new Date(ts).toLocaleString();

// ----- UI elements -----
const video = $('camera');
const canvas = $('overlay');
const ctx = canvas.getContext('2d');
const startCamBtn = $('startCamBtn');
const captureBtn = $('captureBtn');
const toast = $('toast');
const toastThumb = $('toast-thumb');
const toastText = $('toast-text');
const markSafeBtn = $('markSafeBtn');
const ignoreBtn = $('ignoreBtn');
const eventsList = $('events');
const connStatus = $('conn');

// enroll modal
const enrollModal = $('enrollModal');
const enrollThumb = $('enroll-thumb');
const enrollName = $('enroll-name');
const enrollSaveBtn = $('enrollSaveBtn');
const enrollCancelBtn = $('enrollCancelBtn');

// state
let overlayBoxes = []; // current boxes to draw
let events = [];       // stored events
let knownDB = {};      // local known faces DB (id -> name)
let mockInterval = null;

// ----- localStorage persistence -----
function loadState(){
  const k = localStorage.getItem('door_known_db');
  knownDB = k ? JSON.parse(k) : {};
  const e = localStorage.getItem('door_events');
  events = e ? JSON.parse(e) : [];
  renderEvents();
}
function saveKnownDB(){
  localStorage.setItem('door_known_db', JSON.stringify(knownDB));
}
function saveEvents(){
  localStorage.setItem('door_events', JSON.stringify(events));
}

// ----- camera setup -----
async function startCamera(){
  try{
    const stream = await navigator.mediaDevices.getUserMedia({video:{facingMode:"environment"}, audio:false});
    video.srcObject = stream;
    await video.play();
    resizeCanvas();
  }catch(err){
    console.warn('Camera not accessible:', err);
    // fallback: show a placeholder stream (could set a video src to file)
  }
}
function resizeCanvas(){
  canvas.width = video.clientWidth;
  canvas.height = video.clientHeight;
  canvas.style.width = video.clientWidth + 'px';
  canvas.style.height = video.clientHeight + 'px';
}

// draw loop for overlay
function drawOverlay(){
  ctx.clearRect(0,0,canvas.width,canvas.height);
  for(const b of overlayBoxes){
    // b: {x,y,w,h,label,confidence}
    ctx.lineWidth = 2;
    ctx.strokeStyle = b.label==='unknown' ? 'rgba(237,100,101,0.9)' : 'rgba(45,212,191,0.98)';
    ctx.strokeRect(b.x, b.y, b.w, b.h);
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    ctx.fillRect(b.x, b.y - 22, Math.min(180, b.w), 22);
    ctx.fillStyle = '#fff';
    ctx.font = '14px sans-serif';
    ctx.fillText(`${b.label} (${Math.round(b.confidence*100)}%)`, b.x + 6, b.y - 6);
  }
  requestAnimationFrame(drawOverlay);
}

// ----- event creation & UI -----
function captureThumbnail(box){
  // capture current frame and crop to box
  const tmp = document.createElement('canvas');
  const vW = video.videoWidth || canvas.width;
  const vH = video.videoHeight || canvas.height;
  tmp.width = Math.max(1, box.w);
  tmp.height = Math.max(1, box.h);
  const tctx = tmp.getContext('2d');
  // map from displayed coords -> video pixel coords
  const scaleX = (video.videoWidth || vW) / canvas.width;
  const scaleY = (video.videoHeight || vH) / canvas.height;
  tctx.drawImage(video,
    box.x * scaleX, box.y * scaleY, box.w * scaleX, box.h * scaleY,
    0,0, tmp.width, tmp.height
  );
  return tmp.toDataURL('image/jpeg', 0.7);
}

function addEvent(detection){
  // detection: {id, bbox:{x,y,w,h}, label, confidence, timestamp}
  const thumb = captureThumbnail(detection.bbox);
  const ev = {
    id: detection.id,
    thumb,
    label: detection.label,
    confidence: detection.confidence,
    ts: detection.timestamp
  };
  events.unshift(ev);
  if(events.length>100) events.pop();
  saveEvents();
  renderEvents();
  // show toast for unknowns
  if(detection.label === 'unknown'){
    showToast(ev);
  }
}

function renderEvents(){
  eventsList.innerHTML = '';
  for(const ev of events){
    const li = document.createElement('li');
    li.className = 'event';
    li.innerHTML = `
      <img src="${ev.thumb}" alt="thumb">
      <div class="meta">
        <strong>${ev.label}</strong>
        <small>${formatTS(ev.ts)} — ${Math.round(ev.confidence*100)}%</small>
      </div>
      <div style="margin-left:auto">
        <button class="secondary" onclick="markEventSafe('${ev.id}')">Mark Safe</button>
      </div>
    `;
    eventsList.appendChild(li);
  }
}

// quick mark safe from list
window.markEventSafe = function(id){
  const ev = events.find(e=>e.id===id);
  if(!ev) return;
  openEnrollModal(ev.thumb, ev.id);
}

// ----- toast / enroll interactions -----
function showToast(ev){
  toastThumb.src = ev.thumb;
  toastText.textContent = `Unknown detected — ${formatTS(ev.ts)}`;
  toast.classList.remove('hidden');
  // store currentCandidate for enroll
  toast.dataset.evId = ev.id;
}
markSafeBtn.onclick = () => {
  const evId = toast.dataset.evId;
  const ev = events.find(e=>e.id===evId);
  if(!ev) return;
  openEnrollModal(ev.thumb, ev.id);
};
ignoreBtn.onclick = () => {
  toast.classList.add('hidden');
};

function openEnrollModal(thumbDataUrl, sourceEventId){
  enrollThumb.src = thumbDataUrl;
  enrollName.value = '';
  enrollModal.classList.remove('hidden');
  enrollModal.dataset.srcEvent = sourceEventId;
}

enrollCancelBtn.onclick = ()=> enrollModal.classList.add('hidden');

enrollSaveBtn.onclick = ()=>{
  const name = enrollName.value.trim();
  const evId = enrollModal.dataset.srcEvent;
  if(!name){ alert('Enter a name'); return; }
  // create a simple known id mapping
  knownDB[evId] = name;
  saveKnownDB();
  // update any events with this id
  for(const ev of events) if(ev.id===evId) ev.label = name;
  saveEvents();
  renderEvents();
  enrollModal.classList.add('hidden');
  toast.classList.add('hidden');
};

// ----- mock detections / "WebSocket" -----
function startMockDetections(){
  connStatus.textContent = 'mock';
  // generate a detection every ~3-6s
  if(mockInterval) clearInterval(mockInterval);
  mockInterval = setInterval(()=>{
    // generate random box
    const cw = canvas.width, ch = canvas.height;
    const w = Math.floor(Math.max(60, cw * (0.15 + Math.random()*0.2)));
    const h = Math.floor(w * (0.9 + Math.random()*0.25));
    const x = Math.floor(Math.random()*(cw - w - 10));
    const y = Math.floor(Math.random()*(ch - h - 10));
    const isKnown = Math.random() < 0.35; // 35% chance known (mock)
    const id = 'evt_' + Math.random().toString(36).slice(2,9);
    const label = isKnown ? `Person_${Math.floor(Math.random()*8)+1}` : 'unknown';
    const confidence = 0.82 + Math.random()*0.15;
    // detection payload format:
    const det = {
      id,
      bbox: {x,y,w,h},
      label,
      confidence,
      timestamp: Date.now()
    };
    // simulate receiving detection via WS
    onDetection(det);
  }, 3000 + Math.random()*3000);
}

function onDetection(det){
  // transform bbox to displayed coords (already in displayed coords from mock)
  // update overlayBoxes (show for a short time)
  overlayBoxes = [{
    x: det.bbox.x,
    y: det.bbox.y,
    w: det.bbox.w,
    h: det.bbox.h,
    label: det.label,
    confidence: det.confidence
  }];
  // create event
  addEvent(det);
  // after some seconds, clear overlay
  setTimeout(()=>{ overlayBoxes = []; }, 2200);
}

// ----- manual capture button -----
captureBtn.onclick = ()=>{
  if(!overlayBoxes.length) {
    // capture full frame if no box
    const tmp = document.createElement('canvas');
    tmp.width = video.videoWidth || canvas.width;
    tmp.height = video.videoHeight || canvas.height;
    tmp.getContext('2d').drawImage(video, 0, 0, tmp.width, tmp.height);
    const data = tmp.toDataURL('image/jpeg', 0.8);
    const id = 'manual_' + Date.now().toString(36);
    const ev = { id, thumb: data, label: 'manual', confidence: 0, ts: Date.now() };
    events.unshift(ev); saveEvents(); renderEvents();
    return;
  }
  // otherwise capture the first overlay box
  const box = overlayBoxes[0];
  const thumb = captureThumbnail(box);
  const id = 'manual_' + Date.now().toString(36);
  const ev = { id, thumb, label: box.label, confidence: box.confidence, ts: Date.now() };
  events.unshift(ev); saveEvents(); renderEvents();
};

// ----- start/stop UI -----
startCamBtn.onclick = async ()=>{
  await startCamera();
  resizeCanvas();
};

// handle resize
window.addEventListener('resize', resizeCanvas);

// kick off
loadState();
drawOverlay();
startMockDetections();

// try start camera automatically (user may need to click to allow)
startCamera().catch(()=>{ /* user can click Start Camera */ });
