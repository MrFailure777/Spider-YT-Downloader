// elements
const openButtons = document.querySelectorAll(".open-btn");
const formArea = document.getElementById("formArea");
const formTitle = document.getElementById("formTitle");
const videoUrlInput = document.getElementById("videoUrl");
const startDownloadBtn = document.getElementById("startDownload");
const closeFormBtn = document.getElementById("closeForm");
const progressBox = document.getElementById("progressBox");
const progressText = document.getElementById("progressText");
const errorBox = document.getElementById("errorBox");

let currentMode = null;
let currentJobId = null;

// open form when clicking card
openButtons.forEach(btn => {
  btn.addEventListener("click", (e) => {
    currentMode = btn.dataset.mode;
    formTitle.textContent = (currentMode === "mp3") ? "MP3 Download" : (currentMode === "mp4") ? "Video Download" : "Playlist Download";
    videoUrlInput.value = "";
    progressBox.style.display = "none";
    errorBox.style.display = "none";
    formArea.setAttribute("aria-hidden", "false");
  });
});

// close form
closeFormBtn.addEventListener("click", () => {
  formArea.setAttribute("aria-hidden", "true");
});

// start download
startDownloadBtn.addEventListener("click", async () => {
  const url = videoUrlInput.value.trim();
  if (!url) {
    alert("Please enter a URL");
    return;
  }
  // start job
  progressBox.style.display = "block";
  progressText.textContent = "Queued...";
  errorBox.style.display = "none";
  try {
    const resp = await fetch("/start_download", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ url, mode: currentMode })
    });
    if (!resp.ok) {
      const txt = await resp.text();
      throw new Error(txt || "Failed to start download");
    }
    const json = await resp.json();
    currentJobId = json.job_id;
    pollProgress(currentJobId);
  } catch (err) {
    errorBox.style.display = "block";
    errorBox.textContent = err.message || "Error";
  }
});

let pollInterval = null;
async function pollProgress(jobId) {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/progress/${jobId}`);
      if (!res.ok) {
        throw new Error("Job not found");
      }
      const j = await res.json();
      if (j.status === "running") {
        progressText.textContent = `${j.progress || 0}% done`; // Showing Percentage
      } else if (j.status === "queued") {
        progressText.textContent = "Queued...";
      } else if (j.status === "finished") {
        progressText.textContent = "100% - Ready";
        clearInterval(pollInterval);
        // trigger file download (this will open Save As)
        window.location = `/download_file/${jobId}`;
        // hide form after a short delay
        setTimeout(()=> formArea.setAttribute("aria-hidden","true"), 800);
      } else if (j.status === "error") {
        clearInterval(pollInterval);
        progressText.textContent = "Error";
        errorBox.style.display = "block";
        errorBox.textContent = j.error || "Download error";
      }
    } catch (err) {
      clearInterval(pollInterval);
      errorBox.style.display = "block";
      errorBox.textContent = err.message;
    }
  }, 1000);
}

