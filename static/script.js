// ---------------------------------------------------------------------------
// Tab switching
// ---------------------------------------------------------------------------
let activeTab = 'text';

function switchTab(tab) {
    activeTab = tab;
    document.getElementById('tab-text').classList.toggle('active', tab === 'text');
    document.getElementById('tab-file').classList.toggle('active', tab === 'file');
    document.getElementById('panel-text').classList.toggle('hidden', tab !== 'text');
    document.getElementById('panel-file').classList.toggle('hidden', tab !== 'file');
}

// ---------------------------------------------------------------------------
// Drag-and-drop file zone
// ---------------------------------------------------------------------------
let selectedFile = null;

const dropZone  = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileNameEl = document.getElementById('file-name');

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) setFile(file);
});

fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) setFile(fileInput.files[0]);
});

// Clicking anywhere on drop zone triggers file browser (except the label itself)
dropZone.addEventListener('click', (e) => {
    if (e.target.tagName !== 'LABEL') fileInput.click();
});

function setFile(file) {
    selectedFile = file;
    fileNameEl.textContent = `📎 ${file.name}`;
    fileNameEl.classList.remove('hidden');
    dropZone.style.borderColor = 'var(--primary)';
}

// ---------------------------------------------------------------------------
// Main generate button
// ---------------------------------------------------------------------------
document.getElementById('speak-btn').addEventListener('click', async () => {
    const btn       = document.getElementById('speak-btn');
    const btnText   = btn.querySelector('.btn-text');
    const spinner   = btn.querySelector('.spinner');
    const results   = document.getElementById('results-panel');
    const audioPlayer = document.getElementById('audioPlayer');
    const voice     = document.getElementById('voice-select').value;

    // Validate inputs
    if (activeTab === 'text' && !document.getElementById('text').value.trim()) {
        alert('Please enter some text first.');
        return;
    }
    if (activeTab === 'file' && !selectedFile) {
        alert('Please select a file first.');
        return;
    }

    // Loading state
    btn.disabled = true;
    btnText.textContent = 'Analyzing…';
    spinner.classList.remove('hidden');

    try {
        let response;

        if (activeTab === 'text') {
            // ── JSON text request ──────────────────────────────────────
            response = await fetch('/api/synthesize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: document.getElementById('text').value,
                    voice,
                    force_recompute: true
                })
            });
        } else {
            // ── Multipart file upload ──────────────────────────────────
            const formData = new FormData();
            formData.append('file', selectedFile);
            formData.append('voice', voice);
            formData.append('force_recompute', 'true');

            response = await fetch('/api/synthesize-file', {
                method: 'POST',
                body: formData
            });
        }

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || `Server error ${response.status}`);
        }

        // ── Parse headers ──────────────────────────────────────────────
        const emotion    = response.headers.get('X-Detected-Emotion') || 'neutral';
        const confidence = parseFloat(response.headers.get('X-Emotion-Confidence')) || 0;
        const rate       = response.headers.get('X-Prosody-Rate') || '140';
        const pitch      = response.headers.get('X-Prosody-Pitch') || '0st';
        const volume     = response.headers.get('X-Prosody-Volume-db') || '+0dB';

        let segments = [];
        try { segments = JSON.parse(response.headers.get('X-Segments') || '[]'); } catch (_) {}

        updateTopMetrics(emotion, confidence, rate, pitch, volume);
        renderSegments(segments);

        // ── Audio ──────────────────────────────────────────────────────
        const blob = await response.blob();
        audioPlayer.src = URL.createObjectURL(blob);
        results.classList.remove('hidden');
        audioPlayer.play();

    } catch (err) {
        console.error(err);
        alert('Error: ' + err.message);
    } finally {
        btn.disabled = false;
        btnText.textContent = 'Generate Speech';
        spinner.classList.add('hidden');
    }
});

// ---------------------------------------------------------------------------
// Emotion colour helpers
// ---------------------------------------------------------------------------
const EMOTION_COLORS = {
    joy:     '#10b981',
    love:    '#ec4899',
    sadness: '#3b82f6',
    anger:   '#ef4444',
    fear:    '#f59e0b',
    surprise:'#d946ef',
    neutral: '#64748b',
};

const JOY_GRP      = ["joy","excitement","amusement","optimism"];
const LOVE_GRP     = ["love","caring","admiration","approval","pride","gratitude","relief"];
const SADNESS_GRP  = ["sadness","disappointment","embarrassment","grief","remorse"];
const ANGER_GRP    = ["anger","annoyance","disapproval","disgust"];
const FEAR_GRP     = ["fear","nervousness"];
const SURPRISE_GRP = ["surprise","realization","confusion","curiosity","desire"];

function emotionColor(e) {
    e = e.toLowerCase();
    if (JOY_GRP.includes(e))      return EMOTION_COLORS.joy;
    if (LOVE_GRP.includes(e))     return EMOTION_COLORS.love;
    if (SADNESS_GRP.includes(e))  return EMOTION_COLORS.sadness;
    if (ANGER_GRP.includes(e))    return EMOTION_COLORS.anger;
    if (FEAR_GRP.includes(e))     return EMOTION_COLORS.fear;
    if (SURPRISE_GRP.includes(e)) return EMOTION_COLORS.surprise;
    return EMOTION_COLORS.neutral;
}

// ---------------------------------------------------------------------------
// UI updaters
// ---------------------------------------------------------------------------
function updateTopMetrics(emotion, confidence, rate, pitch, volume) {
    const badge   = document.getElementById('emotion-badge');
    const confBar = document.getElementById('confidence-bar');
    const confTxt = document.getElementById('confidence-text');

    document.getElementById('rate-val').textContent = `${rate} wpm`;
    document.getElementById('pitch-val').textContent = pitch;
    document.getElementById('vol-val').textContent   = volume;

    const color = emotionColor(emotion);
    badge.textContent = emotion;
    badge.style.backgroundColor = color;

    document.querySelectorAll('.card.glass').forEach(c => {
        c.style.boxShadow = `0 8px 32px 0 ${color}40`;
    });

    const pct = Math.round(confidence * 100);
    confTxt.textContent = `${pct}%`;
    setTimeout(() => {
        confBar.style.width           = `${pct}%`;
        confBar.style.backgroundColor = color;
    }, 100);
}

function renderSegments(segments) {
    const container = document.getElementById('segments-container');
    const list      = document.getElementById('segments-list');
    list.innerHTML  = '';

    if (!segments || segments.length === 0) { container.classList.add('hidden'); return; }

    segments.forEach((seg, idx) => {
        const color = emotionColor(seg.emotion);
        const pct   = Math.round(seg.confidence * 100);

        const card = document.createElement('div');
        card.className = 'segment-card';
        card.style.borderLeftColor = color;

        card.innerHTML = `
            <div class="seg-header">
                <span class="seg-num">Segment ${idx + 1}</span>
                <span class="seg-badge" style="background:${color}">${seg.emotion}</span>
                <span class="seg-conf">${pct}%</span>
            </div>
            <p class="seg-text">"${seg.text}"</p>
            <div class="seg-params">
                <span>🎵 ${seg.pitch}</span>
                <span>⚡ ${seg.rate} wpm</span>
                <span>🔊 ${seg.volume}</span>
            </div>
            <div class="seg-bar-bg">
                <div class="seg-bar" style="width:${pct}%; background:${color}"></div>
            </div>`;

        list.appendChild(card);
    });

    container.classList.remove('hidden');
}
