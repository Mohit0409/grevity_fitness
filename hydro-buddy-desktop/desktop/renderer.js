const REMINDER_TEXT = "Get up, stretch your body, and drink water.";
const ROWS = {
    idle: { row: 0, frames: 6, delay: 170 },
    "running-right": { row: 1, frames: 8, delay: 120 },
    "running-left": { row: 2, frames: 8, delay: 120 },
    waving: { row: 3, frames: 4, delay: 150 },
    jumping: { row: 4, frames: 5, delay: 145 },
    failed: { row: 5, frames: 8, delay: 160 },
    waiting: { row: 6, frames: 6, delay: 160 },
    running: { row: 7, frames: 6, delay: 130 },
    review: { row: 8, frames: 6, delay: 160 }
};

const pet = document.querySelector("#petSprite");
const speech = document.querySelector("#speechBubble");
const statusPill = document.querySelector("#statusPill");

let frameTimer = 0;
let currentFrame = 0;
let voiceMuted = false;

function setPetState(name) {
    const config = ROWS[name] || ROWS.idle;
    currentFrame = 0;
    window.clearInterval(frameTimer);
    pet.style.setProperty("--row", String(config.row));
    pet.style.setProperty("--frame", "0");
    frameTimer = window.setInterval(() => {
        currentFrame = (currentFrame + 1) % config.frames;
        pet.style.setProperty("--frame", String(currentFrame));
    }, config.delay);
}

function say(text) {
    if (voiceMuted || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.94;
    utterance.pitch = 1.08;
    window.speechSynthesis.speak(utterance);
}

function setSpeech(text) {
    speech.textContent = text;
}

window.hydroBuddy.onPetState((state) => {
    setPetState(state);
});

window.hydroBuddy.onReminder((payload = {}) => {
    const text = typeof payload === "string" ? payload : payload.text || REMINDER_TEXT;
    setSpeech(text);
    if (typeof payload === "string" || payload.speakInRenderer) say(text);
    window.setTimeout(() => setPetState("jumping"), 1300);
});

window.hydroBuddy.onState((state) => {
    voiceMuted = Boolean(state.voiceMuted);
    statusPill.textContent = state.remindersRunning
        ? voiceMuted ? "Running · muted" : "Running"
        : voiceMuted ? "Stopped · muted" : "Stopped";
    if (!state.remindersRunning) setSpeech("Hydro Buddy is resting.");
    if (state.remindersRunning) setSpeech("Hydro Buddy is watching the clock.");
});

window.addEventListener("beforeunload", () => {
    window.clearInterval(frameTimer);
});

setPetState("running");
window.hydroBuddy.ready();
