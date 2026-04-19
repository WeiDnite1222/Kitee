const dockStrip = document.querySelector(".system-window-dock-strip");
const dockButton = document.getElementById("dock_button");
const targetId = dockStrip.getAttribute("data-target-container");
let pointerId = null;
let startY = 0;

function dockThisWindow() {
    window.pywebview?.api?.dock_tab(targetId);
}

dockButton.addEventListener("click", dockThisWindow);

dockStrip.addEventListener("pointerdown", event => {
    if (event.target.closest("button")) {
        return;
    }

    pointerId = event.pointerId;
    startY = event.clientY;
    dockStrip.classList.add("dragging-dock-strip");
    dockStrip.setPointerCapture(event.pointerId);
});

dockStrip.addEventListener("pointermove", event => {
    if (event.pointerId !== pointerId) {
        return;
    }

    const distanceY = event.clientY - startY;
    if (distanceY > 90) {
        dockThisWindow();
    }
});

function stopDockDrag(event) {
    if (event.pointerId !== pointerId) {
        return;
    }

    dockStrip.classList.remove("dragging-dock-strip");

    if (dockStrip.hasPointerCapture(event.pointerId)) {
        dockStrip.releasePointerCapture(event.pointerId);
    }

    pointerId = null;
}

dockStrip.addEventListener("pointerup", stopDockDrag);
dockStrip.addEventListener("pointercancel", stopDockDrag);
window.addEventListener("pywebviewready", loadChildBackgroundSettings);
