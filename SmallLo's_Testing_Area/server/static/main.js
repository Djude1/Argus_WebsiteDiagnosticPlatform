// main.js - WebSocket client for video viewer and detection results

const canvas = document.getElementById("videoCanvas");
const ctx = canvas.getContext("2d");

const viewerDot = document.getElementById("viewerDot");
const viewerStatus = document.getElementById("viewerStatus");
const detDot = document.getElementById("detDot");
const detStatus = document.getElementById("detStatus");
const fpsEl = document.getElementById("fps");
const inferenceMsEl = document.getElementById("inferenceMs");
const objCountEl = document.getElementById("objCount");
const detectionList = document.getElementById("detectionList");

// FPS tracking
let frameCount = 0;
let lastFpsTime = performance.now();

function updateFps() {
    frameCount++;
    const now = performance.now();
    const elapsed = now - lastFpsTime;
    if (elapsed >= 1000) {
        fpsEl.textContent = Math.round((frameCount / elapsed) * 1000);
        frameCount = 0;
        lastFpsTime = now;
    }
}

// ─── Video Viewer WebSocket ───
function connectViewer() {
    const wsUrl = `ws://${location.host}/ws/viewer`;
    const ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
        viewerDot.className = "status-dot connected";
        viewerStatus.textContent = "Connected";
        // Send periodic keepalive
        setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send("ping");
            }
        }, 5000);
    };

    ws.onmessage = (event) => {
        const blob = new Blob([event.data], { type: "image/jpeg" });
        const url = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => {
            canvas.width = img.width;
            canvas.height = img.height;
            ctx.drawImage(img, 0, 0);
            URL.revokeObjectURL(url);
            updateFps();
        };
        img.src = url;
    };

    ws.onclose = () => {
        viewerDot.className = "status-dot disconnected";
        viewerStatus.textContent = "Disconnected";
        setTimeout(connectViewer, 2000);
    };

    ws.onerror = () => ws.close();
}

// ─── Detections WebSocket ───
function connectDetections() {
    const wsUrl = `ws://${location.host}/ws/detections`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        detDot.className = "status-dot connected";
        detStatus.textContent = "Connected";
        setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send("ping");
            }
        }, 5000);
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            // Update stats
            inferenceMsEl.textContent = `${data.inference_time_ms || 0} ms`;
            const dets = data.detections || [];
            objCountEl.textContent = dets.length;

            // Update detection list
            detectionList.innerHTML = "";
            for (const det of dets) {
                const div = document.createElement("div");
                div.className = "detection-item";
                div.innerHTML = `
                    <span class="cls">${det.class_name}</span>
                    <span class="conf">${(det.confidence * 100).toFixed(1)}%</span>
                `;
                detectionList.appendChild(div);
            }
        } catch (e) {
            console.error("Failed to parse detection data:", e);
        }
    };

    ws.onclose = () => {
        detDot.className = "status-dot disconnected";
        detStatus.textContent = "Disconnected";
        setTimeout(connectDetections, 2000);
    };

    ws.onerror = () => ws.close();
}

// Start connections
connectViewer();
connectDetections();
