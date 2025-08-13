const modal = document.getElementById("playlistModal");
const closeModal = document.getElementById("closeModal");

document.getElementById("playlistForm").addEventListener("submit", function(e) {
    e.preventDefault();
    const url = document.getElementById("playlist_url").value;
    const formData = new FormData();
    formData.append("playlist_url", url);

    fetch("/get_playlist_videos", {
        method: "POST",
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        const playlistVideosDiv = document.getElementById("playlistVideos");
        playlistVideosDiv.innerHTML = "";
        if (data.error) {
            alert(data.error);
            return;
        }
        data.forEach(video => {
            const videoDiv = document.createElement("div");
            videoDiv.classList.add("video-item");
            videoDiv.innerHTML = `
                <input type="checkbox" value="${video.url}">
                <img src="${video.thumbnail}" alt="Thumbnail">
                <span>${video.title}</span>
            `;
            playlistVideosDiv.appendChild(videoDiv);
        });
        modal.style.display = "flex"; // Show popup
    });
});

closeModal.addEventListener("click", () => {
    modal.style.display = "none";
});

document.getElementById("downloadSelected").addEventListener("click", function() {
    const checkboxes = document.querySelectorAll("#playlistVideos input[type='checkbox']:checked");
    if (checkboxes.length === 0) {
        alert("Please select at least one video.");
        return;
    }
    const urls = Array.from(checkboxes).map(cb => cb.value);
    const format = document.getElementById("formatSelect").value;

    fetch("/download_selected", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({urls, format})
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            alert(data.error);
        } else {
            alert(data.message);
            modal.style.display = "none"; // Close popup after download
        }
    });
});
