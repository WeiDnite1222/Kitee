function normalizeBakeOverlayPayload(level, message, options, callback) {
    const fallback = level === "warning" ? "Oh no! Warning message is missing." : "Unknown error.";
    let payload = {};
    if (message && typeof message === "object" && !Array.isArray(message)) {
        payload = { ...message };
    } else {
        payload.message = message;
    }

    if (Array.isArray(options)) {
        payload.actions = options;
    } else if (options && typeof options === "object") {
        payload = { ...payload, ...options };
    } else if (typeof options === "function" && !callback) {
        callback = options;
    }

    const actions = Array.isArray(payload.actions) && payload.actions.length
        ? payload.actions
        : [{ id: "close", label: "Close" }];

    return {
        level,
        title: payload.title || (level === "warning" ? "Warning" : "Error"),
        message: payload.message || fallback,
        actions: actions.map((action, index) => {
            if (typeof action === "string") {
                return { id: action, label: action, closes: true };
            }
            const actionId = action?.id || action?.value || `action_${index + 1}`;
            return {
                id: String(actionId),
                label: String(action?.label || action?.text || actionId),
                kind: String(action?.kind || action?.type || ""),
                closes: action?.closes !== false
            };
        }),
        overlayId: payload.overlayId || payload.id || "",
        callback: typeof callback === "function" ? callback : payload.callback
    };
}

function showBakeOverlay(level, message, options, callback) {
    const payload = normalizeBakeOverlayPayload(level, message, options, callback);
    document.querySelector(".bake-error-overlay")?.remove();

    const overlay = document.createElement("div");
    overlay.className = "bake-error-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");

    const widget = document.createElement("section");
    widget.className = `bake-error-widget bake-${payload.level}-widget`;

    const title = document.createElement("h2");
    title.textContent = payload.title;

    const text = document.createElement("pre");
    text.className = "bake-error-message";
    text.textContent = payload.message;

    const actions = document.createElement("div");
    actions.className = "bake-error-actions";

    payload.actions.forEach(action => {
        const button = document.createElement("button");
        button.className = "bake-error-close";
        button.type = "button";
        button.textContent = action.label;
        button.addEventListener("click", () => {
            if (action.closes) {
                overlay.remove();
            }
            if (typeof payload.callback === "function") {
                payload.callback(action.id, action);
            }
            if (payload.overlayId && window.pywebview?.api?.handle_overlay_action) {
                window.pywebview.api.handle_overlay_action(payload.overlayId, action.id).catch(() => {});
            }
        });
        actions.appendChild(button);
    });

    widget.append(title, text, actions);
    overlay.appendChild(widget);
    overlay.addEventListener("click", event => {
        if (event.target === overlay) {
            overlay.remove();
        }
    });
    document.body.appendChild(overlay);
    actions.querySelector("button")?.focus();
}

function showBakeErrorOverlay(message, options, callback) {
    showBakeOverlay("error", message, options, callback);
}

function showBakeWarningOverlay(message, options, callback) {
    showBakeOverlay("warning", message, options, callback);
}

function showBakeMessageBox(titleText, bodyHtml) {
    document.querySelector(".bake-error-overlay")?.remove();

    const overlay = document.createElement("div");
    overlay.className = "bake-error-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");

    const widget = document.createElement("section");
    widget.className = "bake-error-widget bake-message-widget";

    const title = document.createElement("h2");
    title.textContent = titleText || window.t("Notice");

    const text = document.createElement("div");
    text.className = "bake-message-content";
    text.innerHTML = bodyHtml || "";

    const actions = document.createElement("div");
    actions.className = "bake-error-actions";

    const closeButton = document.createElement("button");
    closeButton.className = "bake-error-close";
    closeButton.type = "button";
    closeButton.textContent = "Close";
    closeButton.addEventListener("click", () => overlay.remove());

    actions.appendChild(closeButton);
    widget.append(title, text, actions);
    overlay.appendChild(widget);
    overlay.addEventListener("click", event => {
        if (event.target === overlay) {
            overlay.remove();
        }
    });
    document.body.appendChild(overlay);
    closeButton.focus();
}

window.__bakeShowErrorOverlay = showBakeErrorOverlay;
window.__bakeShowWarningOverlay = showBakeWarningOverlay;

function cssUrl(value) {
    return `url("${String(value || "").replaceAll("\\", "\\\\").replaceAll("\"", "\\\"").replaceAll("\n", "")}")`;
}

function isBackgroundVideo(value) {
    const media = String(value || "").trim().toLowerCase();
    return media.startsWith("data:video/") || media.startsWith("blob:") || media.split("?", 1)[0].endsWith(".webm");
}

function normalizePercent(value, fallback) {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) ? Math.max(0, Math.min(100, parsed)) : fallback;
}

function normalizeThemeSettings(theme) {
    return theme === "black" ? "black" : "light";
}

function applyThemeSettings(theme) {
    document.body.classList.toggle("bake-theme-black", normalizeThemeSettings(theme) === "black");
}

function normalizeBackgroundSettings(settings) {
    const imageDataUri = String(settings?.imageDataUri || settings?.image || "").trim();
    const parsedBlur = Number.parseInt(settings?.blur, 10);
    return {
        imageDataUri,
        blur: Number.isFinite(parsedBlur) ? Math.max(0, Math.min(80, parsedBlur)) : 0,
        mediaOpacity: normalizePercent(settings?.mediaOpacity, 100),
        surfaceAlpha: normalizePercent(settings?.surfaceAlpha, 60)
    };
}

function resolveChildBackgroundSettings(settings) {
    const mode = ["inherit", "none", "custom"].includes(settings?.childMode) ? settings.childMode : "inherit";
    if (mode === "none") {
        return null;
    }

    if (mode === "custom") {
        return {
            image: settings?.childImage || "",
            imageDataUri: settings?.childImageDataUri || settings?.childImage || "",
            blur: settings?.childBlur || 0,
            mediaOpacity: settings?.mediaOpacity ?? 100,
            surfaceAlpha: settings?.surfaceAlpha ?? 60
        };
    }

    return settings;
}

function applyBackgroundSettings(settings) {
    const background = normalizeBackgroundSettings(settings);
    let backgroundLayer = document.querySelector(".bake-background-layer");

    document.body.classList.toggle("bake-has-background", Boolean(background.imageDataUri));
    document.body.classList.toggle("bake-transparent-surfaces", background.surfaceAlpha <= 0);
    if (background.imageDataUri) {
        if (!backgroundLayer) {
            backgroundLayer = document.createElement("div");
            backgroundLayer.className = "bake-background-layer";
            backgroundLayer.setAttribute("aria-hidden", "true");
            document.body.prepend(backgroundLayer);
        }
        backgroundLayer.innerHTML = "";
        backgroundLayer.style.backgroundImage = "";
        backgroundLayer.style.filter = `blur(${background.blur}px)`;
        document.body.style.setProperty("--bake-background-media-opacity", `${background.mediaOpacity / 100}`);
        document.body.style.setProperty("--bake-background-surface-alpha", `${background.surfaceAlpha / 100}`);
        if (isBackgroundVideo(background.imageDataUri)) {
            const video = document.createElement("video");
            video.className = "bake-background-video";
            video.src = background.imageDataUri;
            video.autoplay = true;
            video.loop = true;
            video.muted = true;
            video.playsInline = true;
            video.setAttribute("playsinline", "");
            video.play().catch(error => {
                console.error("Failed to play background video.", error);
            });
            backgroundLayer.appendChild(video);
            return;
        }
        backgroundLayer.style.backgroundImage = cssUrl(background.imageDataUri);
        return;
    }

    backgroundLayer?.remove();
    document.body.classList.remove("bake-transparent-surfaces");
    document.body.style.removeProperty("--bake-background-media-opacity");
    document.body.style.removeProperty("--bake-background-surface-alpha");
}

function loadChildBackgroundSettings() {
    if (!window.pywebview?.api?.get_frontend_settings) {
        return;
    }

    window.pywebview.api.get_frontend_settings()
        .then(settings => {
            applyThemeSettings(settings?.frontend?.theme);
            applyBackgroundSettings(resolveChildBackgroundSettings(settings?.frontend?.background));
        })
        .catch(error => {
            console.error("Failed to load child background settings.", error);
        });
}

function loadFrontendBackgroundSettings() {
    loadChildBackgroundSettings();
}
