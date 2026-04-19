const managedInstanceId = __BK_INSTANCE_ID__;
const initialInstancePage = __BK_INITIAL_PAGE__;
const initialInstanceDetail = __BK_INITIAL_DETAIL__;
const instanceWindowName = document.getElementById("instance_window_name");
const instanceWindowVersion = document.getElementById("instance_window_version");
const instanceWindowStatus = document.getElementById("instance_window_status");
const instanceOverviewGrid = document.getElementById("instance_overview_grid");
const instanceSettingsGrid = document.getElementById("instance_settings_grid");
const instanceSettingsForm = document.getElementById("instance_settings_form");
const instanceSettingsRefresh = document.getElementById("instance_settings_refresh");
const instanceIconPreview = document.getElementById("instance_icon_preview");
const instanceIconFile = document.getElementById("instance_icon_file");
const instanceIconRecommended = document.getElementById("instance_icon_recommended");
const instanceIconGrass = document.getElementById("instance_icon_grass");
const instanceIconModded = document.getElementById("instance_icon_modded");
const instanceIconClear = document.getElementById("instance_icon_clear");
const instanceClientVersions = document.getElementById("instance_client_versions");
const instanceClientForm = document.getElementById("instance_client_form");
const instanceClientMainClass = document.getElementById("instance_client_main_class");
const instanceClientCustomJar = document.getElementById("instance_client_custom_jar");
const instanceClientClasspathVersion = document.getElementById("instance_client_classpath_version");
const instanceClientClasspathList = document.getElementById("instance_client_classpath_list");
const instanceClientInsertClasspath = document.getElementById("instance_client_insert_classpath");
const instanceClientRefresh = document.getElementById("instance_client_refresh");
const instanceModsPath = document.getElementById("instance_mods_path");
const instanceModsList = document.getElementById("instance_mods_list");
const instanceModLoaderSelect = document.getElementById("instance_mod_loader_select");
const instanceModLoaderVersion = document.getElementById("instance_mod_loader_version");
const instanceModInstallLoader = document.getElementById("instance_mod_install_loader");
const instanceModDropZone = document.getElementById("instance_mod_drop_zone");
const instanceModBrowserMenu = document.getElementById("instance_mod_browser_menu");
const instanceModAdd = document.getElementById("instance_mod_add");
const instanceModRemove = document.getElementById("instance_mod_remove");
const instanceModToggle = document.getElementById("instance_mod_toggle");
const instanceModRefresh = document.getElementById("instance_mod_refresh");
const instanceWorldsPath = document.getElementById("instance_worlds_path");
const instanceWorldsList = document.getElementById("instance_worlds_list");
const instanceWorldImport = document.getElementById("instance_world_import");
const instanceWorldDelete = document.getElementById("instance_world_delete");
const instanceWorldRefresh = document.getElementById("instance_world_refresh");
const instanceResourcePacksPath = document.getElementById("instance_resource_packs_path");
const instanceResourcePacksList = document.getElementById("instance_resource_packs_list");
const instanceResourcePackImport = document.getElementById("instance_resource_pack_import");
const instanceResourcePackDelete = document.getElementById("instance_resource_pack_delete");
const instanceResourcePackRefresh = document.getElementById("instance_resource_pack_refresh");
const instanceJvmForm = document.getElementById("instance_jvm_form");
const instanceJvmRuntimeSelect = document.getElementById("instance_jvm_runtime_select");
const instanceJvmRefreshList = document.getElementById("instance_jvm_refresh_list");
const instanceJvmRefreshSettings = document.getElementById("instance_jvm_refresh_settings");
const instanceJvmSupportVersion = document.getElementById("instance_jvm_support_version");
const instanceJvmExecutable = document.getElementById("instance_jvm_executable");
const instanceJvmMemoryArgs = document.getElementById("instance_jvm_memory_args");
const instanceJvmCustomArgs = document.getElementById("instance_jvm_custom_args");
const instanceJvmModloaderArgs = document.getElementById("instance_jvm_modloader_args");
const instanceLaunchButton = document.getElementById("instance_launch_button");
const instanceLogCopy = document.getElementById("instance_log_copy");
const instanceLogRefresh = document.getElementById("instance_log_refresh");
const instanceLogClearView = document.getElementById("instance_log_clear_view");
const instanceLogPath = document.getElementById("instance_log_path");
const instanceLogOutput = document.getElementById("instance_log_output");
const instanceLogContextMenu = document.getElementById("instance_log_context_menu");
const instanceLogContextCopy = document.getElementById("instance_log_context_copy");
const instanceClasspathContextMenu = document.getElementById("instance_classpath_context_menu");
const instanceClasspathContextToggle = document.getElementById("instance_classpath_context_toggle");
let instanceJobTimer = null;
let instanceLogTimer = null;
let instanceLogOffset = 0;
let instanceLogRecordingStopped = false;
let instanceJvmSettingsLoaded = false;
let instanceJvmListLoaded = false;
let instanceClientLoaded = false;
let currentClasspathItems = [];
let contextClasspathItem = null;
let instanceModsLoaded = false;
let instanceModLoaderJobTimer = null;
let selectedInstanceModName = "";
let currentInstanceMods = [];
let instanceWorldsLoaded = false;
let selectedInstanceWorldName = "";
let currentInstanceWorlds = [];
let instanceResourcePacksLoaded = false;
let selectedInstanceResourcePackName = "";
let currentInstanceResourcePacks = [];
let currentInstanceDetail = initialInstanceDetail?.ok ? initialInstanceDetail : null;
const builtinInstanceIcons = {
    grass: __BK_GRASS_ICON__,
    modded: __BK_GRASS_MODDED_ICON__
};

const overviewFields = [
    ["instance_name", "Name"],
    ["client_version", "Minecraft"],
    ["type", "Type"],
    ["mod_loader_display", "Mod loader"],
    ["effective_main_class", "Main class"],
    ["support_java_version", "Java"],
    ["instance_format", "Format"],
    ["create_date", "Created"],
    ["real_minecraft_version", "Real version"],
    ["game_folder", "Game folder"],
    ["assets_folder", "Assets folder"]
];

const editableFields = [
    ["instance_name", "Name"],
    ["client_version", "Minecraft"],
    ["type", "Type"],
    ["main_class", "Base main class"],
    ["support_java_version", "Java"],
    ["real_minecraft_version", "Real version"],
    ["game_folder", "Game folder"],
    ["assets_folder", "Assets folder"],
    ["enable_config", "Enable config"],
    ["custom_config_path", "Config path"]
];

function setInstanceWindowStatus(message) {
    instanceWindowStatus.textContent = message || "";
}

function isErrorLogLine(line) {
    return /\[ERROR\]|\bERROR\b|\bERR\b|Exception|Traceback|Failed|failed|Can't|exit(ed)? with code\s+[1-9]\d*/.test(line);
}

function appendLogText(text) {
    if (!text) {
        return;
    }

    const shouldStickToBottom = instanceLogOutput.scrollTop + instanceLogOutput.clientHeight >= instanceLogOutput.scrollHeight - 16;
    const fragment = document.createDocumentFragment();
    const parts = text.split(/(\r?\n)/);

    for (let index = 0; index < parts.length; index += 1) {
        const part = parts[index];
        if (!part) {
            continue;
        }

        if (part === "\n" || part === "\r\n") {
            fragment.appendChild(document.createTextNode(part));
            continue;
        }

        const line = document.createElement("span");
        line.className = isErrorLogLine(part) ? "instance-log-line error" : "instance-log-line";
        line.textContent = part;
        fragment.appendChild(line);
    }

    instanceLogOutput.appendChild(fragment);

    if (shouldStickToBottom) {
        instanceLogOutput.scrollTop = instanceLogOutput.scrollHeight;
    }

    if (text.includes("Log line limit reached")) {
        instanceLogRecordingStopped = true;
        setInstanceWindowStatus("Log recording stopped after 20000 lines.");
    }
}

function loadInstanceLog(reset = false) {
    if (!window.pywebview?.api?.get_instance_log) {
        instanceLogPath.textContent = "Log API is not ready.";
        return;
    }

    const offset = reset ? 0 : instanceLogOffset;
    if (reset) {
        instanceLogOutput.textContent = "";
        instanceLogRecordingStopped = false;
    }

    window.pywebview.api.get_instance_log(managedInstanceId, offset)
        .then(result => {
            if (!result?.ok) {
                instanceLogPath.textContent = result?.error || "Failed to read log.";
                return;
            }

            instanceLogPath.textContent = result.path || "";
            instanceLogOffset = Number(result.offset || 0);
            appendLogText(result.text || "");

            if (instanceLogRecordingStopped && instanceLogTimer) {
                window.clearInterval(instanceLogTimer);
                instanceLogTimer = null;
            }
        })
        .catch(error => {
            instanceLogPath.textContent = "Failed to read log.";
            console.error("Failed to read instance log.", error);
        });
}

function startInstanceLogPolling(reset = false) {
    loadInstanceLog(reset);

    if (instanceLogTimer) {
        return;
    }

    instanceLogTimer = window.setInterval(() => loadInstanceLog(false), 900);
}

function stopInstanceLogPolling() {
    if (!instanceLogTimer) {
        return;
    }

    window.clearInterval(instanceLogTimer);
    instanceLogTimer = null;
}

function getSelectedLogText() {
    const selection = window.getSelection?.();
    if (!selection || selection.isCollapsed) {
        return "";
    }

    const range = selection.getRangeAt(0);
    if (!instanceLogOutput.contains(range.commonAncestorContainer)) {
        return "";
    }

    return selection.toString();
}

function copyInstanceLog(selectedOnly = false) {
    const selectedText = getSelectedLogText();
    const text = selectedOnly
        ? selectedText
        : selectedText || instanceLogOutput.innerText || instanceLogOutput.textContent || "";
    if (!text) {
        setInstanceWindowStatus("No log text to copy.");
        return;
    }

    if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(text)
            .then(() => setInstanceWindowStatus("Log copied."))
            .catch(() => fallbackCopyInstanceLog(text));
        return;
    }

    fallbackCopyInstanceLog(text);
}

function openLogContextMenu(x, y) {
    if (!instanceLogContextMenu) {
        return;
    }

    instanceLogContextMenu.hidden = false;
    const menuBox = instanceLogContextMenu.getBoundingClientRect();
    const safeX = Math.min(x, window.innerWidth - menuBox.width - 8);
    const safeY = Math.min(y, window.innerHeight - menuBox.height - 8);
    instanceLogContextMenu.style.left = `${Math.max(8, safeX)}px`;
    instanceLogContextMenu.style.top = `${Math.max(8, safeY)}px`;
}

function closeLogContextMenu() {
    if (instanceLogContextMenu) {
        instanceLogContextMenu.hidden = true;
    }
}

function openClasspathContextMenu(x, y, item) {
    contextClasspathItem = item;
    instanceClasspathContextToggle.textContent = item.source === "extra"
        ? "Remove"
        : item.enabled ? "Disable" : "Enable";
    instanceClasspathContextMenu.hidden = false;
    const menuBox = instanceClasspathContextMenu.getBoundingClientRect();
    const safeX = Math.min(x, window.innerWidth - menuBox.width - 8);
    const safeY = Math.min(y, window.innerHeight - menuBox.height - 8);
    instanceClasspathContextMenu.style.left = `${Math.max(8, safeX)}px`;
    instanceClasspathContextMenu.style.top = `${Math.max(8, safeY)}px`;
}

function closeClasspathContextMenu() {
    if (instanceClasspathContextMenu) {
        instanceClasspathContextMenu.hidden = true;
    }
    contextClasspathItem = null;
}

function fallbackCopyInstanceLog(text) {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();

    try {
        document.execCommand("copy");
        setInstanceWindowStatus("Log copied.");
    } catch (error) {
        setInstanceWindowStatus("Failed to copy log.");
        console.error("Failed to copy instance log.", error);
    } finally {
        textarea.remove();
    }
}

function activateLaunchLog() {
    showInstancePage("launch");
    startInstanceLogPolling(true);
}

function showInstancePage(pageName) {
    if (pageName !== "launch") {
        stopInstanceLogPolling();
    }

    if (pageName === "jvm") {
        loadJvmPage();
    }

    if (pageName === "client") {
        loadClientPage();
    }

    if (pageName === "mods") {
        loadInstanceMods();
    }

    if (pageName === "worlds") {
        loadInstanceWorlds();
    }

    if (pageName === "resourcepacks") {
        loadInstanceResourcePacks();
    }

    document.querySelectorAll(".instance-window-tab").forEach(button => {
        const active = button.dataset.instancePage === pageName;
        button.classList.toggle("active", active);
    });

    document.querySelectorAll(".instance-widget-box").forEach(box => {
        box.classList.toggle("active", box.id === `instance_page_${pageName}`);
    });
}

function getInstanceDisplayName(detail = currentInstanceDetail) {
    const info = detail?.info || {};
    return info.instance_name || detail?.id || managedInstanceId || "Instance";
}

function getInstanceInitial(detail = currentInstanceDetail) {
    if (detail?.icon?.initial) {
        return detail.icon.initial;
    }

    const name = getInstanceDisplayName(detail).trim();
    return (Array.from(name).find(isInstanceInitialChar) || "?").toUpperCase();
}

function isInstanceInitialChar(char) {
    const code = char.codePointAt(0) || 0;
    return (
        (code >= 48 && code <= 57)
        || (code >= 65 && code <= 90)
        || (code >= 97 && code <= 122)
        || (code >= 0x3400 && code <= 0x9fff)
        || (code >= 0xf900 && code <= 0xfaff)
    );
}

function getInstanceIconColor(name) {
    const colors = ["#22c55e", "#38bdf8", "#64748b", "#f59e0b", "#ef4444", "#14b8a6", "#8b5cf6", "#ec4899"];
    let hash = 0;
    for (const char of String(name || "")) {
        hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
    }
    return colors[hash % colors.length];
}

function renderIconPreview(detail = currentInstanceDetail) {
    if (!instanceIconPreview) {
        return;
    }

    instanceIconPreview.innerHTML = "";
    const icon = document.createElement("div");
    icon.className = "instance-app-icon instance-icon-editor-preview-icon";
    icon.style.setProperty("--instance-icon-bg", getInstanceIconColor(getInstanceDisplayName(detail)));

    if (detail?.icon?.src) {
        const image = document.createElement("img");
        image.src = detail.icon.src;
        image.alt = "";
        icon.classList.add("instance-app-image-icon");
        icon.appendChild(image);
    } else {
        const shine = document.createElement("span");
        shine.className = "instance-app-icon-shine";
        icon.appendChild(shine);

        const glyph = document.createElement("span");
        glyph.className = "instance-app-icon-glyph";
        glyph.textContent = getInstanceInitial(detail);
        icon.appendChild(glyph);
    }

    const name = document.createElement("p");
    name.className = "instance-app-name";
    name.textContent = getInstanceDisplayName(detail);

    instanceIconPreview.appendChild(icon);
    instanceIconPreview.appendChild(name);
}

function getRecommendedBuiltinIcon() {
    return currentInstanceDetail?.icon?.recommended === "modded" ? builtinInstanceIcons.modded : builtinInstanceIcons.grass;
}

function saveInstanceIcon(dataUrl) {
    if (!window.pywebview?.api?.save_instance_icon) {
        setInstanceWindowStatus("Icon API is not ready.");
        return;
    }

    if (!String(dataUrl || "").includes("base64,")) {
        setInstanceWindowStatus("Icon data is missing.");
        return;
    }

    setInstanceWindowStatus("Saving icon...");
    window.pywebview.api.save_instance_icon(managedInstanceId, {dataUrl})
        .then(result => {
            if (!result?.ok) {
                setInstanceWindowStatus(result?.error || "Failed to save icon.");
                return;
            }

            setInstanceWindowStatus("Icon saved.");
            loadInstanceDetail();
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to save icon.");
            console.error("Failed to save instance icon.", error);
        });
}

function clearInstanceIcon() {
    if (!window.pywebview?.api?.clear_instance_icon) {
        setInstanceWindowStatus("Icon API is not ready.");
        return;
    }

    setInstanceWindowStatus("Clearing icon...");
    window.pywebview.api.clear_instance_icon(managedInstanceId)
        .then(result => {
            if (!result?.ok) {
                setInstanceWindowStatus(result?.error || "Failed to clear icon.");
                return;
            }

            setInstanceWindowStatus("Letter icon is active.");
            loadInstanceDetail();
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to clear icon.");
            console.error("Failed to clear instance icon.", error);
        });
}

function uploadInstanceIcon(file) {
    if (!file) {
        return;
    }

    if (!/^image\/(png|jpeg|webp)$/.test(file.type)) {
        setInstanceWindowStatus("Icon must be PNG, JPEG, or WebP.");
        return;
    }

    if (file.size > 2 * 1024 * 1024) {
        setInstanceWindowStatus("Icon must be 2 MB or smaller.");
        return;
    }

    const reader = new FileReader();
    reader.addEventListener("load", () => saveInstanceIcon(reader.result));
    reader.addEventListener("error", () => setInstanceWindowStatus("Failed to read icon file."));
    reader.readAsDataURL(file);
}

function renderDetail(result) {
    if (!result?.ok) {
        setInstanceWindowStatus(result?.error || "Failed to load instance.");
        return;
    }

    currentInstanceDetail = result;
    const info = result.info || {};
    const modLoader = result.modLoader || {};
    info.mod_loader_display = formatModLoaderInfo(modLoader);
    instanceWindowName.textContent = info.instance_name || result.id;
    instanceWindowVersion.textContent = info.client_version || "Unknown version";
    document.title = `Instance: ${info.instance_name || result.id}`;
    setInstanceWindowStatus("");
    renderIconPreview(result);

    instanceOverviewGrid.innerHTML = "";
    overviewFields.forEach(([key, label]) => {
        const item = document.createElement("article");
        item.className = "instance-detail-item";

        const name = document.createElement("span");
        name.textContent = label;

        const value = document.createElement("strong");
        value.textContent = info[key] ?? "";

        item.appendChild(name);
        item.appendChild(value);
        instanceOverviewGrid.appendChild(item);
    });

    instanceSettingsGrid.innerHTML = "";
    editableFields.forEach(([key, label]) => {
        const row = document.createElement("label");
        row.className = "instance-settings-row";

        const name = document.createElement("span");
        name.textContent = label;

        const input = document.createElement("input");
        input.type = "text";
        input.dataset.instanceField = key;
        input.value = info[key] ?? "";

        row.appendChild(name);
        row.appendChild(input);
        instanceSettingsGrid.appendChild(row);
    });
}

function formatModLoaderInfo(modLoader) {
    if (!modLoader?.installed) {
        return "";
    }

    return [modLoader.displayName || modLoader.name, modLoader.version]
        .filter(Boolean)
        .join(" ");
}

function loadInstanceDetail() {
    if (!window.pywebview?.api?.get_instance_detail) {
        setInstanceWindowStatus("Instance API is not ready.");
        return;
    }

    setInstanceWindowStatus("Loading instance...");
    window.pywebview.api.get_instance_detail(managedInstanceId)
        .then(renderDetail)
        .catch(error => {
            setInstanceWindowStatus("Failed to load instance.");
            console.error("Failed to load instance detail.", error);
        });
}

function saveInstanceDetail() {
    if (!window.pywebview?.api?.save_instance_detail) {
        setInstanceWindowStatus("Instance API is not ready.");
        return;
    }

    const values = {};
    instanceSettingsGrid.querySelectorAll("[data-instance-field]").forEach(input => {
        values[input.dataset.instanceField] = input.value.trim();
    });

    setInstanceWindowStatus("Saving instance...");
    window.pywebview.api.save_instance_detail(managedInstanceId, values)
        .then(result => {
            if (!result?.ok) {
                setInstanceWindowStatus(result?.error || "Failed to save instance.");
                return;
            }

            setInstanceWindowStatus("Saved.");
            loadInstanceDetail();
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to save instance.");
            console.error("Failed to save instance detail.", error);
        });
}

function renderClientVersionItem(label, value) {
    const item = document.createElement("article");
    item.className = "instance-detail-item";

    const name = document.createElement("span");
    name.textContent = label;

    const text = document.createElement("strong");
    text.textContent = value || "";

    item.append(name, text);
    instanceClientVersions.appendChild(item);
}

function renderClientSettings(result) {
    if (!result?.ok) {
        instanceClientVersions.innerHTML = "";
        renderClientVersionItem("Client", result?.error || "Failed to load client settings.");
        instanceClientMainClass.value = "";
        instanceClientCustomJar.value = "";
        return;
    }

    const modLoader = result.modLoader || {};
    const modLoaderLabel = formatModLoaderInfo(modLoader) || "None";
    const realVersion = result.realMinecraftVersion && result.realMinecraftVersion !== result.minecraftVersion
        ? result.realMinecraftVersion
        : "";

    instanceClientVersions.innerHTML = "";
    renderClientVersionItem("Minecraft", result.minecraftVersion || "");
    renderClientVersionItem("Real Minecraft", realVersion || result.minecraftVersion || "");
    renderClientVersionItem("Mod loader", modLoaderLabel);
    renderClientVersionItem("Mod loader main", modLoader.mainClass || "");

    instanceClientMainClass.value = result.mainClass || "";
    instanceClientCustomJar.value = result.customJar?.path || "";
    instanceClientCustomJar.classList.toggle("missing-value", Boolean(result.customJar?.path && !result.customJar?.exists));
    renderClientClasspath(result.classpath || {});
}

function renderClientClasspath(classpath) {
    currentClasspathItems = classpath.items || [];
    instanceClientClasspathVersion.textContent = classpath.ok
        ? `${classpath.launchVersion || ""} | ${currentClasspathItems.length} items`
        : classpath.error || "Classpath unavailable.";
    instanceClientClasspathList.innerHTML = "";

    if (!currentClasspathItems.length) {
        const empty = document.createElement("p");
        empty.className = "instance-mod-empty";
        empty.textContent = classpath.ok ? "No classpath items." : classpath.error || "Classpath unavailable.";
        instanceClientClasspathList.appendChild(empty);
        return;
    }

    currentClasspathItems.forEach(item => {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "instance-classpath-item";
        row.classList.toggle("disabled-classpath", !item.enabled);
        row.classList.toggle("missing-classpath", !item.exists);
        row.title = item.path || "";

        const name = document.createElement("strong");
        name.textContent = item.name || item.path || "";

        const meta = document.createElement("span");
        const state = item.enabled ? "Enabled" : "Disabled";
        const exists = item.exists ? "" : " | Missing";
        meta.textContent = `${item.source || "default"} | ${item.kind || "jar"} | ${state}${exists}`;

        const path = document.createElement("small");
        path.textContent = item.path || "";

        row.append(name, meta, path);
        row.addEventListener("contextmenu", event => {
            event.preventDefault();
            openClasspathContextMenu(event.clientX, event.clientY, item);
        });
        instanceClientClasspathList.appendChild(row);
    });
}

function loadClientPage(force = false) {
    if (instanceClientLoaded && !force) {
        return;
    }

    if (!window.pywebview?.api?.get_instance_client_settings) {
        setInstanceWindowStatus("Client API is not ready.");
        return;
    }

    setInstanceWindowStatus("Loading client settings...");
    window.pywebview.api.get_instance_client_settings(managedInstanceId)
        .then(result => {
            renderClientSettings(result);
            instanceClientLoaded = Boolean(result?.ok);
            setInstanceWindowStatus(result?.ok ? "" : result?.error || "Failed to load client settings.");
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to load client settings.");
            console.error("Failed to load client settings.", error);
        });
}

function saveClientSettings() {
    if (!window.pywebview?.api?.save_instance_client_settings) {
        setInstanceWindowStatus("Client API is not ready.");
        return;
    }

    setInstanceWindowStatus("Saving client settings...");
    window.pywebview.api.save_instance_client_settings(managedInstanceId, {
        mainClass: instanceClientMainClass.value.trim()
    })
        .then(result => {
            renderClientSettings(result);
            instanceClientLoaded = Boolean(result?.ok);
            setInstanceWindowStatus(result?.ok ? "Client settings saved." : result?.error || "Failed to save client settings.");
            loadInstanceDetail();
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to save client settings.");
            console.error("Failed to save client settings.", error);
        });
}

function browseClientJar() {
    if (!window.pywebview?.api?.browse_instance_client_jar) {
        setInstanceWindowStatus("Client jar API is not ready.");
        return;
    }

    setInstanceWindowStatus("Choose client jar...");
    window.pywebview.api.browse_instance_client_jar(managedInstanceId)
        .then(result => {
            renderClientSettings(result);
            instanceClientLoaded = Boolean(result?.ok);
            setInstanceWindowStatus(result?.insertedJar ? "Custom client jar inserted." : result?.ok ? "" : result?.error || "Failed to insert custom jar.");
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to insert custom jar.");
            console.error("Failed to insert client jar.", error);
        });
}

// function clearClientJar() {
//     if (!window.pywebview?.api?.clear_instance_client_jar) {
//         setInstanceWindowStatus("Client jar API is not ready.");
//         return;
//     }

//     setInstanceWindowStatus("Clearing custom jar...");
//     window.pywebview.api.clear_instance_client_jar(managedInstanceId)
//         .then(result => {
//             renderClientSettings(result);
//             instanceClientLoaded = Boolean(result?.ok);
//             setInstanceWindowStatus(result?.ok ? "Default client jar is active." : result?.error || "Failed to clear custom jar.");
//         })
//         .catch(error => {
//             setInstanceWindowStatus("Failed to clear custom jar.");
//             console.error("Failed to clear client jar.", error);
//         });
// }

function insertClasspathJar() {
    if (!window.pywebview?.api?.browse_instance_classpath_jar) {
        setInstanceWindowStatus("Classpath API is not ready.");
        return;
    }

    setInstanceWindowStatus("Choose classpath jar...");
    window.pywebview.api.browse_instance_classpath_jar(managedInstanceId)
        .then(result => {
            renderClientSettings(result);
            instanceClientLoaded = Boolean(result?.ok);
            setInstanceWindowStatus(result?.insertedClasspath ? "Classpath inserted." : result?.ok ? "" : result?.error || "Failed to insert classpath.");
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to insert classpath.");
            console.error("Failed to insert classpath.", error);
        });
}

function toggleContextClasspathItem() {
    const item = contextClasspathItem;
    closeClasspathContextMenu();
    if (!item || !window.pywebview?.api?.set_instance_classpath_enabled) {
        setInstanceWindowStatus(item ? "Classpath API is not ready." : "Select a classpath item first.");
        return;
    }

    const enable = item.source === "extra" ? false : !item.enabled;
    setInstanceWindowStatus(item.source === "extra" ? "Removing classpath..." : enable ? "Enabling classpath..." : "Disabling classpath...");
    window.pywebview.api.set_instance_classpath_enabled(managedInstanceId, item.id, enable)
        .then(result => {
            renderClientSettings(result);
            instanceClientLoaded = Boolean(result?.ok);
            setInstanceWindowStatus(result?.ok ? "Classpath saved." : result?.error || "Failed to save classpath.");
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to save classpath.");
            console.error("Failed to save classpath.", error);
        });
}

function formatModSize(size) {
    const bytes = Number(size || 0);
    if (bytes >= 1024 * 1024) {
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
    if (bytes >= 1024) {
        return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${bytes} B`;
}

function renderLibraryList({target, items, selectedName, emptyText, iconText, onSelect}) {
    target.innerHTML = "";
    if (!items.length) {
        const item = document.createElement("p");
        item.className = "instance-mod-empty";
        item.textContent = emptyText;
        target.appendChild(item);
        return;
    }

    items.forEach(entry => {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "instance-library-item";
        row.classList.toggle("selected", entry.name === selectedName);
        row.setAttribute("role", "option");
        row.setAttribute("aria-selected", entry.name === selectedName ? "true" : "false");

        const icon = document.createElement("span");
        icon.className = "instance-library-icon";
        if (entry.icon) {
            const image = document.createElement("img");
            image.src = entry.icon;
            image.alt = "";
            icon.appendChild(image);
        } else {
            icon.textContent = iconText;
        }

        const summary = document.createElement("span");
        summary.className = "instance-library-summary";

        const title = document.createElement("strong");
        title.textContent = entry.name || "";

        const meta = document.createElement("span");
        meta.textContent = `${entry.created || "Unknown date"} | ${formatModSize(entry.size)}`;

        summary.append(title, meta);
        row.append(icon, summary);
        row.addEventListener("click", () => onSelect(entry.name));
        target.appendChild(row);
    });
}

function getSelectedInstanceMod() {
    return currentInstanceMods.find(mod => mod.name === selectedInstanceModName) || null;
}

function updateModActionState(available = true) {
    const selectedMod = getSelectedInstanceMod();
    const hasSelection = Boolean(selectedMod);
    instanceModInstallLoader.disabled = false;
    instanceModAdd.disabled = !available;
    instanceModBrowserMenu.disabled = !available;
    instanceModRemove.disabled = !available || !hasSelection;
    instanceModToggle.disabled = !available || !hasSelection;
    instanceModRefresh.disabled = false;
    instanceModToggle.textContent = selectedMod?.enabled ? "Disable" : "Enable";
}

function renderInstanceMods(result) {
    if (!result?.ok) {
        instanceModsPath.textContent = "";
        instanceModsList.innerHTML = "";
        const item = document.createElement("p");
        item.className = "instance-mod-empty";
        item.textContent = result?.error || "Failed to load mods.";
        instanceModsList.appendChild(item);
        updateModActionState(false);
        return;
    }

    instanceModsPath.textContent = result.modsDir || "";
    currentInstanceMods = result.mods || [];
    const installedLoaderName = currentInstanceDetail?.modLoader?.name || "";
    const normalizedLoaderName = String(installedLoaderName).trim().toLowerCase();
    if (["fabric", "forge", "neoforge"].includes(normalizedLoaderName)) {
        instanceModLoaderSelect.value = normalizedLoaderName;
    }
    instanceModInstallLoader.textContent = result.available ? "Reinstall Mod Loader" : "Install Mod Loader";

    if (!result.available) {
        selectedInstanceModName = "";
        instanceModsList.innerHTML = "";
        const item = document.createElement("p");
        item.className = "instance-mod-empty instance-mod-unavailable";
        item.textContent = "Mod Loader Unavailable: Install Mod Loader first";
        instanceModsList.appendChild(item);
        updateModActionState(false);
        return;
    }

    if (!currentInstanceMods.some(mod => mod.name === selectedInstanceModName)) {
        selectedInstanceModName = currentInstanceMods[0]?.name || "";
    }

    instanceModsList.innerHTML = "";
    if (!currentInstanceMods.length) {
        const item = document.createElement("p");
        item.className = "instance-mod-empty";
        item.textContent = "No mods installed.";
        instanceModsList.appendChild(item);
        updateModActionState(true);
        return;
    }

    currentInstanceMods.forEach(mod => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "instance-mod-item";
        item.classList.toggle("selected", mod.name === selectedInstanceModName);
        item.classList.toggle("disabled-mod", !mod.enabled);
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", mod.name === selectedInstanceModName ? "true" : "false");

        const title = document.createElement("strong");
        title.textContent = mod.displayName || mod.name;

        const meta = document.createElement("span");
        meta.textContent = `${mod.enabled ? "Enabled" : "Disabled"} | ${formatModSize(mod.size)}`;

        item.append(title, meta);
        item.addEventListener("click", () => {
            selectedInstanceModName = mod.name;
            renderInstanceMods({ok: true, available: true, modsDir: result.modsDir, mods: currentInstanceMods});
        });
        instanceModsList.appendChild(item);
    });

    updateModActionState(true);
}

function loadInstanceMods(force = false) {
    if (instanceModsLoaded && !force) {
        return;
    }

    if (!window.pywebview?.api?.get_instance_mods) {
        setInstanceWindowStatus("Mods API is not ready.");
        return;
    }

    setInstanceWindowStatus("Loading mods...");
    window.pywebview.api.get_instance_mods(managedInstanceId)
        .then(result => {
            renderInstanceMods(result);
            instanceModsLoaded = Boolean(result?.ok);
            setInstanceWindowStatus(result?.ok ? "" : result?.error || "Failed to load mods.");
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to load mods.");
            console.error("Failed to load instance mods.", error);
        });
}

function browseInstanceMods() {
    if (!window.pywebview?.api?.browse_instance_mods) {
        setInstanceWindowStatus("Mod browser API is not ready.");
        return;
    }

    if (instanceModBrowserMenu.value !== "local") {
        setInstanceWindowStatus("This mod browser is not available yet.");
        return;
    }

    setInstanceWindowStatus("Choose mod files...");
    window.pywebview.api.browse_instance_mods(managedInstanceId)
        .then(result => {
            renderInstanceMods(result);
            instanceModsLoaded = Boolean(result?.ok);
            if (result?.ok) {
                setInstanceWindowStatus(result.added?.length ? "Mod added." : "");
            } else {
                setInstanceWindowStatus(result?.error || "Failed to add mod.");
            }
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to add mod.");
            console.error("Failed to browse instance mods.", error);
        });
}

function getDroppedFilePaths(event) {
    return Array.from(event.dataTransfer?.files || [])
        .map(file => file.path || file.webkitRelativePath || "")
        .filter(path => path && /\.jar(\.disabled)?$/i.test(path));
}

function readDroppedModPayloads(files) {
    const modFiles = Array.from(files || []).filter(file => /\.jar(\.disabled)?$/i.test(file.name || ""));
    return Promise.all(modFiles.map(file => new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.addEventListener("load", () => resolve({name: file.name, dataUrl: reader.result}));
        reader.addEventListener("error", () => reject(reader.error || new Error("Failed to read file.")));
        reader.readAsDataURL(file);
    })));
}

function importDroppedMods(event) {
    event.preventDefault();
    instanceModDropZone.classList.remove("drag-over");

    if (!window.pywebview?.api?.import_instance_mod_payloads && !window.pywebview?.api?.import_instance_mod_files) {
        setInstanceWindowStatus("Mod import API is not ready.");
        return;
    }

    const files = Array.from(event.dataTransfer?.files || []);
    if (!files.some(file => /\.jar(\.disabled)?$/i.test(file.name || ""))) {
        setInstanceWindowStatus("Drop .jar files only.");
        return;
    }

    setInstanceWindowStatus("Importing mods...");
    const importPromise = window.pywebview?.api?.import_instance_mod_payloads
        ? readDroppedModPayloads(files).then(payloads => window.pywebview.api.import_instance_mod_payloads(managedInstanceId, payloads))
        : Promise.resolve().then(() => {
            const paths = getDroppedFilePaths(event);
            if (!paths.length) {
                return {ok: false, error: "Drop paths are unavailable. Use Add instead."};
            }
            return window.pywebview.api.import_instance_mod_files(managedInstanceId, paths);
        });

    importPromise
        .then(result => {
            renderInstanceMods(result);
            instanceModsLoaded = Boolean(result?.ok);
            setInstanceWindowStatus(result?.ok ? `Imported ${result.added?.length || 0} mod(s).` : result?.error || "Failed to import mods.");
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to import mods.");
            console.error("Failed to import dropped mods.", error);
        });
}

function removeSelectedInstanceMod() {
    const selectedMod = getSelectedInstanceMod();
    if (!selectedMod || !window.pywebview?.api?.remove_instance_mod) {
        setInstanceWindowStatus(selectedMod ? "Remove mod API is not ready." : "Select a mod first.");
        return;
    }

    setInstanceWindowStatus("Removing mod...");
    window.pywebview.api.remove_instance_mod(managedInstanceId, selectedMod.name)
        .then(result => {
            selectedInstanceModName = "";
            renderInstanceMods(result);
            setInstanceWindowStatus(result?.ok ? "Mod removed." : result?.error || "Failed to remove mod.");
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to remove mod.");
            console.error("Failed to remove instance mod.", error);
        });
}

function toggleSelectedInstanceMod() {
    const selectedMod = getSelectedInstanceMod();
    if (!selectedMod || !window.pywebview?.api?.set_instance_mod_enabled) {
        setInstanceWindowStatus(selectedMod ? "Mod toggle API is not ready." : "Select a mod first.");
        return;
    }

    const enable = !selectedMod.enabled;
    setInstanceWindowStatus(enable ? "Enabling mod..." : "Disabling mod...");
    window.pywebview.api.set_instance_mod_enabled(managedInstanceId, selectedMod.name, enable)
        .then(result => {
            renderInstanceMods(result);
            setInstanceWindowStatus(result?.ok ? (enable ? "Mod enabled." : "Mod disabled.") : result?.error || "Failed to update mod.");
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to update mod.");
            console.error("Failed to update instance mod.", error);
        });
}

function installInstanceModLoader() {
    if (!window.pywebview?.api?.install_instance_mod_loader) {
        setInstanceWindowStatus("Mod loader install API is not ready.");
        return;
    }

    const payload = {
        modLoader: instanceModLoaderSelect.value,
        modLoaderVersion: instanceModLoaderVersion.value.trim()
    };

    instanceModInstallLoader.disabled = true;
    setInstanceWindowStatus("Installing mod loader...");
    window.pywebview.api.install_instance_mod_loader(managedInstanceId, payload)
        .then(result => {
            if (!result?.ok) {
                instanceModInstallLoader.disabled = false;
                setInstanceWindowStatus(result?.error || "Failed to install mod loader.");
                return;
            }

            if (result.jobId) {
                watchModLoaderJob(result.jobId);
            } else {
                instanceModInstallLoader.disabled = false;
                setInstanceWindowStatus("Mod loader installed.");
                loadInstanceDetail();
                loadInstanceMods(true);
            }
        })
        .catch(error => {
            instanceModInstallLoader.disabled = false;
            setInstanceWindowStatus("Failed to install mod loader.");
            console.error("Failed to install mod loader.", error);
        });
}

function watchModLoaderJob(jobId) {
    window.clearInterval(instanceModLoaderJobTimer);
    instanceModLoaderJobTimer = window.setInterval(() => {
        window.pywebview.api.get_instance_job(jobId)
            .then(job => {
                if (!job?.ok) {
                    window.clearInterval(instanceModLoaderJobTimer);
                    instanceModLoaderJobTimer = null;
                    instanceModInstallLoader.disabled = false;
                    setInstanceWindowStatus(job?.error || "Job not found.");
                    return;
                }

                const progress = Number(job.total || 0) > 0
                    ? ` (${Number(job.progress || 0)}/${Number(job.total || 0)})`
                    : "";
                setInstanceWindowStatus(`${job.status || job.state || "Running..."}${progress}`);
                if (!job.done) {
                    return;
                }

                window.clearInterval(instanceModLoaderJobTimer);
                instanceModLoaderJobTimer = null;
                instanceModInstallLoader.disabled = false;
                setInstanceWindowStatus(job.state === "failed" ? job.error || "Install mod loader failed." : "Mod loader installed.");
                instanceModsLoaded = false;
                instanceClientLoaded = false;
                loadInstanceDetail();
                loadInstanceMods(true);
            })
            .catch(error => {
                window.clearInterval(instanceModLoaderJobTimer);
                instanceModLoaderJobTimer = null;
                instanceModInstallLoader.disabled = false;
                setInstanceWindowStatus("Failed to read install status.");
                console.error("Failed to read mod loader install job.", error);
            });
    }, 800);
}

function updateWorldActionState() {
    instanceWorldDelete.disabled = !selectedInstanceWorldName;
}

function renderInstanceWorlds(result) {
    if (!result?.ok) {
        instanceWorldsPath.textContent = "";
        currentInstanceWorlds = [];
        selectedInstanceWorldName = "";
        renderLibraryList({
            target: instanceWorldsList,
            items: [],
            selectedName: "",
            emptyText: result?.error || "Failed to load worlds.",
            iconText: "W",
            onSelect: () => {
            }
        });
        updateWorldActionState();
        return;
    }

    instanceWorldsPath.textContent = result.worldsDir || "";
    currentInstanceWorlds = result.worlds || [];
    if (!currentInstanceWorlds.some(world => world.name === selectedInstanceWorldName)) {
        selectedInstanceWorldName = currentInstanceWorlds[0]?.name || "";
    }

    renderLibraryList({
        target: instanceWorldsList,
        items: currentInstanceWorlds,
        selectedName: selectedInstanceWorldName,
        emptyText: "No worlds found.",
        iconText: "W",
        onSelect: name => {
            selectedInstanceWorldName = name;
            renderInstanceWorlds({ok: true, worldsDir: result.worldsDir, worlds: currentInstanceWorlds});
        }
    });
    updateWorldActionState();
}

function loadInstanceWorlds(force = false) {
    if (instanceWorldsLoaded && !force) {
        return;
    }

    if (!window.pywebview?.api?.get_instance_worlds) {
        setInstanceWindowStatus("World API is not ready.");
        return;
    }

    setInstanceWindowStatus("Loading worlds...");
    window.pywebview.api.get_instance_worlds(managedInstanceId)
        .then(result => {
            renderInstanceWorlds(result);
            instanceWorldsLoaded = Boolean(result?.ok);
            setInstanceWindowStatus(result?.ok ? "" : result?.error || "Failed to load worlds.");
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to load worlds.");
            console.error("Failed to load worlds.", error);
        });
}

function importInstanceWorld() {
    if (!window.pywebview?.api?.browse_import_instance_world) {
        setInstanceWindowStatus("World import API is not ready.");
        return;
    }

    setInstanceWindowStatus("Choose world folder...");
    window.pywebview.api.browse_import_instance_world(managedInstanceId)
        .then(result => {
            renderInstanceWorlds(result);
            instanceWorldsLoaded = Boolean(result?.ok);
            setInstanceWindowStatus(result?.imported ? "World imported." : result?.ok ? "" : result?.error || "Failed to import world.");
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to import world.");
            console.error("Failed to import world.", error);
        });
}

function deleteSelectedWorld() {
    if (!selectedInstanceWorldName || !window.pywebview?.api?.delete_instance_world) {
        setInstanceWindowStatus(selectedInstanceWorldName ? "World delete API is not ready." : "Select a world first.");
        return;
    }

    setInstanceWindowStatus("Deleting world...");
    window.pywebview.api.delete_instance_world(managedInstanceId, selectedInstanceWorldName)
        .then(result => {
            selectedInstanceWorldName = "";
            renderInstanceWorlds(result);
            setInstanceWindowStatus(result?.ok ? "World deleted." : result?.error || "Failed to delete world.");
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to delete world.");
            console.error("Failed to delete world.", error);
        });
}

function updateResourcePackActionState() {
    instanceResourcePackDelete.disabled = !selectedInstanceResourcePackName;
}

function renderInstanceResourcePacks(result) {
    if (!result?.ok) {
        instanceResourcePacksPath.textContent = "";
        currentInstanceResourcePacks = [];
        selectedInstanceResourcePackName = "";
        renderLibraryList({
            target: instanceResourcePacksList,
            items: [],
            selectedName: "",
            emptyText: result?.error || "Failed to load resource packs.",
            iconText: "R",
            onSelect: () => {
            }
        });
        updateResourcePackActionState();
        return;
    }

    instanceResourcePacksPath.textContent = result.packsDir || "";
    currentInstanceResourcePacks = result.packs || [];
    if (!currentInstanceResourcePacks.some(pack => pack.name === selectedInstanceResourcePackName)) {
        selectedInstanceResourcePackName = currentInstanceResourcePacks[0]?.name || "";
    }

    renderLibraryList({
        target: instanceResourcePacksList,
        items: currentInstanceResourcePacks,
        selectedName: selectedInstanceResourcePackName,
        emptyText: "No resource packs found.",
        iconText: "R",
        onSelect: name => {
            selectedInstanceResourcePackName = name;
            renderInstanceResourcePacks({ok: true, packsDir: result.packsDir, packs: currentInstanceResourcePacks});
        }
    });
    updateResourcePackActionState();
}

function loadInstanceResourcePacks(force = false) {
    if (instanceResourcePacksLoaded && !force) {
        return;
    }

    if (!window.pywebview?.api?.get_instance_resource_packs) {
        setInstanceWindowStatus("Resource pack API is not ready.");
        return;
    }

    setInstanceWindowStatus("Loading resource packs...");
    window.pywebview.api.get_instance_resource_packs(managedInstanceId)
        .then(result => {
            renderInstanceResourcePacks(result);
            instanceResourcePacksLoaded = Boolean(result?.ok);
            setInstanceWindowStatus(result?.ok ? "" : result?.error || "Failed to load resource packs.");
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to load resource packs.");
            console.error("Failed to load resource packs.", error);
        });
}

function importInstanceResourcePack() {
    if (!window.pywebview?.api?.browse_import_instance_resource_pack) {
        setInstanceWindowStatus("Resource pack import API is not ready.");
        return;
    }

    setInstanceWindowStatus("Choose resource pack zip...");
    window.pywebview.api.browse_import_instance_resource_pack(managedInstanceId)
        .then(result => {
            renderInstanceResourcePacks(result);
            instanceResourcePacksLoaded = Boolean(result?.ok);
            setInstanceWindowStatus(result?.imported?.length ? "Resource pack imported." : result?.ok ? "" : result?.error || "Failed to import resource pack.");
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to import resource pack.");
            console.error("Failed to import resource pack.", error);
        });
}

function deleteSelectedResourcePack() {
    if (!selectedInstanceResourcePackName || !window.pywebview?.api?.delete_instance_resource_pack) {
        setInstanceWindowStatus(selectedInstanceResourcePackName ? "Resource pack delete API is not ready." : "Select a resource pack first.");
        return;
    }

    setInstanceWindowStatus("Deleting resource pack...");
    window.pywebview.api.delete_instance_resource_pack(managedInstanceId, selectedInstanceResourcePackName)
        .then(result => {
            selectedInstanceResourcePackName = "";
            renderInstanceResourcePacks(result);
            setInstanceWindowStatus(result?.ok ? "Resource pack deleted." : result?.error || "Failed to delete resource pack.");
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to delete resource pack.");
            console.error("Failed to delete resource pack.", error);
        });
}

function loadJvmPage(force = false) {
    loadJvmSettings(force);
    loadJvmList(force);
}

function loadJvmSettings(force = false) {
    if (instanceJvmSettingsLoaded && !force) {
        return;
    }

    if (!window.pywebview?.api?.get_instance_jvm_settings) {
        setInstanceWindowStatus("JVM API is not ready.");
        return;
    }

    window.pywebview.api.get_instance_jvm_settings(managedInstanceId)
        .then(result => {
            if (!result?.ok) {
                setInstanceWindowStatus(result?.error || "Failed to load JVM settings.");
                return;
            }

            const settings = result.settings || {};
            instanceJvmSupportVersion.value = settings.supportJavaVersion || "";
            instanceJvmExecutable.value = settings.javaExecutable || "";
            instanceJvmMemoryArgs.value = settings.memoryJVMArgs || "";
            instanceJvmCustomArgs.value = settings.customJVMArgs || "";
            instanceJvmModloaderArgs.value = settings.modLoaderJVMArgs || "";
            syncSelectedJvmRuntime();
            instanceJvmSettingsLoaded = true;
            setInstanceWindowStatus("");
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to load JVM settings.");
            console.error("Failed to load JVM settings.", error);
        });
}

function loadJvmList(force = false) {
    if (instanceJvmListLoaded && !force) {
        return;
    }

    if (!window.pywebview?.api?.get_jvms) {
        return;
    }

    window.pywebview.api.get_jvms(force)
        .then(renderJvmList)
        .catch(error => {
            console.error("Failed to load JVM list.", error);
        });
}

function renderJvmList(result) {
    if (!instanceJvmRuntimeSelect) {
        return;
    }

    const selectedPath = instanceJvmExecutable.value;
    instanceJvmRuntimeSelect.innerHTML = "";

    const autoOption = document.createElement("option");
    autoOption.value = "";
    autoOption.textContent = "Auto / PATH";
    instanceJvmRuntimeSelect.appendChild(autoOption);

    if (result?.ok) {
        for (const runtime of result.jvms || []) {
            const option = document.createElement("option");
            option.value = runtime.path || "";
            option.dataset.majorVersion = runtime.majorVersion || "";
            option.textContent = `${runtime.source || "JVM"} ${runtime.majorVersion || "?"} | ${runtime.path || ""}`;
            instanceJvmRuntimeSelect.appendChild(option);
        }
    }

    instanceJvmExecutable.value = selectedPath;
    syncSelectedJvmRuntime();
    instanceJvmListLoaded = Boolean(result?.ok);
}

function syncSelectedJvmRuntime() {
    if (!instanceJvmRuntimeSelect) {
        return;
    }

    const executable = instanceJvmExecutable.value.trim();
    const option = Array.from(instanceJvmRuntimeSelect.options).find(item => item.value === executable);
    instanceJvmRuntimeSelect.value = option ? executable : "";
}

function applySelectedJvmRuntime() {
    const option = instanceJvmRuntimeSelect.selectedOptions[0];
    instanceJvmExecutable.value = option?.value || "";
    if (option?.dataset?.majorVersion) {
        instanceJvmSupportVersion.value = option.dataset.majorVersion;
    }
}

function saveJvmSettings() {
    if (!window.pywebview?.api?.save_instance_jvm_settings) {
        setInstanceWindowStatus("JVM API is not ready.");
        return;
    }

    const payload = {
        supportJavaVersion: instanceJvmSupportVersion.value.trim(),
        javaExecutable: instanceJvmExecutable.value.trim(),
        memoryJVMArgs: instanceJvmMemoryArgs.value.trim(),
        customJVMArgs: instanceJvmCustomArgs.value.trim()
    };

    setInstanceWindowStatus("Saving JVM settings...");
    window.pywebview.api.save_instance_jvm_settings(managedInstanceId, payload)
        .then(result => {
            if (!result?.ok) {
                setInstanceWindowStatus(result?.error || "Failed to save JVM settings.");
                return;
            }

            instanceJvmSettingsLoaded = false;
            setInstanceWindowStatus("JVM settings saved.");
            loadJvmSettings(true);
            loadInstanceDetail();
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to save JVM settings.");
            console.error("Failed to save JVM settings.", error);
        });
}

function launchInstance() {
    if (!window.pywebview?.api?.launch_instance) {
        setInstanceWindowStatus("Launch API is not ready.");
        return;
    }

    activateLaunchLog();
    setInstanceWindowStatus("Starting launch...");
    window.pywebview.api.launch_instance(managedInstanceId)
        .then(result => {
            if (!result?.ok) {
                setInstanceWindowStatus(result?.error || "Failed to launch instance.");
                return;
            }

            if (result.jobId) {
                watchInstanceJob(result.jobId);
            } else {
                setInstanceWindowStatus("Launch started.");
            }
        })
        .catch(error => {
            setInstanceWindowStatus("Failed to launch instance.");
            console.error("Failed to launch instance.", error);
        });
}

function watchInstanceJob(jobId) {
    window.clearInterval(instanceJobTimer);
    instanceJobTimer = window.setInterval(() => {
        window.pywebview.api.get_instance_job(jobId)
            .then(job => {
                if (!job?.ok) {
                    window.clearInterval(instanceJobTimer);
                    instanceJobTimer = null;
                    setInstanceWindowStatus(job?.error || "Job not found.");
                    return;
                }

                setInstanceWindowStatus(job.status || job.state || "Running...");
                if (!job.done) {
                    return;
                }

                window.clearInterval(instanceJobTimer);
                instanceJobTimer = null;
                setInstanceWindowStatus(job.state === "failed" ? job.error || "Job failed." : "Launch started.");
                loadInstanceLog(false);
            })
            .catch(error => {
                window.clearInterval(instanceJobTimer);
                instanceJobTimer = null;
                setInstanceWindowStatus("Failed to read job status.");
                console.error("Failed to read instance job.", error);
            });
    }, 800);
}

document.querySelectorAll(".instance-window-tab").forEach(button => {
    button.addEventListener("click", () => {
        if (button.dataset.instancePage === "launch") {
            activateLaunchLog();
            return;
        }

        showInstancePage(button.dataset.instancePage);
    });
});

instanceSettingsForm.addEventListener("submit", event => {
    event.preventDefault();
    saveInstanceDetail();
});
instanceSettingsRefresh.addEventListener("click", loadInstanceDetail);
instanceIconFile.addEventListener("change", () => {
    uploadInstanceIcon(instanceIconFile.files?.[0]);
    instanceIconFile.value = "";
});
instanceIconRecommended.addEventListener("click", () => saveInstanceIcon(getRecommendedBuiltinIcon()));
instanceIconGrass.addEventListener("click", () => saveInstanceIcon(builtinInstanceIcons.grass));
instanceIconModded.addEventListener("click", () => saveInstanceIcon(builtinInstanceIcons.modded));
instanceIconClear.addEventListener("click", clearInstanceIcon);
instanceClientForm.addEventListener("submit", event => {
    event.preventDefault();
    saveClientSettings();
});
instanceClientInsertClasspath.addEventListener("click", insertClasspathJar);
// instanceClientClearJar.addEventListener("click", clearClientJar);
instanceClientRefresh.addEventListener("click", () => loadClientPage(true));
instanceClientMainClass.addEventListener("change", saveClientSettings);
instanceClasspathContextToggle.addEventListener("click", toggleContextClasspathItem);
instanceModInstallLoader.addEventListener("click", installInstanceModLoader);
instanceModAdd.addEventListener("click", browseInstanceMods);
instanceModRemove.addEventListener("click", removeSelectedInstanceMod);
instanceModToggle.addEventListener("click", toggleSelectedInstanceMod);
instanceModRefresh.addEventListener("click", () => loadInstanceMods(true));
instanceWorldImport.addEventListener("click", importInstanceWorld);
instanceWorldDelete.addEventListener("click", deleteSelectedWorld);
instanceWorldRefresh.addEventListener("click", () => loadInstanceWorlds(true));
instanceResourcePackImport.addEventListener("click", importInstanceResourcePack);
instanceResourcePackDelete.addEventListener("click", deleteSelectedResourcePack);
instanceResourcePackRefresh.addEventListener("click", () => loadInstanceResourcePacks(true));
instanceModDropZone.addEventListener("dragenter", event => {
    event.preventDefault();
    instanceModDropZone.classList.add("drag-over");
});
instanceModDropZone.addEventListener("dragover", event => {
    event.preventDefault();
    instanceModDropZone.classList.add("drag-over");
});
instanceModDropZone.addEventListener("dragleave", event => {
    if (!instanceModDropZone.contains(event.relatedTarget)) {
        instanceModDropZone.classList.remove("drag-over");
    }
});
instanceModDropZone.addEventListener("drop", importDroppedMods);
instanceJvmForm.addEventListener("submit", event => {
    event.preventDefault();
    saveJvmSettings();
});
instanceJvmRefreshList.addEventListener("click", () => loadJvmList(true));
instanceJvmRefreshSettings.addEventListener("click", () => loadJvmSettings(true));
instanceJvmRuntimeSelect.addEventListener("change", applySelectedJvmRuntime);
instanceJvmExecutable.addEventListener("input", syncSelectedJvmRuntime);
instanceLaunchButton.addEventListener("click", launchInstance);
instanceLogCopy.addEventListener("click", copyInstanceLog);
instanceLogRefresh.addEventListener("click", () => loadInstanceLog(false));
instanceLogClearView.addEventListener("click", () => {
    instanceLogOutput.textContent = "";
});
instanceLogOutput.addEventListener("contextmenu", event => {
    event.preventDefault();
    openLogContextMenu(event.clientX, event.clientY);
});
instanceLogContextCopy.addEventListener("click", () => {
    copyInstanceLog(false);
    closeLogContextMenu();
});
window.addEventListener("click", event => {
    if (!instanceLogContextMenu || instanceLogContextMenu.hidden) {
        if (instanceClasspathContextMenu && !instanceClasspathContextMenu.hidden && !instanceClasspathContextMenu.contains(event.target)) {
            closeClasspathContextMenu();
        }
        return;
    }

    if (!instanceLogContextMenu.contains(event.target)) {
        closeLogContextMenu();
    }
    if (instanceClasspathContextMenu && !instanceClasspathContextMenu.hidden && !instanceClasspathContextMenu.contains(event.target)) {
        closeClasspathContextMenu();
    }
});
window.addEventListener("keydown", event => {
    if (event.key === "Escape") {
        closeLogContextMenu();
        closeClasspathContextMenu();
    }
});
window.__bakeShowInstancePage = pageName => {
    if (pageName === "launch") {
        activateLaunchLog();
        return;
    }
    showInstancePage(pageName || "overview");
};
if (initialInstanceDetail?.ok) {
    renderDetail(initialInstanceDetail);
}

window.addEventListener("pywebviewready", () => {
    loadFrontendBackgroundSettings();

    if (!initialInstanceDetail?.ok) {
        loadInstanceDetail();
    }

    if (initialInstancePage === "launch") {
        activateLaunchLog();
    } else {
        showInstancePage(initialInstancePage || "overview");
    }
});
