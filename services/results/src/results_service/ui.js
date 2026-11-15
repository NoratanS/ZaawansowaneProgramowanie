// Shared by the single (/) and batch (/batch) pages: token, page config,
// submitting to the Analysis Service, polling Results and drawing boxes.
"use strict";

const TOKEN_KEY = "people-counter-token";
const FAST_POLL_MS = 1000;
const SLOW_POLL_MS = 5000;
const FAST_FOR_MS = 30 * 1000;
const GIVE_UP_AFTER_MS = 10 * 60 * 1000;
const BOX_COLOUR = "#ff2d55";

// Keeps the token field in localStorage. It can throw (private mode,
// blocked storage); the page works without it.
function bindToken(input) {
  try { input.value = localStorage.getItem(TOKEN_KEY) || ""; } catch {}
  input.addEventListener("input", () => {
    try { localStorage.setItem(TOKEN_KEY, input.value.trim()); } catch {}
  });
  return () => input.value.trim();
}

let analysisUrl = null;
async function getAnalysisUrl() {
  if (analysisUrl === null) {
    // Relative URLs keep working when the Results Service sits under a path.
    const response = await fetch("ui-config");
    if (!response.ok) throw new Error(`ui-config answered ${response.status}`);
    analysisUrl = (await response.json()).analysis_url;
  }
  return analysisUrl;
}

// POST to the Analysis Service. Returns the 202 body or throws an Error
// whose message is ready to show.
async function postToAnalysis(path, token, init) {
  let url;
  try {
    url = await getAnalysisUrl();
  } catch (error) {
    throw new Error(`Could not load the page config (${error.message}).`);
  }
  const headers = { ...init.headers, "Authorization": `Bearer ${token}` };
  let response;
  try {
    response = await fetch(`${url}${path}`, { ...init, method: "POST", headers });
  } catch (error) {
    // A CORS block also lands here: open the page at RESULTS_PUBLIC_URL exactly.
    throw new Error(`Could not reach the Analysis Service (${error.message}).`);
  }
  const body = await response.json().catch(() => ({}));
  if (response.status !== 202) {
    throw new Error(`Rejected: ${response.status} ${describeDetail(body.detail)}`);
  }
  return body;
}

// Uploads files in one request; the 202 body lists one job per file.
function uploadFiles(files, token) {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  // No Content-Type: the browser sets it with the multipart boundary.
  return postToAnalysis("/uploads", token, { body: form });
}

function describeDetail(detail) {
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join("; ");
  return detail || "";
}

// Polls a result_url every 1 s, every 5 s after 30 s, and gives up after
// 10 min. Calls onResult(result) or onGiveUp() once, unless isCancelled()
// turns true first.
function pollResult(resultUrl, { onResult, onGiveUp, isCancelled = () => false }) {
  const startedAt = Date.now();
  const tick = async () => {
    if (isCancelled()) return;
    const elapsed = Date.now() - startedAt;
    if (elapsed >= GIVE_UP_AFTER_MS) {
      onGiveUp();
      return;
    }
    try {
      const response = await fetch(resultUrl);
      if (isCancelled()) return;
      if (response.ok) {
        onResult(await response.json());
        return;
      }
    } catch {}
    // 404 (not delivered yet) or a network blip: try again later.
    setTimeout(tick, elapsed < FAST_FOR_MS ? FAST_POLL_MS : SLOW_POLL_MS);
  };
  tick();
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    // No crossOrigin: a tainted canvas still draws, and images from hosts
    // without CORS headers still load. Object URLs never taint it.
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`Could not load ${src} in the browser.`));
    image.src = src;
  });
}

// Draws the image at full size with its boxes, which are in pixels of the
// original image, the canvas's own units.
function drawDetections(canvas, image, detections) {
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext("2d");
  context.drawImage(image, 0, 0);
  context.lineWidth = Math.max(2, Math.round(image.naturalWidth / 300));
  context.strokeStyle = BOX_COLOUR;
  for (const box of detections) {
    context.strokeRect(box.x, box.y, box.width, box.height);
  }
}
