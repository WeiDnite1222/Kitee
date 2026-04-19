const pageStage = document.querySelector(".page-stage");

// Tab Bar
const tabBar = document.querySelector(".tab-bar");
const tabBarContextMenu = document.getElementById("tab_bar_context_menu");
let contextTabButton = null;
let tabButtons = tabBar.querySelectorAll(".tab-button");

// Settings
const settingsList = document.getElementById("settings_list");
const jvmSettingsList = document.getElementById("jvm_settings_list");
const settingsPanelTitle = document.getElementById("settings_panel_title");
const settingsSwitchButtons = Array.from(document.querySelectorAll(".settings-switch-button"));
const settingsRefreshButton = document.getElementById("settings_refresh_button");
const settingsSaveButton = document.getElementById("settings_save_button");
const settingsSaveStatus = document.getElementById("settings_save_status");

// Account
const accountList = document.getElementById("account_list");
const accountStatus = document.getElementById("account_status");
const accountDataPath = document.getElementById("account_data_path");
const accountRefreshButton = document.getElementById("account_refresh_button");
const accountLoginButton = document.getElementById("account_login_button");
const accountCreateForm = document.getElementById("account_create_form");
const offlineUsernameInput = document.getElementById("offline_username");
const accountClearButton = document.getElementById("account_clear_button");

// Instance
const homeInstanceList = document.getElementById("home_instance_list");
const instanceList = document.getElementById("instance_list");
const homeInstancesPath = document.getElementById("home_instances_path");
const instancesPath = document.getElementById("instances_path");
const instanceStatus = document.getElementById("instance_status");
const instanceContextMenu = document.getElementById("instance_context_menu");
const homeInstancesRefreshButton = document.getElementById("home_instances_refresh_button");
const instancesRefreshButton = document.getElementById("instances_refresh_button");

// Instance Creator
const tabbarCreateInstanceButton = document.getElementById("tabbar_create_instance_button");
const builtinInstanceIcons = {
    grass: __BK_GRASS_ICON__,
    modded: __BK_GRASS_MODDED_ICON__
};


// Vars for tab and container transition
let draggedTab = null;
let dragPointerId = null;
let dragStartX = 0;
let dragStartY = 0;
let dragOffsetX = 0;
let dragOffsetY = 0;
let didDragTab = false;
let didDetachTab = false;
const reorderCoverage = 0.75;
const detachDistance = 86;
const pageTransitionMs = 220;

// Flags and Settings
let frontendSettingsLoaded = false;
let activeSettingsPage = "config";
let jvmSettingsLoaded = false;
let jvmJobTimer = null;
let suppressSettingsReloadDisplay = false;
let isSwitchingContainer = false;
let contextInstance = null;
let contextInstanceCard = null;
let instanceJobTimer = null;
let accountsLoadPromise = null;
let accountsLoaded = false;
let instancesLoadPromise = null;
let instancesLoaded = false;
let instanceDisplayMode = "icon";
let currentBackgroundSettings = {
    image: "",
    blur: 0,
    imageDataUri: "",
    mediaOpacity: 100,
    surfaceAlpha: 60,
    childMode: "inherit",
    childImage: "",
    childBlur: 0,
    childImageDataUri: ""
};

// Internation
const availableLanguages = window.KiteeLauncherI18n?.availableLanguages || ["en"];
const currentLauncherLanguage = window.KiteeLauncherI18n?.language || "en";
let selectedLauncherLanguage = currentLauncherLanguage;
const settingsTabItems = [
    {value: "home_container", label: "Home"},
    {value: "instances_container", label: "Instances"},
    {value: "accounts_container", label: "Accounts"},
    {value: "settings_container", label: "Settings"},
    {value: "about_container", label: "About"}
];
const settingsDetachableTabItems = settingsTabItems.filter(item => item.value !== "home_container");
const settingsHideableTabItems = settingsTabItems;
const defaultTabOrder = [
    "home_container",
    "instances_container",
    "accounts_container",
    "about_container",
    "settings_container"
];


function openTabButtonContextMenu(x, y, tabBtn) {
    if (!tabBarContextMenu) {
        return;
    }

    contextTabButton = tabBtn;
    tabBarContextMenu.hidden = false;

    const menuBox = tabBarContextMenu.getBoundingClientRect();
    const safeX = Math.min(x, window.innerWidth - menuBox.width - 8);
    const safeY = Math.min(y, window.innerHeight - menuBox.height - 8);
    tabBarContextMenu.style.left = `${Math.max(8, safeX)}px`;
    tabBarContextMenu.style.top = `${Math.max(8, safeY)}px`;
    tabBarContextMenu.style.bottom = "";
}

function closeTabButtonContextMenu() {
    if (!tabBarContextMenu) {
        return;
    }

    tabBarContextMenu.hidden = true;
    contextTabButton = null;
}

tabButtons.forEach((btn) => {
    btn.addEventListener("contextmenu", event => {
        event.preventDefault();
        openTabButtonContextMenu(event.x, event.y, btn)
    });
})

tabBarContextMenu?.addEventListener("click", event => {
    const button = event.target.closest("button[data-action]");
    if (!button) {
        return;
    }

    const action = button.dataset.action;
    if (action === "hidden") {
        hideContextTab();
    } else if (action === "reset_sort") {
        resetTabSort();
    }
    closeTabButtonContextMenu();
});

function getTabButtons() {
    return Array.from(document.querySelectorAll(".tab-button"));
}

function getDockedTabButtons() {
    return getTabButtons().filter(button => !button.classList.contains("detached-tab"));
}

function getVisibleTabButtons() {
    return getTabButtons().filter(button => !button.classList.contains("hidden-tab"));
}

function getVisibleDockedTabButtons() {
    return getDockedTabButtons().filter(button => !button.classList.contains("hidden-tab"));
}

function getStageContainers() {
    return Array.from(pageStage.querySelectorAll("main.container"));
}

function getKnownTabIds() {
    return settingsTabItems.map(item => item.value);
}

function getTabButtonByTargetId(targetId) {
    return targetId ? tabBar?.querySelector(`[data-target-container="${targetId}"]`) : null;
}

function getTargetContainerByButton(button) {
    const targetId = button?.getAttribute("data-target-container");
    return targetId ? document.getElementById(targetId) : null;
}

function waitForContainerTransition(container) {
    return new Promise(resolve => {
        let done = false;

        function finish() {
            if (done) {
                return;
            }

            done = true;
            container.removeEventListener("transitionend", onTransitionEnd);
            resolve();
        }

        function onTransitionEnd(event) {
            if (event.target === container && event.propertyName === "transform") {
                finish();
            }
        }

        container.addEventListener("transitionend", onTransitionEnd);
        window.setTimeout(finish, pageTransitionMs + 80);
    });
}

function setActiveButton(button) {
    getTabButtons().forEach(tabButton => {
        tabButton.classList.remove("active");
        tabButton.removeAttribute("aria-current");
    });

    button.classList.add("active");
    button.setAttribute("aria-current", "page");
}

function setTabHidden(button, hidden) {
    if (!button) {
        return;
    }

    button.classList.toggle("hidden-tab", hidden);
    button.toggleAttribute("aria-hidden", hidden);
}

function normalizeHiddenTabIds(hiddenTabIds = []) {
    const hiddenSet = new Set(Array.isArray(hiddenTabIds) ? hiddenTabIds : []);
    const dockedTargetIds = getDockedTabButtons()
        .map(button => button.getAttribute("data-target-container"))
        .filter(Boolean);
    if (dockedTargetIds.length && dockedTargetIds.every(targetId => hiddenSet.has(targetId))) {
        hiddenSet.delete("home_container");
        hiddenSet.delete(dockedTargetIds[0]);
    }

    return Array.from(hiddenSet);
}

function applyHiddenTabs(hiddenTabIds = []) {
    const hiddenSet = new Set(normalizeHiddenTabIds(hiddenTabIds));

    getTabButtons().forEach(button => {
        const targetId = button.getAttribute("data-target-container");
        setTabHidden(button, hiddenSet.has(targetId));
    });

    const activeButton = document.querySelector(".tab-button.active");
    if (activeButton?.classList.contains("hidden-tab")) {
        activateFirstDockedTab();
    }
}

function hideContextTab() {
    if (!contextTabButton) {
        return;
    }

    const visibleDockedTabs = getVisibleDockedTabButtons();
    if (!contextTabButton.classList.contains("detached-tab") && visibleDockedTabs.length <= 1) {
        return;
    }

    const wasActive = contextTabButton.classList.contains("active");


    if (contextTabButton.getAttribute('data-target-container') === "home_container") {
        return;
    } else {
        setTabHidden(contextTabButton, true);
    }

    if (wasActive) {
        activateFirstDockedTab();
    } else {
        saveFrontendSettings();
    }
}

function resetTabSort() {
    const knownTargets = new Set(defaultTabOrder);
    defaultTabOrder.forEach(targetId => {
        const button = getTabButtonByTargetId(targetId);
        if (button) {
            tabBar.appendChild(button);
        }
    });

    getTabButtons()
        .filter(button => !knownTargets.has(button.getAttribute("data-target-container")))
        .forEach(button => tabBar.appendChild(button));

    getTabButtons().forEach(button => setTabHidden(button, false));

    const activeButton = document.querySelector(".tab-button.active");
    if (!activeButton || activeButton.classList.contains("detached-tab")) {
        activateFirstDockedTab();
        return;
    }

    saveFrontendSettings();
}

function showContainerImmediately(targetContainer) {
    getStageContainers().forEach(container => {
        container.classList.remove("active-container", "entering-right", "exiting-left");
        container.classList.toggle("hidden", container !== targetContainer);
    });

    targetContainer?.classList.add("active-container");
}

async function activateTab(button, animate = true) {
    // Active target tab and switch current container

    if (isSwitchingContainer) {
        return;
    }

    if (button.classList.contains("detached-tab")) {
        focusDetachedTab(button.getAttribute("data-target-container"));
        return;
    }
    const targetContainer = getTargetContainerByButton(button);
    const currentContainer = pageStage.querySelector(".container.active-container");

    if (!targetContainer) {
        return;
    }

    if (currentContainer === targetContainer) {
        setActiveButton(button);
        if (frontendSettingsLoaded) {
            saveFrontendSettings();
        }
        loadContainerApis(targetContainer);
        return;
    }

    setActiveButton(button);

    if (!animate || !currentContainer) {
        showContainerImmediately(targetContainer);
        if (frontendSettingsLoaded) {
            saveFrontendSettings();
        }
        loadContainerApis(targetContainer);
        return;
    }

    // Switch container
    isSwitchingContainer = true;

    // Apply animation
    targetContainer.classList.add("entering-right", "active-container");
    targetContainer.classList.remove("hidden");

    targetContainer.getBoundingClientRect();
    currentContainer.classList.add("exiting-left");
    targetContainer.classList.remove("entering-right");

    await Promise.all([
        waitForContainerTransition(currentContainer),
        waitForContainerTransition(targetContainer)
    ]);

    currentContainer.classList.remove("active-container", "exiting-left");
    currentContainer.classList.add("hidden");
    isSwitchingContainer = false;

    if (frontendSettingsLoaded) {
        saveFrontendSettings();
    }

    loadContainerApis(targetContainer);
}

function loadContainerApis(targetContainer) {
    if (!targetContainer) {
        return;
    }

    if (targetContainer.id === "accounts_container") {
        loadAccounts();
    }

    if (targetContainer.id === "home_container" || targetContainer.id === "instances_container") {
        loadInstances();
    }

    if (targetContainer.id === "settings_container" && activeSettingsPage === "jvm") {
        loadJvmSettingsList();
    }
}

function getFrontendSettings() {
    const activeTab = document.querySelector(".tab-button.active");

    const settings = {
        tabs: {
            order: getTabButtons()
                .map(button => button.getAttribute("data-target-container"))
                .filter(Boolean),
            active: activeTab?.getAttribute("data-target-container") || null,
            detached: getTabButtons()
                .filter(button => button.classList.contains("detached-tab"))
                .map(button => button.getAttribute("data-target-container"))
                .filter(Boolean),
            hidden: getTabButtons()
                .filter(button => button.classList.contains("hidden-tab"))
                .map(button => button.getAttribute("data-target-container"))
                .filter(Boolean)
        },
        instances: {
            display: instanceDisplayMode
        },
        background: {
            image: currentBackgroundSettings.image || "",
            blur: currentBackgroundSettings.blur || 0,
            mediaOpacity: currentBackgroundSettings.mediaOpacity ?? 100,
            surfaceAlpha: currentBackgroundSettings.surfaceAlpha ?? 60,
            childMode: currentBackgroundSettings.childMode || "inherit",
            childImage: currentBackgroundSettings.childImage || "",
            childBlur: currentBackgroundSettings.childBlur || 0
        },
        theme: document.body.classList.contains("bake-theme-black") ? "black" : "light",
        language: selectedLauncherLanguage
    };

    settings.tabs.hidden = normalizeHiddenTabIds(settings.tabs.hidden);
    return settings;
}


function normalizeBackgroundSettings(settings) {
    const image = String(settings?.image || "").trim();
    const imageDataUri = String(settings?.imageDataUri || image).trim();
    const parsedBlur = Number.parseInt(settings?.blur, 10);
    return {
        image,
        imageDataUri,
        blur: Number.isFinite(parsedBlur) ? Math.max(0, Math.min(80, parsedBlur)) : 0,
        mediaOpacity: normalizePercent(settings?.mediaOpacity, 100),
        surfaceAlpha: normalizePercent(settings?.surfaceAlpha, 60),
        childMode: ["inherit", "none", "custom"].includes(settings?.childMode) ? settings.childMode : "inherit",
        childImage: String(settings?.childImage || "").trim(),
        childImageDataUri: String(settings?.childImageDataUri || settings?.childImage || "").trim(),
        childBlur: Number.isFinite(Number.parseInt(settings?.childBlur, 10))
            ? Math.max(0, Math.min(80, Number.parseInt(settings.childBlur, 10)))
            : 0
    };
}


function applyBackgroundSettings(settings) {
    currentBackgroundSettings = normalizeBackgroundSettings(settings);
    const image = currentBackgroundSettings.imageDataUri;
    let backgroundLayer = document.querySelector(".bake-background-layer");

    document.body.classList.toggle("bake-has-background", Boolean(image));
    document.body.classList.toggle("bake-transparent-surfaces", currentBackgroundSettings.surfaceAlpha <= 0);
    if (image) {
        if (!backgroundLayer) {
            backgroundLayer = document.createElement("div");
            backgroundLayer.className = "bake-background-layer";
            backgroundLayer.setAttribute("aria-hidden", "true");
            document.body.prepend(backgroundLayer);
        }
        backgroundLayer.innerHTML = "";
        backgroundLayer.style.backgroundImage = "";
        backgroundLayer.style.filter = `blur(${currentBackgroundSettings.blur}px)`;
        document.body.style.setProperty("--bake-background-media-opacity", `${currentBackgroundSettings.mediaOpacity / 100}`);
        document.body.style.setProperty("--bake-background-surface-alpha", `${currentBackgroundSettings.surfaceAlpha / 100}`);
        if (isBackgroundVideo(image)) {
            const video = document.createElement("video");
            video.className = "bake-background-video";
            video.src = image;
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
        backgroundLayer.style.backgroundImage = cssUrl(image);
        return;
    }

    backgroundLayer?.remove();
    document.body.classList.remove("bake-transparent-surfaces");
    document.body.style.removeProperty("--bake-background-media-opacity");
    document.body.style.removeProperty("--bake-background-surface-alpha");
}

function saveFrontendSettings() {
    if (!window.pywebview?.api?.save_frontend_settings) {
        return;
    }

    window.pywebview.api.save_frontend_settings(getFrontendSettings())
        .then(settings => {
            settings = normalizeFrontendSettingsResponse(settings);
            applyReloadedFrontendSettings(settings);
        })
        .catch(error => {
            console.error("Failed to save frontend settings.", error);
        });
}

function applyFrontendSettings(settings) {
    renderSettingsPage(settings);

    const instances = settings?.frontend?.instances;
    applyInstanceDisplaySettings(instances);
    applyThemeSettings(settings?.frontend?.theme);
    applyBackgroundSettings(settings?.frontend?.background);

    const tabs = settings?.frontend?.tabs;
    if (!tabs) {
        frontendSettingsLoaded = true;
        return;
    }

    if (Array.isArray(tabs.order)) {
        tabs.order.forEach(targetId => {
            const button = getTabButtonByTargetId(targetId);
            if (button) {
                tabBar.appendChild(button);
            }
        });
    }

    applyHiddenTabs(tabs.hidden);

    const activeButton = getTabButtonByTargetId(tabs.active);
    if (activeButton && !activeButton.classList.contains("hidden-tab")) {
        activateTab(activeButton, false);
    } else if (!pageStage.querySelector(".container.active-container")) {
        activateFirstDockedTab();
    }

    frontendSettingsLoaded = true;
}

function loadFrontendSettings(applyLayout = true) {
    if (!window.pywebview?.api?.get_frontend_settings) {
        frontendSettingsLoaded = true;
        loadContainerApis(pageStage.querySelector(".container.active-container"));
        return Promise.resolve();
    }

    return window.pywebview.api.get_frontend_settings()
        .then(settings => {
            settings = normalizeFrontendSettingsResponse(settings);
            if (applyLayout) {
                applyFrontendSettings(settings);
                loadContainerApis(pageStage.querySelector(".container.active-container"));
            } else {
                applyReloadedFrontendSettings(settings);
            }
        })
        .catch(error => {
            frontendSettingsLoaded = true;
            loadContainerApis(pageStage.querySelector(".container.active-container"));
            console.error("Failed to load frontend settings.", error);
        });
}

function normalizeFrontendSettingsResponse(settings) {
    if (settings?.ok === false) {
        throw new Error(settings.error || "Failed to load frontend settings.");
    }
    return settings || {};
}

function applyReloadedFrontendSettings(settings) {
    if (!suppressSettingsReloadDisplay) {
        applyInstanceDisplaySettings(settings?.frontend?.instances);
    }
    applyThemeSettings(settings?.frontend?.theme);
    applyBackgroundSettings(settings?.frontend?.background);
    renderSettingsPage(settings);
}

function setAccountStatus(message) {
    if (accountStatus) {
        accountStatus.textContent = message;
    }
}

function loadAccounts(force = false) {
    if (!window.pywebview?.api?.get_accounts) {
        setAccountStatus("Account API is not ready.");
        return Promise.resolve();
    }

    if (accountsLoadPromise && !force) {
        return accountsLoadPromise;
    }

    if (accountsLoaded && !force) {
        return Promise.resolve();
    }

    accountsLoadPromise = window.pywebview.api.get_accounts()
        .then(result => {
            renderAccounts(result);
            accountsLoaded = Boolean(result?.ok);
            return result;
        })
        .catch(error => {
            setAccountStatus("Failed to load accounts.");
            console.error("Failed to load accounts.", error);
        })
        .finally(() => {
            accountsLoadPromise = null;
        });

    return accountsLoadPromise;
}

function renderAccounts(result) {
    if (!accountList) {
        return;
    }

    accountList.innerHTML = "";

    if (accountDataPath) {
        accountDataPath.textContent = result?.accountDataPath || "AccountData path unavailable.";
    }

    if (!result?.ok) {
        setAccountStatus(result?.error || "Failed to load accounts.");
        return;
    }

    if (!result.accounts.length) {
        accountList.innerHTML = '<p class="account-empty">No accounts yet.</p>';
        setAccountStatus("");
        return;
    }

    result.accounts.forEach(account => {
        const item = document.createElement("article");
        item.className = "account-item";

        const summary = document.createElement("div");
        summary.className = "account-summary";

        const avatar = document.createElement("div");
        avatar.classList = "account-avatar";

        const avatarImage = document.createElement("img");
        avatarImage.src = account.avatar

        avatar.appendChild(avatarImage);

        const name = document.createElement("h3");
        name.textContent = account.username || "Unnamed";

        const meta = document.createElement("p");
        meta.textContent = `ID ${account.id} | ${account.type || "unknown"} | ${account.uuid || "no uuid"}`;

        summary.appendChild(name);
        summary.appendChild(meta);

        const actions = document.createElement("div");
        actions.className = "account-actions";

        if (account.current) {
            const badge = document.createElement("span");
            badge.className = "account-current-badge";
            badge.textContent = "Current";
            actions.appendChild(badge);
        } else {
            const selectButton = document.createElement("button");
            selectButton.type = "button";
            selectButton.textContent = "Use";
            selectButton.addEventListener("click", () => selectAccount(account.id));
            actions.appendChild(selectButton);
        }

        const deleteButton = document.createElement("button");
        deleteButton.type = "button";
        deleteButton.className = "account-delete-button";
        deleteButton.textContent = "Delete";
        deleteButton.addEventListener("click", () => deleteAccount(account.id));
        actions.appendChild(deleteButton);

        item.appendChild(avatar);
        item.appendChild(summary);
        item.appendChild(actions);
        accountList.appendChild(item);
    });

    setAccountStatus("");
}

function createOfflineAccount(username) {
    if (!window.pywebview?.api?.create_offline_account) {
        setAccountStatus("Account API is not ready.");
        return;
    }

    setAccountStatus("Creating account...");
    window.pywebview.api.create_offline_account(username)
        .then(result => {
            if (!result?.ok) {
                setAccountStatus(result?.error || "Failed to create account.");
                return;
            }

            offlineUsernameInput.value = "";
            setAccountStatus("Offline account created.");
            loadAccounts(true);
        })
        .catch(error => {
            setAccountStatus("Failed to create account.");
            console.error("Failed to create account.", error);
        });
}

function startMicrosoftLogin() {
    if (!window.pywebview?.api?.start_msa_login) {
        setAccountStatus("Account API is not ready.");
        return;
    }

    setAccountStatus("Opening Microsoft login...");
    window.pywebview.api.start_msa_login()
        .then(result => {
            if (!result?.ok) {
                setAccountStatus(result?.error || "Failed to open login window.");
                return;
            }

            setAccountStatus(result.alreadyOpen ? "Login window is already open." : "Continue in the Microsoft login window.");
        })
        .catch(error => {
            setAccountStatus("Failed to open login window.");
            console.error("Failed to open login window.", error);
        });
}

function selectAccount(accountId) {
    setAccountStatus("Updating current account...");
    window.pywebview.api.select_account(accountId)
        .then(result => {
            setAccountStatus(result?.ok ? "Current account updated." : result?.error || "Failed to select account.");
            loadAccounts(true);
        })
        .catch(error => {
            setAccountStatus("Failed to select account.");
            console.error("Failed to select account.", error);
        });
}

function deleteAccount(accountId) {
    setAccountStatus("Deleting account...");
    window.pywebview.api.delete_account(accountId)
        .then(result => {
            setAccountStatus(result?.ok ? "Account deleted." : result?.error || "Failed to delete account.");
            loadAccounts(true);
        })
        .catch(error => {
            setAccountStatus("Failed to delete account.");
            console.error("Failed to delete account.", error);
        });
}

function clearAccountData() {
    setAccountStatus("Clearing account data...");
    window.pywebview.api.clear_account_data()
        .then(result => {
            setAccountStatus(result?.ok ? "AccountData cleared." : result?.error || "Failed to clear AccountData.");
            loadAccounts(true);
        })
        .catch(error => {
            setAccountStatus("Failed to clear AccountData.");
            console.error("Failed to clear AccountData.", error);
        });
}

window.__bakeAccountStatus = setAccountStatus;
window.__bakeAccountsChanged = () => loadAccounts(true);

function setInstanceStatus(message) {
    if (instanceStatus) {
        instanceStatus.textContent = message;
    }
}

function loadInstances(force = false) {
    if (!window.pywebview?.api?.get_instances) {
        setInstanceStatus("Instance API is not ready.");
        return Promise.resolve();
    }

    if (instancesLoadPromise && !force) {
        return instancesLoadPromise;
    }

    if (instancesLoaded && !force) {
        return Promise.resolve();
    }

    instancesLoadPromise = window.pywebview.api.get_instances()
        .then(result => {
            renderInstances(result);
            instancesLoaded = Boolean(result?.ok);
            return result;
        })
        .catch(error => {
            setInstanceStatus("Failed to load instances.");
            console.error("Failed to load instances.", error);
        })
        .finally(() => {
            instancesLoadPromise = null;
        });

    return instancesLoadPromise;
}

function renderInstances(result) {
    if (homeInstancesPath) {
        homeInstancesPath.textContent = result?.instancesDir || "Instances path unavailable.";
    }

    if (instancesPath) {
        instancesPath.textContent = result?.instancesDir || "Instances path unavailable.";
    }

    if (!result?.ok) {
        setInstanceStatus(result?.error || "Failed to load instances.");
        renderInstanceGrid(homeInstanceList, [], true);
        renderInstanceGrid(instanceList, [], false);
        return;
    }

    setInstanceStatus("");
    renderInstanceGrid(homeInstanceList, result.instances || [], true);
    renderInstanceGrid(instanceList, result.instances || [], false);
}

function applyInstanceDisplaySettings(settings) {
    const nextMode = settings?.display === "detail" ? "detail" : "icon";
    const changed = instanceDisplayMode !== nextMode;
    instanceDisplayMode = nextMode;

    if (changed && instancesLoaded) {
        loadInstances(true);
    }
}

function renderInstanceGrid(target, instances, compact) {
    if (!target) {
        return;
    }

    target.innerHTML = "";
    target.classList.toggle("instance-icon-grid", instanceDisplayMode === "icon");
    target.classList.toggle("instance-detail-grid-mode", instanceDisplayMode === "detail");

    if (!instances.length) {
        const empty = document.createElement("p");
        empty.className = "instance-empty";
        empty.textContent = "No instances yet.";
        target.appendChild(empty);
        return;
    }

    instances.forEach(instance => {
        target.appendChild(instanceDisplayMode === "icon"
            ? createInstanceIcon(instance, compact)
            : createInstanceCard(instance, compact));
    });
}

function getInstanceDisplayName(instance) {
    return instance.name || instance.id || "Unnamed";
}

function getInstanceInitial(instance) {
    if (instance?.icon?.initial) {
        return instance.icon.initial;
    }

    const name = getInstanceDisplayName(instance).trim();
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

function createInstanceIcon(instance, compact) {
    const card = document.createElement("article");
    card.className = compact ? "instance-app-card compact-instance-app-card" : "instance-app-card";
    card.dataset.instanceId = instance.id || "";
    card.setAttribute("aria-label", getInstanceDisplayName(instance));

    const icon = document.createElement("div");
    icon.className = "instance-app-icon";
    icon.style.setProperty("--instance-icon-bg", getInstanceIconColor(getInstanceDisplayName(instance)));

    if (instance.icon?.src) {
        const image = document.createElement("img");
        image.src = instance.icon.src;
        image.alt = "";
        icon.classList.add("instance-app-image-icon");
        icon.appendChild(image);
    } else {
        const shine = document.createElement("span");
        shine.className = "instance-app-icon-shine";
        icon.appendChild(shine);

        const glyph = document.createElement("span");
        glyph.className = "instance-app-icon-glyph";
        glyph.textContent = getInstanceInitial(instance);
        icon.appendChild(glyph);
    }

    const title = document.createElement("p");
    title.className = "instance-app-name";
    title.textContent = getInstanceDisplayName(instance);

    card.appendChild(icon);
    card.appendChild(title);

    if (instance.error) {
        card.classList.add("instance-app-card-error");
        card.title = instance.error;
    } else if (instance.clientVersion) {
        card.title = `${getInstanceDisplayName(instance)} | ${instance.clientVersion}`;
    }

    card.addEventListener("contextmenu", event => {
        event.preventDefault();
        openInstanceContextMenu(event.clientX, event.clientY, instance, card);
    });

    card.addEventListener("dblclick", () => launchInstanceDirectly(instance));

    return card;
}

function createInstanceCard(instance, compact) {
    const card = document.createElement("article");
    card.className = compact ? "instance-card compact-instance-card" : "instance-card";
    card.dataset.instanceId = instance.id || "";

    const title = document.createElement("input");
    title.className = "instance-name-input";
    title.type = "text";
    title.value = instance.name || instance.id || "Unnamed";
    title.disabled = !instance.editable;
    title.setAttribute("aria-label", "Instance name");

    const version = document.createElement("p");
    version.className = "instance-version";
    version.textContent = instance.clientVersion
        ? `${instance.clientVersion} | ${instance.type || "unknown"}`
        : instance.error || "Instance profile not found.";

    const meta = document.createElement("p");
    meta.className = "instance-meta";
    meta.textContent = instance.instanceFormat
        ? `${instance.instanceFormat} | ${instance.createDate || "unknown date"}`
        : instance.path;

    card.appendChild(title);
    card.appendChild(version);

    if (!compact) {
        card.appendChild(meta);

        const actions = document.createElement("div");
        actions.className = "instance-actions";

        const saveButton = document.createElement("button");
        saveButton.type = "button";
        saveButton.textContent = "Save";
        saveButton.disabled = !instance.editable;
        saveButton.addEventListener("click", () => renameInstance(instance.id, title.value));
        actions.appendChild(saveButton);

        card.appendChild(actions);
    }

    card.addEventListener("contextmenu", event => {
        event.preventDefault();
        openInstanceContextMenu(event.clientX, event.clientY, instance, card);
    });

    card.addEventListener("dblclick", event => {
        if (event.target.closest("input, button, textarea, select")) {
            return;
        }

        launchInstanceDirectly(instance);
    });

    return card;
}

function launchInstanceDirectly(instance) {
    if (!instance || !window.pywebview?.api?.launch_instance) {
        setInstanceStatus("Launch API is not ready.");
        return;
    }

    setInstanceStatus("Starting launch...");
    window.pywebview.api.launch_instance(instance.id)
        .then(result => {
            if (!result?.ok) {
                setInstanceStatus(result?.error || "Failed to launch instance.");
                return;
            }

            if (result.jobId) {
                watchInstanceJob(result.jobId, "Launch instance started.");
            } else {
                setInstanceStatus("Launch instance started.");
            }
        })
        .catch(error => {
            setInstanceStatus("Failed to launch instance.");
            console.error("Failed to launch instance.", error);
        });
}

function renameInstance(instanceId, newName) {
    if (!window.pywebview?.api?.rename_instance) {
        setInstanceStatus("Instance API is not ready.");
        return;
    }

    setInstanceStatus("Saving instance...");
    window.pywebview.api.rename_instance(instanceId, newName)
        .then(result => {
            if (!result?.ok) {
                setInstanceStatus(result?.error || "Failed to rename instance.");
                return;
            }

            setInstanceStatus("Instance saved.");
            loadInstances(true);
        })
        .catch(error => {
            setInstanceStatus("Failed to rename instance.");
            console.error("Failed to rename instance.", error);
        });
}



function openInstanceContextMenu(x, y, instance, card) {
    if (!instanceContextMenu) {
        return;
    }

    contextInstance = instance;
    contextInstanceCard = card;
    instanceContextMenu.hidden = false;

    const menuBox = instanceContextMenu.getBoundingClientRect();
    const safeX = Math.min(x, window.innerWidth - menuBox.width - 8);
    const safeY = Math.min(y, window.innerHeight - menuBox.height - 8);
    instanceContextMenu.style.left = `${Math.max(8, safeX)}px`;
    instanceContextMenu.style.top = `${Math.max(8, safeY)}px`;
}

function closeInstanceContextMenu() {
    if (!instanceContextMenu) {
        return;
    }

    instanceContextMenu.hidden = true;
    contextInstance = null;
    contextInstanceCard = null;
}

function editContextInstance() {
    const instance = contextInstance;
    closeInstanceContextMenu();

    if (!instance || !window.pywebview?.api?.open_instance_window) {
        setInstanceStatus("Instance window API is not ready.");
        return;
    }

    window.pywebview.api.open_instance_window(instance.id)
        .then(result => {
            if (!result?.ok) {
                setInstanceStatus(result?.error || "Failed to open instance window.");
            }
        })
        .catch(error => {
            setInstanceStatus("Failed to open instance window.");
            console.error("Failed to open instance window.", error);
        });
}

function editContextInstanceIcon() {
    const instance = contextInstance;
    closeInstanceContextMenu();

    if (!instance || !window.pywebview?.api?.open_instance_window) {
        setInstanceStatus("Instance window API is not ready.");
        return;
    }

    window.pywebview.api.open_instance_window(instance.id, "icon")
        .then(result => {
            if (!result?.ok) {
                setInstanceStatus(result?.error || "Failed to open icon editor.");
            }
        })
        .catch(error => {
            setInstanceStatus("Failed to open icon editor.");
            console.error("Failed to open icon editor.", error);
        });
}

function deleteContextInstance() {
    const instance = contextInstance;
    closeInstanceContextMenu();

    if (!instance || !window.pywebview?.api?.delete_instance) {
        setInstanceStatus("Delete API is not ready.");
        return;
    }

    if (!window.confirm(`Delete instance "${instance.name || instance.id}"?`)) {
        return;
    }

    setInstanceStatus("Deleting instance...");
    window.pywebview.api.delete_instance(instance.id)
        .then(result => {
            if (!result?.ok) {
                setInstanceStatus(result?.error || "Failed to delete instance.");
                return;
            }

            setInstanceStatus("Instance deleted.");
            loadInstances(true);
        })
        .catch(error => {
            setInstanceStatus("Failed to delete instance.");
            console.error("Failed to delete instance.", error);
        });
}

function launchContextInstance() {
    const instance = contextInstance;
    closeInstanceContextMenu();

    if (!instance || !window.pywebview?.api?.launch_instance) {
        setInstanceStatus("Launch API is not ready.");
        return;
    }

    setInstanceStatus("Starting launch...");
    window.pywebview.api.launch_instance(instance.id)
        .then(result => {
            if (!result?.ok) {
                setInstanceStatus(result?.error || "Failed to launch instance.");
                return;
            }

            if (result.jobId) {
                watchInstanceJob(result.jobId, "Launch started.");
            } else {
                setInstanceStatus("Launch started.");
            }
        })
        .catch(error => {
            setInstanceStatus("Failed to launch instance.");
            console.error("Failed to launch instance.", error);
        });
}

function watchInstanceJob(jobId, successMessage) {
    window.clearInterval(instanceJobTimer);
    instanceJobTimer = window.setInterval(() => {
        if (!window.pywebview?.api?.get_instance_job) {
            return;
        }

        window.pywebview.api.get_instance_job(jobId)
            .then(job => {
                if (!job?.ok) {
                    window.clearInterval(instanceJobTimer);
                    instanceJobTimer = null;
                    setInstanceStatus(job?.error || "Job not found.");
                    return;
                }

                setInstanceStatus(job.status || job.state || "Running...");
                if (!job.done) {
                    return;
                }

                window.clearInterval(instanceJobTimer);
                instanceJobTimer = null;
                setInstanceStatus(job.state === "failed" ? job.error || "Job failed." : successMessage);
            })
            .catch(error => {
                window.clearInterval(instanceJobTimer);
                instanceJobTimer = null;
                setInstanceStatus("Failed to read job status.");
                console.error("Failed to read instance job.", error);
            });
    }, 800);
}

function openCreateInstanceWindow() {
    if (!window.pywebview?.api?.open_create_instance_window) {
        setInstanceStatus("Create instance API is not ready.");
        return;
    }

    window.pywebview.api.open_create_instance_window()
        .then(result => {
            if (!result?.ok) {
                setInstanceStatus(result?.error || "Failed to open create instance window.");
            }
        })
        .catch(error => {
            setInstanceStatus("Failed to open create instance window.");
            console.error("Failed to open create instance window.", error);
        });
}

window.__bakeInstancesChanged = () => loadInstances(true);

instanceContextMenu?.addEventListener("click", event => {
    const button = event.target.closest("button[data-action]");
    if (!button) {
        return;
    }

    const action = button.dataset.action;
    if (action === "edit") {
        editContextInstance();
    } else if (action === "icon") {
        editContextInstanceIcon();
    } else if (action === "delete") {
        deleteContextInstance();
    } else if (action === "launch") {
        launchContextInstance();
    }
});

window.addEventListener("click", event => {
    if ((!instanceContextMenu || instanceContextMenu.hidden) && (!tabBarContextMenu || tabBarContextMenu.hidden)) {
        return;
    }

    if (!instanceContextMenu.contains(event.target)) {
        closeInstanceContextMenu();
    }

    if (!tabBarContextMenu.contains(event.target)) {
        closeTabButtonContextMenu()
    }
});

window.addEventListener("keydown", event => {
    if (event.key === "Escape") {
        closeInstanceContextMenu();
        closeTabButtonContextMenu();
    }
});

function renderSettingsPage(settings) {
    if (!settingsList) {
        return;
    }

    settingsList.innerHTML = "";

    const language = settings?.frontend?.language || currentLauncherLanguage;
    const theme = normalizeThemeSettings(settings?.frontend?.theme);
    selectedLauncherLanguage = language;
    const tabIds = getKnownTabIds();
    const tabs = settings?.frontend?.tabs || {
        order: tabIds,
        active: document.querySelector(".tab-button.active")?.getAttribute("data-target-container") || "",
        detached: [],
        hidden: []
    };
    const tabOrder = normalizeSettingsOrder(tabs.order || tabIds, tabIds);
    const instances = settings?.frontend?.instances || {
        display: instanceDisplayMode
    };
    const background = settings?.frontend?.background || currentBackgroundSettings;

    const frontendSection = document.createElement("section");
    frontendSection.className = "settings-section";

    const frontendTitle = document.createElement("h3");
    frontendTitle.textContent = "frontend";
    frontendSection.appendChild(frontendTitle);
    const frontendGroup = createSettingsGroup(frontendSection);
    frontendGroup.appendChild(createSettingsEditor("frontend", "language", language, "select", availableLanguages.map(value => ({
        value,
        label: value
    }))));
    frontendGroup.appendChild(createSettingsEditor("frontend", "theme", theme, "select", [
        {value: "light", label: "Light"},
        {value: "black", label: "Black"}
    ]));
    settingsList.appendChild(frontendSection);

    const tabsSection = document.createElement("section");
    tabsSection.className = "settings-section";

    const tabsTitle = document.createElement("h3");
    tabsTitle.textContent = "frontend.tabs";
    tabsSection.appendChild(tabsTitle);

    const tabsGroup = createSettingsGroup(tabsSection);
    tabsGroup.appendChild(createSettingsEditor("tabs", "order", tabOrder, "tabOrder", settingsTabItems));
    tabsGroup.appendChild(createSettingsEditor("tabs", "active", tabs.active || tabOrder[0] || "", "select", settingsTabItems));
    tabsGroup.appendChild(createSettingsEditor("tabs", "detached", tabs.detached || [], "multi", settingsDetachableTabItems));
    tabsGroup.appendChild(createSettingsEditor("tabs", "hidden", tabs.hidden || [], "multi", settingsHideableTabItems));
    settingsList.appendChild(tabsSection);

    const instancesSection = document.createElement("section");
    instancesSection.className = "settings-section";

    const instancesTitle = document.createElement("h3");
    instancesTitle.textContent = "frontend.instances";
    instancesSection.appendChild(instancesTitle);
    const instancesGroup = createSettingsGroup(instancesSection);
    instancesGroup.appendChild(createSettingsEditor("instances", "display", instances.display || "icon", "select", [
        {value: "icon", label: "Icon"},
        {value: "detail", label: "Detail"}
    ]));
    settingsList.appendChild(instancesSection);

    const backgroundSection = document.createElement("section");
    backgroundSection.className = "settings-section";

    const backgroundTitle = document.createElement("h3");
    backgroundTitle.textContent = "frontend.background";
    backgroundSection.appendChild(backgroundTitle);
    const backgroundGroup = createSettingsGroup(backgroundSection);
    backgroundGroup.appendChild(createSettingsEditor("background", "image", background.image || "", "text"));
    backgroundGroup.appendChild(createSettingsEditor("background", "blur", String(background.blur || 0), "text"));
    backgroundGroup.appendChild(createSettingsEditor("background", "mediaOpacity", String(background.mediaOpacity ?? 100), "text"));
    backgroundGroup.appendChild(createSettingsEditor("background", "surfaceAlpha", String(background.surfaceAlpha ?? 60), "text"));
    backgroundGroup.appendChild(createSettingsEditor("background", "childMode", background.childMode || "inherit", "select", [
        {value: "inherit", label: "Child windows: Apply main background"},
        {value: "none", label: "Child windows: No background"},
        {value: "custom", label: "Child windows: Different background"}
    ]));
    backgroundGroup.appendChild(createSettingsEditor("background", "childImage", background.childImage || "", "text"));
    backgroundGroup.appendChild(createSettingsEditor("background", "childBlur", String(background.childBlur || 0), "text"));
    settingsList.appendChild(backgroundSection);
}

function createSettingsGroup(section) {
    const group = document.createElement("div");
    group.className = "settings-group";
    section.appendChild(group);
    return group;
}

function switchSettingsPage(pageName) {
    activeSettingsPage = pageName === "jvm" ? "jvm" : "config";
    settingsSwitchButtons.forEach(button => {
        const isActive = button.dataset.settingsPage === activeSettingsPage;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-selected", isActive ? "true" : "false");
    });

    settingsList?.classList.toggle("hidden", activeSettingsPage !== "config");
    jvmSettingsList?.classList.toggle("hidden", activeSettingsPage !== "jvm");
    if (settingsPanelTitle) {
        settingsPanelTitle.textContent = activeSettingsPage === "jvm" ? "JVM Settings" : "frontend.toml";
    }
    if (settingsSaveButton) {
        settingsSaveButton.hidden = activeSettingsPage !== "config";
    }
    setSettingsSaveStatus("");

    if (activeSettingsPage === "jvm") {
        loadJvmSettingsList();
    }
}

function loadJvmSettingsList(force = false) {
    if (!jvmSettingsList) {
        return Promise.resolve();
    }

    if (jvmSettingsLoaded && !force) {
        return Promise.resolve();
    }

    if (!window.pywebview?.api?.get_managed_jvms) {
        jvmSettingsList.innerHTML = `<p class="settings-empty">${window.t("JVM API is not ready.")}</p>`;
        return Promise.resolve();
    }

    jvmSettingsList.innerHTML = `<p class="settings-empty">${window.t("Loading JVMs...")}</p>`;
    return window.pywebview.api.get_managed_jvms(force)
        .then(result => {
            renderJvmSettings(result);
            jvmSettingsLoaded = Boolean(result?.ok);
            return result;
        })
        .catch(error => {
            jvmSettingsList.innerHTML = `<p class="settings-empty">${window.t("Failed to load JVM settings.")}</p>`;
            console.error("Failed to load JVM settings.", error);
        });
}

function renderJvmSettings(result) {
    if (!jvmSettingsList) {
        return;
    }

    jvmSettingsList.innerHTML = "";

    const installSection = document.createElement("section");
    installSection.className = "settings-section jvm-install-section";
    const installTitle = document.createElement("h3");
    installTitle.textContent = "Download";
    const installControls = document.createElement("div");
    installControls.className = "jvm-download-controls";

    const versionSelect = document.createElement("select");
    versionSelect.className = "settings-input";
    for (const optionData of result?.downloadOptions || []) {
        const option = document.createElement("option");
        option.value = optionData.majorVersion || "";
        option.textContent = `${optionData.name || `Java ${option.value}`}${optionData.installed ? " (installed)" : ""}`;
        versionSelect.appendChild(option);
    }

    const downloadButton = document.createElement("button");
    downloadButton.type = "button";
    downloadButton.className = "jvm-download-button";
    downloadButton.textContent = "Download";
    downloadButton.addEventListener("click", () => downloadJvm(versionSelect.value));
    installControls.append(versionSelect, downloadButton);
    installSection.append(installTitle, installControls);
    jvmSettingsList.appendChild(installSection);

    const listSection = document.createElement("section");
    listSection.className = "settings-section";
    const listHeader = document.createElement("div");
    listHeader.className = "jvm-list-header";
    const listTitle = document.createElement("h3");
    listTitle.textContent = "Installed and System JVMs";
    const checkAllButton = document.createElement("button");
    checkAllButton.type = "button";
    checkAllButton.className = "jvm-check-all-button";
    checkAllButton.textContent = "Check All";
    checkAllButton.disabled = !(result?.jvms || []).length;
    checkAllButton.addEventListener("click", () => checkAllJvms(result?.jvms || []));
    listHeader.append(listTitle, checkAllButton);
    const registry = document.createElement("p");
    registry.className = "jvm-registry-path";
    registry.textContent = `Registry: ${result?.registryPath || ""}`;
    const list = document.createElement("div");
    list.className = "jvm-list";

    const runtimes = result?.jvms || [];
    if (!runtimes.length) {
        const empty = document.createElement("p");
        empty.className = "settings-empty";
        empty.textContent = "No JVMs found.";
        list.appendChild(empty);
    }

    for (const runtime of runtimes) {
        list.appendChild(createJvmItem(runtime));
    }

    listSection.append(listHeader, registry, list);
    jvmSettingsList.appendChild(listSection);
}

function createJvmItem(runtime) {
    const item = document.createElement("article");
    item.className = "jvm-item";

    const summary = document.createElement("div");
    summary.className = "jvm-summary";

    const title = document.createElement("strong");
    title.textContent = `${runtime.source || "JVM"} Java ${runtime.majorVersion || "?"}`;

    const meta = document.createElement("span");
    meta.textContent = `Version ${runtime.version || "unknown"} | ${runtime.validationMethod || "not checked"}`;

    const path = document.createElement("small");
    path.textContent = runtime.path || "";

    summary.append(title, meta, path);

    const actions = document.createElement("div");
    actions.className = "jvm-actions";
    const checkButton = document.createElement("button");
    checkButton.type = "button";
    checkButton.className = "jvm-check-button";
    checkButton.textContent = "Check";
    checkButton.addEventListener("click", () => checkJvm(runtime.id));
    actions.appendChild(checkButton);

    if (runtime.canDelete) {
        const deleteButton = document.createElement("button");
        deleteButton.type = "button";
        deleteButton.className = "jvm-delete-button";
        deleteButton.textContent = "Delete";
        deleteButton.addEventListener("click", () => deleteJvm(runtime.id));
        actions.appendChild(deleteButton);
    } else {
        const badge = document.createElement("span");
        badge.className = "jvm-readonly-badge";
        badge.textContent = runtime.managed ? "Managed" : "System";
        actions.appendChild(badge);
    }

    item.append(summary, actions);
    return item;
}

function checkJvm(runtimeId) {
    if (!runtimeId || !window.pywebview?.api?.check_jvm) {
        setSettingsSaveStatus("JVM API is not ready.");
        return;
    }

    const message = window.t("This will run Java to test the selected runtime. A Java window may appear briefly; you can close it. Continue?");
    if (!window.confirm(message)) {
        return;
    }

    setSettingsSaveStatus("Checking JVM...");
    window.pywebview.api.check_jvm(runtimeId)
        .then(result => {
            setSettingsSaveStatus(result?.ok ? "Checked." : result?.error || "Check failed.");
            if (result?.ok) {
                renderJvmSettings(result);
                jvmSettingsLoaded = true;
            }
        })
        .catch(error => {
            setSettingsSaveStatus("Check failed.");
            console.error("Failed to check JVM.", error);
        });
}

async function checkAllJvms(runtimes) {
    const runtimeIds = (runtimes || [])
        .map(runtime => runtime?.id)
        .filter(Boolean);

    if (!runtimeIds.length || !window.pywebview?.api?.check_jvm) {
        setSettingsSaveStatus("JVM API is not ready.");
        return;
    }

    const message = window.t("This will run Java to test every detected runtime. Java windows may appear briefly; you can close them. Continue?");
    if (!window.confirm(message)) {
        return;
    }

    let latestResult = null;
    let failed = 0;
    for (let index = 0; index < runtimeIds.length; index += 1) {
        setSettingsSaveStatus(`Checking JVMs... ${index + 1}/${runtimeIds.length}`);
        try {
            const result = await window.pywebview.api.check_jvm(runtimeIds[index]);
            if (result?.ok) {
                latestResult = result;
            } else {
                failed += 1;
            }
        } catch (error) {
            failed += 1;
            console.error("Failed to check JVM.", error);
        }
    }

    if (latestResult) {
        renderJvmSettings(latestResult);
        jvmSettingsLoaded = true;
    } else {
        jvmSettingsLoaded = false;
        await loadJvmSettingsList(true);
    }

    setSettingsSaveStatus(failed ? `Checked with ${failed} failed.` : "Checked all.");
}

function downloadJvm(javaMajorVersion) {
    if (!window.pywebview?.api?.download_jvm) {
        setSettingsSaveStatus("JVM API is not ready.");
        return;
    }

    setSettingsSaveStatus("Starting...");
    window.pywebview.api.download_jvm(javaMajorVersion)
        .then(result => {
            if (!result?.ok) {
                setSettingsSaveStatus(result?.error || "Download failed.");
                return;
            }

            if (result.jobId) {
                watchJvmJob(result.jobId);
                return;
            }

            setSettingsSaveStatus("Download started.");
            jvmSettingsLoaded = false;
            loadJvmSettingsList(true);
        })
        .catch(error => {
            setSettingsSaveStatus("Download failed.");
            console.error("Failed to start JVM download.", error);
        });
}

function deleteJvm(runtimeId) {
    if (!runtimeId || !window.pywebview?.api?.delete_jvm) {
        setSettingsSaveStatus("Delete API is not ready.");
        return;
    }

    if (!window.confirm("Delete this launcher-installed JVM?")) {
        return;
    }

    setSettingsSaveStatus("Deleting...");
    window.pywebview.api.delete_jvm(runtimeId)
        .then(result => {
            setSettingsSaveStatus(result?.ok ? "Deleted." : result?.error || "Delete failed.");
            if (result?.ok) {
                renderJvmSettings(result);
                jvmSettingsLoaded = true;
            }
        })
        .catch(error => {
            setSettingsSaveStatus("Delete failed.");
            console.error("Failed to delete JVM.", error);
        });
}

function watchJvmJob(jobId) {
    window.clearInterval(jvmJobTimer);
    jvmJobTimer = window.setInterval(() => {
        if (!window.pywebview?.api?.get_instance_job) {
            window.clearInterval(jvmJobTimer);
            return;
        }

        window.pywebview.api.get_instance_job(jobId)
            .then(job => {
                if (!job?.ok) {
                    setSettingsSaveStatus(job?.error || "Job not found.");
                    window.clearInterval(jvmJobTimer);
                    return;
                }

                const total = Number(job.total || 0);
                const progress = Number(job.progress || 0);
                const suffix = total > 0 ? ` ${progress}/${total}` : "";
                setSettingsSaveStatus(`${job.status || "Running..."}${suffix}`);

                if (job.done) {
                    window.clearInterval(jvmJobTimer);
                    setSettingsSaveStatus(job.state === "failed" ? job.error || "Download failed." : "Installed.");
                    jvmSettingsLoaded = false;
                    loadJvmSettingsList(true);
                }
            })
            .catch(error => {
                setSettingsSaveStatus("Failed to read job status.");
                window.clearInterval(jvmJobTimer);
                console.error("Failed to watch JVM job.", error);
            });
    }, 700);
}

function normalizeSettingsOrder(order, allowedItems) {
    const allowed = new Set(allowedItems);
    const normalized = [];
    (Array.isArray(order) ? order : []).forEach(item => {
        if (allowed.has(item) && !normalized.includes(item)) {
            normalized.push(item);
        }
    });
    allowedItems.forEach(item => {
        if (!normalized.includes(item)) {
            normalized.push(item);
        }
    });
    return normalized;
}

function normalizeSettingsOptions(options, fallbackValue = "") {
    const normalized = (options || []).map(option => {
        if (typeof option === "string") {
            return {value: option, label: option};
        }
        return {
            value: String(option?.value || ""),
            label: String(option?.label || option?.value || "")
        };
    }).filter(option => option.value);

    if (!normalized.length && fallbackValue) {
        normalized.push({value: fallbackValue, label: fallbackValue});
    }
    return normalized;
}

function createSettingsEditor(group, key, value, type, options = []) {
    const row = document.createElement(type === "multi" || type === "tabOrder" ? "div" : "label");
    row.className = "settings-row";
    row.dataset.settingGroup = group;
    row.dataset.settingKey = key;
    row.dataset.settingType = type;

    const keyElement = document.createElement("span");
    keyElement.className = "settings-key";
    keyElement.textContent = key;

    const valueElement = document.createElement("span");
    valueElement.className = "settings-value";

    if (type === "tabOrder") {
        valueElement.appendChild(createTabOrderEditor(value, options));
    } else if (type === "multi") {
        valueElement.appendChild(createMultiSelectEditor(value, options));
    } else if (type === "array") {
        const input = document.createElement("textarea");
        input.className = "settings-input settings-textarea";
        input.rows = Math.max(2, value.length || 1);
        input.value = value.join("\n");
        valueElement.appendChild(input);
    } else if (type === "select") {
        const input = document.createElement("select");
        input.className = "settings-input";

        const normalizedOptions = normalizeSettingsOptions(options, value || "en");
        normalizedOptions.forEach(optionValue => {
            const option = document.createElement("option");
            option.value = optionValue.value;
            option.textContent = optionValue.label;
            input.appendChild(option);
        });

        input.value = value || normalizedOptions[0]?.value || "en";
        valueElement.appendChild(input);
    } else {
        const input = document.createElement("input");
        input.className = "settings-input";
        input.type = "text";
        input.value = value;
        if (group === "background" && (key === "image" || key === "childImage")) {
            valueElement.appendChild(createBackgroundImageEditor(input, key));
        } else {
            valueElement.appendChild(input);
        }
    }

    row.appendChild(keyElement);
    row.appendChild(valueElement);
    return row;
}

function createBackgroundImageEditor(input, key) {
    const wrapper = document.createElement("div");
    wrapper.className = "settings-file-input";

    const browseButton = document.createElement("button");
    browseButton.className = "settings-file-button";
    browseButton.type = "button";
    browseButton.textContent = "Browse";
    browseButton.addEventListener("click", () => browseBackgroundImage(input, key));

    const clearButton = document.createElement("button");
    clearButton.className = "settings-file-button";
    clearButton.type = "button";
    clearButton.textContent = "Clear";
    clearButton.addEventListener("click", () => {
        input.value = "";
        if (key === "image") {
            applyBackgroundSettings({
                image: "",
                blur: readBackgroundBlurInput()
            });
        }
    });

    wrapper.append(input, browseButton, clearButton);
    return wrapper;
}

function readBackgroundBlurInput() {
    const row = settingsList?.querySelector('.settings-row[data-setting-group="background"][data-setting-key="blur"]');
    const input = row?.querySelector("input, select, textarea");
    return input?.value || currentBackgroundSettings.blur || 0;
}

function browseBackgroundImage(input, key) {
    if (!window.pywebview?.api?.browse_frontend_background_image) {
        setSettingsSaveStatus("Image picker is not ready.");
        return;
    }

    setSettingsSaveStatus("Choosing image...");
    window.pywebview.api.browse_frontend_background_image()
        .then(result => {
            if (result?.cancelled) {
                setSettingsSaveStatus("");
                return;
            }

            if (!result?.ok) {
                setSettingsSaveStatus("Choose failed");
                console.error("Failed to choose background image.", result?.error);
                return;
            }

            input.value = result.image || "";
            if (key === "image") {
                applyBackgroundSettings({
                    image: result.image || "",
                    imageDataUri: result.imageDataUri || result.image || "",
                    blur: readBackgroundBlurInput()
                });
            }
            setSettingsSaveStatus("Image selected");
        })
        .catch(error => {
            setSettingsSaveStatus("Choose failed");
            console.error("Failed to choose background image.", error);
        });
}

function createTabOrderEditor(order, options) {
    const list = document.createElement("div");
    list.className = "settings-tab-order-list";
    const normalizedOptions = normalizeSettingsOptions(options);
    const normalizedOrder = normalizeSettingsOrder(order, normalizedOptions.map(option => option.value));

    normalizedOrder.forEach((targetId, index) => {
        const item = document.createElement("label");
        item.className = "settings-tab-order-item";

        const position = document.createElement("span");
        position.textContent = String(index + 1);

        const select = document.createElement("select");
        select.className = "settings-input settings-tab-position";
        select.dataset.previousValue = targetId;

        normalizedOptions.forEach(optionValue => {
            const option = document.createElement("option");
            option.value = optionValue.value;
            option.textContent = optionValue.label;
            select.appendChild(option);
        });

        select.value = targetId;
        select.addEventListener("change", syncTabOrderSelects);
        item.append(position, select);
        list.appendChild(item);
    });

    return list;
}

function syncTabOrderSelects(event) {
    const changed = event.currentTarget;
    const previousValue = changed.dataset.previousValue;
    const nextValue = changed.value;
    const list = changed.closest(".settings-tab-order-list");

    if (!previousValue || previousValue === nextValue || !list) {
        changed.dataset.previousValue = nextValue;
        return;
    }

    const duplicate = Array.from(list.querySelectorAll(".settings-tab-position"))
        .find(select => select !== changed && select.value === nextValue);
    if (duplicate) {
        duplicate.value = previousValue;
        duplicate.dataset.previousValue = previousValue;
    }
    changed.dataset.previousValue = nextValue;
}

function createMultiSelectEditor(value, options) {
    const wrapper = document.createElement("div");
    wrapper.className = "settings-multi-select";
    const selected = new Set(Array.isArray(value) ? value : []);
    const normalizedOptions = normalizeSettingsOptions(options);

    const list = document.createElement("div");
    list.className = "settings-checkbox-list";

    const selectedList = document.createElement("div");
    selectedList.className = "settings-selected-list";

    function updateSelectedList() {
        const checkedLabels = Array.from(list.querySelectorAll("input[type='checkbox']:checked"))
            .map(input => normalizedOptions.find(option => option.value === input.value)?.label || input.value);

        selectedList.innerHTML = "";
        if (!checkedLabels.length) {
            const empty = document.createElement("span");
            empty.className = "settings-selected-empty";
            empty.textContent = "None";
            selectedList.appendChild(empty);
            return;
        }

        checkedLabels.forEach(label => {
            const chip = document.createElement("span");
            chip.className = "settings-selected-item";
            chip.textContent = label;
            selectedList.appendChild(chip);
        });
    }

    normalizedOptions.forEach(optionValue => {
        const label = document.createElement("label");
        label.className = "settings-checkbox-item";

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = optionValue.value;
        checkbox.checked = selected.has(optionValue.value);
        checkbox.addEventListener("change", updateSelectedList);

        const text = document.createElement("span");
        text.textContent = optionValue.label;

        label.append(checkbox, text);
        list.appendChild(label);
    });

    wrapper.append(list, selectedList);
    updateSelectedList();
    return wrapper;
}

function readSettingsEditors() {
    const editedSettings = {
        language: selectedLauncherLanguage,
        theme: document.body.classList.contains("bake-theme-black") ? "black" : "light",
        tabs: {},
        instances: {},
        background: {}
    };

    settingsList?.querySelectorAll(".settings-row[data-setting-key]").forEach(row => {
        const group = row.dataset.settingGroup || "tabs";
        const key = row.dataset.settingKey;
        const type = row.dataset.settingType;
        const target = group === "frontend" ? editedSettings : editedSettings[group];

        if (!target) {
            return;
        }

        if (type === "tabOrder") {
            target[key] = normalizeSettingsOrder(
                Array.from(row.querySelectorAll(".settings-tab-position")).map(select => select.value),
                getKnownTabIds()
            );
            return;
        }

        if (type === "multi") {
            target[key] = Array.from(row.querySelectorAll("input[type='checkbox']:checked"))
                .map(input => input.value)
                .filter(Boolean);
            if (group === "tabs" && key === "hidden") {
                target[key] = normalizeHiddenTabIds(target[key]);
            }
            return;
        }

        const input = row.querySelector("input, select, textarea");
        if (!input) {
            return;
        }

        if (type === "array") {
            target[key] = input.value
                .split("\n")
                .map(item => item.trim())
                .filter(Boolean);
            return;
        }

        target[key] = input.value.trim();
    });

    return editedSettings;
}

function applyEditedSettings(settings) {
    const tabs = settings?.tabs;
    const languageChanged = settings?.language && settings.language !== currentLauncherLanguage;
    if (settings?.language) {
        selectedLauncherLanguage = settings.language;
    }

    applyThemeSettings(settings?.theme);
    applyInstanceDisplaySettings(settings?.instances);
    applyBackgroundSettings(settings?.background);

    if (tabs && Array.isArray(tabs.order)) {
        tabs.order.forEach(targetId => {
            const button = getTabButtonByTargetId(targetId);
            if (button) {
                tabBar.appendChild(button);
            }
        });
    }

    applyHiddenTabs(tabs?.hidden);

    const activeButton = tabs ? getTabButtonByTargetId(tabs.active) : null;
    if (activeButton && !activeButton.classList.contains("hidden-tab")) {
        activateTab(activeButton, false);
    } else if (tabs?.hidden?.length) {
        activateFirstDockedTab();
    }

    return languageChanged;
}

function setSettingsSaveStatus(message) {
    if (!settingsSaveStatus) {
        return;
    }

    settingsSaveStatus.textContent = message;
}

function saveSettingsFromPage() {
    if (!window.pywebview?.api?.save_frontend_settings) {
        return;
    }

    const editedSettings = readSettingsEditors();
    setSettingsSaveStatus("Saving...");

    window.pywebview.api.save_frontend_settings(editedSettings)
        .then(settings => {
            settings = normalizeFrontendSettingsResponse(settings);
            const latestSettings = settings?.frontend || editedSettings;
            const languageChanged = applyEditedSettings(latestSettings);
            setSettingsSaveStatus(languageChanged ? "Saved. Restart to apply language." : "Saved");
            if (languageChanged) {
                showBakeMessageBox(
                    window.t("Restart required"),
                    `<p>${window.t("Language settings were saved.")}</p><p>${window.t("Restart KiteeLauncher to apply the selected language.")}</p>`
                );
            }
            suppressSettingsReloadDisplay = true;
            applyReloadedFrontendSettings(settings);
        })
        .finally(() => {
            suppressSettingsReloadDisplay = false;
        })
        .catch(error => {
            setSettingsSaveStatus("Save failed");
            console.error("Failed to save edited settings.", error);
        });
}

function getCoveredTab() {
    if (!draggedTab) {
        return null;
    }

    const draggedBox = draggedTab.getBoundingClientRect();
    const candidates = getVisibleDockedTabButtons().filter(button => button !== draggedTab);

    return candidates.reduce((covered, button) => {
        const box = button.getBoundingClientRect();
        const overlap = Math.min(draggedBox.right, box.right) - Math.max(draggedBox.left, box.left);
        const coverage = Math.max(0, overlap) / box.width;

        if (coverage >= reorderCoverage && coverage > covered.coverage) {
            return {coverage, button};
        }

        return covered;
    }, {coverage: 0, button: null}).button;
}

function moveDraggedTab(targetTab) {
    const beforeMoveBox = draggedTab.getBoundingClientRect();

    if (dragOffsetX > 0) {
        tabBar.insertBefore(draggedTab, targetTab.nextElementSibling);
    } else {
        tabBar.insertBefore(draggedTab, targetTab);
    }

    const afterMoveBox = draggedTab.getBoundingClientRect();
    const layoutShift = afterMoveBox.left - beforeMoveBox.left;
    dragStartX += layoutShift;
    dragOffsetX -= layoutShift;
    draggedTab.style.transform = `translate(${dragOffsetX}px, ${dragOffsetY}px)`;
}

function focusDetachedTab(targetId) {
    if (!window.pywebview?.api?.focus_detached_tab) {
        return;
    }

    window.pywebview.api.focus_detached_tab(targetId).catch(error => {
        console.error("Failed to focus detached tab.", error);
    });
}

function activateFirstDockedTab() {
    const nextButton = getVisibleDockedTabButtons()[0];
    if (nextButton) {
        activateTab(nextButton, false);
        return;
    }

    getTabButtons().forEach(button => {
        button.classList.remove("active");
        button.removeAttribute("aria-current");
    });
}

async function detachTab(button) {
    const targetContainer = getTargetContainerByButton(button);
    const targetId = button.getAttribute("data-target-container");

    if (targetContainer.id === "home_container") {
        return;
    }

    if (!targetContainer || button.classList.contains("detached-tab")) {
        focusDetachedTab(targetId);
        return;
    }

    if (!window.pywebview?.api?.detach_tab) {
        return;
    }

    const title = button.innerText.trim();
    const bodyHtml = targetContainer.innerHTML;

    button.classList.add("detached-tab");
    button.classList.remove("active");
    button.removeAttribute("aria-current");
    targetContainer.classList.remove("active-container", "entering-right", "exiting-left");
    targetContainer.classList.add("hidden");
    activateFirstDockedTab();

    try {
        const result = await window.pywebview.api.detach_tab(targetId, title, bodyHtml);
        if (!result?.ok) {
            throw new Error(result?.error || "Detach failed.");
        }
        saveFrontendSettings();
    } catch (error) {
        console.error("Failed to detach tab.", error);
        dockSystemTab(targetId);
    }
}

function dockSystemTab(targetId) {
    const button = tabBar?.querySelector(`[data-target-container="${targetId}"]`);
    const targetContainer = document.getElementById(targetId);

    if (!button || !targetContainer) {
        return;
    }

    button.classList.remove("detached-tab");
    targetContainer.classList.add("hidden");
    targetContainer.classList.remove("active-container", "entering-right", "exiting-left");
    activateTab(button, false);
    saveFrontendSettings();
}

window.__bakeDockTab = dockSystemTab;

tabBar?.addEventListener("click", event => {
    const button = event.target.closest(".tab-button");
    if (!button || !tabBar.contains(button)) {
        return;
    }

    if (didDragTab) {
        event.preventDefault();
        return;
    }

    activateTab(button);
});

tabBar?.addEventListener("wheel", event => {
    if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) {
        return;
    }

    event.preventDefault();
    tabBar.scrollLeft += event.deltaY;
}, {passive: false});

tabBar?.addEventListener("pointerdown", event => {
    const button = event.target.closest(".tab-button");
    if (!button || event.button !== 0) {
        return;
    }

    draggedTab = button;
    dragPointerId = event.pointerId;
    dragStartX = event.clientX;
    dragStartY = event.clientY;
    dragOffsetX = 0;
    dragOffsetY = 0;
    didDragTab = false;
    didDetachTab = false;

    button.setPointerCapture(event.pointerId);
    button.classList.add("dragging-tab");
    tabBar.classList.add("sorting");
});

tabBar?.addEventListener("pointermove", event => {
    if (!draggedTab || event.pointerId !== dragPointerId) {
        return;
    }

    dragOffsetX = event.clientX - dragStartX;
    dragOffsetY = event.clientY - dragStartY;
    draggedTab.style.transform = `translate(${dragOffsetX}px, ${dragOffsetY}px)`;

    if (Math.abs(dragOffsetX) > 6 || Math.abs(dragOffsetY) > 6) {
        didDragTab = true;
    }

    if (dragOffsetY > detachDistance) {
        didDetachTab = true;
        detachTab(draggedTab);
        stopTabDrag(event);
        return;
    }

    if (Math.abs(dragOffsetX) > Math.abs(dragOffsetY)) {
        const coveredTab = getCoveredTab();
        if (coveredTab) {
            moveDraggedTab(coveredTab);
        }
    }
});

function stopTabDrag(event) {
    if (!draggedTab || event.pointerId !== dragPointerId) {
        return;
    }

    draggedTab.style.transform = "";
    draggedTab.classList.remove("dragging-tab");
    tabBar?.classList.remove("sorting");

    if (draggedTab.hasPointerCapture(event.pointerId)) {
        draggedTab.releasePointerCapture(event.pointerId);
    }

    draggedTab = null;
    dragPointerId = null;
    dragOffsetX = 0;

    if (didDragTab && !didDetachTab) {
        saveFrontendSettings();
    }

    window.setTimeout(() => {
        didDragTab = false;
    }, 0);
}

tabBar?.addEventListener("pointerup", stopTabDrag);
tabBar?.addEventListener("pointercancel", stopTabDrag);
tabBar?.addEventListener("pointerleave", stopTabDrag);
settingsSwitchButtons.forEach(button => {
    button.addEventListener("click", () => switchSettingsPage(button.dataset.settingsPage));
});
settingsRefreshButton?.addEventListener("click", () => {
    if (activeSettingsPage === "jvm") {
        jvmSettingsLoaded = false;
        loadJvmSettingsList(true);
        return;
    }
    loadFrontendSettings(false);
});
settingsSaveButton?.addEventListener("click", saveSettingsFromPage);
accountRefreshButton?.addEventListener("click", () => loadAccounts(true));
accountLoginButton?.addEventListener("click", startMicrosoftLogin);
accountCreateForm?.addEventListener("submit", event => {
    event.preventDefault();
    createOfflineAccount(offlineUsernameInput.value);
});
accountClearButton?.addEventListener("click", clearAccountData);
homeInstancesRefreshButton?.addEventListener("click", () => loadInstances(true));
instancesRefreshButton?.addEventListener("click", () => loadInstances(true));
tabbarCreateInstanceButton?.addEventListener("click", openCreateInstanceWindow);
window.addEventListener("pywebviewready", loadFrontendSettings);
