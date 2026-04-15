document.getElementById('speak-btn').addEventListener('click', async () => {
    const textInput = document.getElementById('text').value;
    if (!textInput.trim()) return;

    const btn        = document.getElementById('speak-btn');
    const btnText    = btn.querySelector('.btn-text');
    const spinner    = btn.querySelector('.spinner');
    const results    = document.getElementById('results-panel');
    const audioPlayer = document.getElementById('audioPlayer');
    const voiceSelect = document.getElementById('voice-select').value;

    // Loading state
    btn.disabled = true;
    btnText.textContent = "Analyzing...";
    spinner.classList.remove('hidden');

    try {
        const response = await fetch('/api/synthesize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: textInput, voice: voiceSelect, force_recompute: true })
        });

        if (!response.ok) {
            const detail = await response.json().catch(() => ({}));
            throw new Error(detail.detail || `Server error ${response.status}`);
        }

        // ---- top-level headers (dominant segment) ----
        const emotion    = response.headers.get('X-Detected-Emotion') || 'neutral';
        const confidence = parseFloat(response.headers.get('X-Emotion-Confidence')) || 0;
        const rate       = response.headers.get('X-Prosody-Rate') || '140';
        const pitch      = response.headers.get('X-Prosody-Pitch') || '0st';
        const volume     = response.headers.get('X-Prosody-Volume-db') || '+0dB';

        // ---- per-segment breakdown ----
        let segments = [];
        try {
            const raw = response.headers.get('X-Segments');
            if (raw) segments = JSON.parse(raw);
        } catch (_) {}

        updateTopMetrics(emotion, confidence, rate, pitch, volume);
        renderSegments(segments);

        // ---- audio ----
        const blob = await response.blob();
        audioPlayer.src = URL.createObjectURL(blob);
        results.classList.remove('hidden');
        audioPlayer.play();

    } catch (err) {
        console.error(err);
        alert('Error: ' + err.message);
    } finally {
        btn.disabled = false;
        btnText.textContent = "Generate Speech";
        spinner.classList.add('hidden');
    }
});

// ---------------------------------------------------------------------------
// Emotion colour palette  (covers GoEmotions 28 categories via grouping)
// ---------------------------------------------------------------------------
const EMOTION_COLORS = {
    joy:      '#10b981',
    love:     '#ec4899',
    sadness:  '#3b82f6',
    anger:    '#ef4444',
    fear:     '#f59e0b',
    surprise: '#d946ef',
    neutral:  '#64748b',
};

const JOY_GROUP      = ["joy","excitement","amusement","optimism"];
const LOVE_GROUP     = ["love","caring","admiration","approval","pride","gratitude","relief"];
const SADNESS_GROUP  = ["sadness","disappointment","embarrassment","grief","remorse"];
const ANGER_GROUP    = ["anger","annoyance","disapproval","disgust"];
const FEAR_GROUP     = ["fear","nervousness"];
const SURPRISE_GROUP = ["surprise","realization","confusion","curiosity","desire"];

function emotionColor(emotion) {
    const e = emotion.toLowerCase();
    if (JOY_GROUP.includes(e))      return EMOTION_COLORS.joy;
    if (LOVE_GROUP.includes(e))     return EMOTION_COLORS.love;
    if (SADNESS_GROUP.includes(e))  return EMOTION_COLORS.sadness;
    if (ANGER_GROUP.includes(e))    return EMOTION_COLORS.anger;
    if (FEAR_GROUP.includes(e))     return EMOTION_COLORS.fear;
    if (SURPRISE_GROUP.includes(e)) return EMOTION_COLORS.surprise;
    return EMOTION_COLORS.neutral;
}

// ---------------------------------------------------------------------------
// Update top-level dominant-emotion metrics
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

    // Glow the card
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

// ---------------------------------------------------------------------------
// Render per-segment breakdown cards
// ---------------------------------------------------------------------------
function renderSegments(segments) {
    const container = document.getElementById('segments-container');
    const list      = document.getElementById('segments-list');
    list.innerHTML  = '';

    if (!segments || segments.length === 0) {
        container.classList.add('hidden');
        return;
    }

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
            </div>
        `;

        list.appendChild(card);
    });

    container.classList.remove('hidden');
}
