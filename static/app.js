// --- Session & WebSocket Setup ---

const sessionId = crypto.randomUUID();
let ws = null;
let currentAssistantMsg = null;
let isSubmitted = false;

function connect() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${location.host}/ws/${sessionId}`);

    ws.onopen = () => {
        console.log("Connected");
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleMessage(data);
    };

    ws.onclose = () => {
        console.log("Disconnected — reconnecting in 2s");
        setTimeout(connect, 2000);
    };

    ws.onerror = (err) => {
        console.error("WebSocket error:", err);
    };
}

// --- Message Handling ---

function handleMessage(data) {
    switch (data.type) {
        case "assistant_message":
            appendAssistantMessage(data.content);
            break;

        case "assistant_chunk":
            appendChunk(data.content);
            break;

        case "assistant_done":
            finalizeAssistantMessage();
            break;

        case "quality_update":
            updateQualityMeter(data.completeness, data.quality);
            updateCollectedData(data.blip_data);
            updateMissingFields(data.missing_fields, data.ring_gaps);
            break;

        case "submission_complete":
            showSubmissionBanner(data.quality_score);
            isSubmitted = true;
            break;

        case "error":
            appendAssistantMessage("Error: " + data.content);
            break;
    }
}

// --- Chat UI ---

function appendUserMessage(text) {
    const el = document.createElement("div");
    el.className = "message user";
    el.textContent = text;
    document.getElementById("messages").appendChild(el);
    scrollToBottom();
}

function appendAssistantMessage(text) {
    const el = document.createElement("div");
    el.className = "message assistant";
    el.textContent = text;
    document.getElementById("messages").appendChild(el);
    currentAssistantMsg = null;
    scrollToBottom();
}

function appendChunk(text) {
    if (!currentAssistantMsg) {
        currentAssistantMsg = document.createElement("div");
        currentAssistantMsg.className = "message assistant";
        document.getElementById("messages").appendChild(currentAssistantMsg);
    }
    currentAssistantMsg.textContent += text;
    scrollToBottom();
}

function finalizeAssistantMessage() {
    currentAssistantMsg = null;
}

function scrollToBottom() {
    const container = document.getElementById("messages");
    container.scrollTop = container.scrollHeight;
}

// --- User Actions ---

function sendMessage() {
    const input = document.getElementById("message-input");
    const text = input.value.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

    appendUserMessage(text);
    ws.send(JSON.stringify({ action: "message", message: text }));
    input.value = "";
    input.focus();
}

function submitBlip() {
    if (isSubmitted) return;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    const input = document.getElementById("message-input");
    const text = input.value.trim();

    appendUserMessage(text || "I'd like to submit this blip now.");
    ws.send(JSON.stringify({
        action: "submit",
        message: text || "I'd like to submit this blip now.",
    }));
    input.value = "";
}

function resetSession() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    document.getElementById("messages").innerHTML = "";
    isSubmitted = false;
    currentAssistantMsg = null;

    ws.send(JSON.stringify({ action: "reset" }));
    closeBanner();
}

// Handle Enter to send (Shift+Enter for newline)
document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("message-input");
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
});

// --- Quality Meter ---

function updateQualityMeter(completeness, quality) {
    updateBar("completeness", completeness);
    updateBar("quality", quality);
}

function updateBar(id, value) {
    const bar = document.getElementById(`${id}-bar`);
    const label = document.getElementById(`${id}-value`);

    bar.style.width = `${value}%`;
    label.textContent = `${Math.round(value)}%`;

    bar.className = "meter-fill";
    if (value >= 67) {
        bar.classList.add("green");
    } else if (value >= 34) {
        bar.classList.add("yellow");
    }
    // Default (red) is already the base style
}

// --- Collected Data Display ---

const FIELD_LABELS = {
    name: "Name",
    quadrant: "Quadrant",
    ring: "Ring",
    description: "Description",
    client_references: "Client References",
    submitter_name: "Submitter",
    submitter_contact: "Contact",
    why_now: "Why Now",
    alternatives_considered: "Alternatives",
    strengths: "Strengths",
    weaknesses: "Weaknesses",
    is_resubmission: "Resubmission",
    resubmission_rationale: "Rationale",
};

function updateCollectedData(blipData) {
    const container = document.getElementById("collected-data");

    if (!blipData || Object.keys(blipData).length === 0) {
        container.innerHTML = '<p class="empty-state">No data collected yet</p>';
        return;
    }

    let html = "";
    for (const [key, label] of Object.entries(FIELD_LABELS)) {
        const value = blipData[key];
        if (value === undefined || value === null) continue;

        let display;
        if (Array.isArray(value)) {
            display = value.length > 0 ? value.join("; ") : "—";
        } else if (typeof value === "boolean") {
            display = value ? "Yes" : "No";
        } else {
            // Truncate long descriptions for the sidebar
            display = String(value);
            if (display.length > 120) {
                display = display.substring(0, 117) + "...";
            }
        }

        html += `<div class="data-field">
            <div class="field-label">${label}</div>
            <div class="field-value">${escapeHtml(display)}</div>
        </div>`;
    }

    container.innerHTML = html || '<p class="empty-state">No data collected yet</p>';
}

function updateMissingFields(missingFields, ringGaps) {
    const container = document.getElementById("missing-fields");
    let html = "";

    if (ringGaps && ringGaps.length > 0) {
        for (const gap of ringGaps) {
            html += `<div class="missing-item">${escapeHtml(gap)}</div>`;
        }
    }

    if (missingFields && missingFields.length > 0) {
        for (const field of missingFields) {
            const label = FIELD_LABELS[field] || field.replace(/_/g, " ");
            html += `<div class="missing-item">${escapeHtml(label)}</div>`;
        }
    }

    container.innerHTML = html || '<p class="empty-state">Looking good! All key fields covered.</p>';
}

// --- Submission Banner ---

function showSubmissionBanner(score) {
    const banner = document.getElementById("submission-banner");
    document.getElementById("submission-score").textContent =
        ` Quality score: ${Math.round(score)}%`;
    banner.classList.remove("hidden");
}

function closeBanner() {
    document.getElementById("submission-banner").classList.add("hidden");
}

// --- Utilities ---

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// --- Init ---
connect();
