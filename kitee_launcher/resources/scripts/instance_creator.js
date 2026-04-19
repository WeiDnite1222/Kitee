const createInstanceForm = document.getElementById("create_instance_form");
const createInstanceName = document.getElementById("create_instance_name");
const createClientVersion = document.getElementById("create_client_version");
const createVersionType = document.getElementById("create_version_type");
const createModLoader = document.getElementById("create_mod_loader");
const createModLoaderVersion = document.getElementById("create_mod_loader_version");
const createModLoaderVersionLabel = document.getElementById("create_mod_loader_version_label");
const createJavaMajorVersion = document.getElementById("create_java_major_version");
const createMainClass = document.getElementById("create_main_class");
const createSkipGameFiles = document.getElementById("create_skip_game_files");
const createSkipJavaDownload = document.getElementById("create_skip_java_download");
const createInstanceStatus = document.getElementById("create_instance_status");
const createInstanceProgress = document.getElementById("create_instance_progress");
const createInstanceProgressFill = document.getElementById("create_instance_progress_fill");
const createInstanceSubmit = document.getElementById("create_instance_submit");
const createInstanceAddTask = document.getElementById("create_instance_add_task");
const createInstanceTaskList = document.getElementById("create_instance_task_list");
let createInstanceTasks = [];
let createInstanceSingleJobTimer = null;
let createInstanceBatchTimer = null;
let createInstanceTaskCounter = 0;
let createInstanceBatchRunning = false;
let createInstanceActiveTaskIds = new Set();
let minecraftVersions = [];
let minecraftVersionsPromise = null;

function setCreateInstanceStatus(message) {
    createInstanceStatus.textContent = message;
}

function setCreateInstanceProgress(progress, total) {
    const safeProgress = Math.max(0, Number(progress || 0));
    const safeTotal = Math.max(0, Number(total || 0));
    const percent = safeTotal ? Math.min(100, Math.round((safeProgress / safeTotal) * 100)) : 0;
    createInstanceProgress.style.setProperty("--progress", `${percent}%`);
    createInstanceProgress.setAttribute("aria-valuenow", String(percent));
    createInstanceProgressFill.textContent = safeTotal ? `${percent}%` : "";
}

function progressPercent(progress, total, done) {
    if (done) {
        return 100;
    }

    const safeProgress = Math.max(0, Number(progress || 0));
    const safeTotal = Math.max(0, Number(total || 0));
    return safeTotal ? Math.min(100, Math.round((safeProgress / safeTotal) * 100)) : 0;
}

function getCreateInstancePayload() {
    const skipGameFiles = createSkipGameFiles.checked;
    return {
        name: createInstanceName.value.trim(),
        clientVersion: createClientVersion.value,
        type: createVersionType.value,
        modLoader: createModLoader.value,
        modLoaderVersion: createModLoaderVersion.value.trim(),
        skipJavaDownload: createSkipJavaDownload.checked,
        javaMajorVersion: createJavaMajorVersion.value.trim(),
        mainClass: createMainClass.value.trim(),
        skipGameFiles,
        downloadGameFiles: !skipGameFiles
    };
}

function taskSubtitle(payload) {
    const loader = payload.modLoader && payload.modLoader !== "none"
        ? `, ${payload.modLoader}${payload.modLoaderVersion ? ` ${payload.modLoaderVersion}` : ""}`
        : "";
    return `${payload.clientVersion || "No version"} (${payload.type || "custom"}${loader})`;
}

function makeCreateInstanceTask(payload) {
    return {
        id: `create-task-${++createInstanceTaskCounter}`,
        payload,
        jobId: "",
        state: "pending",
        status: "Pending.",
        progress: 0,
        total: 0,
        error: "",
        done: false
    };
}

function validateCreateInstancePayload(payload) {
    if (!payload.name) {
        return "Instance name is required.";
    }

    if (!payload.clientVersion) {
        return "Minecraft version is required.";
    }

    const sameName = createInstanceTasks.some(task => task.payload.name.toLowerCase() === payload.name.toLowerCase() && !task.done);
    if (sameName) {
        return "This instance is already in the task list.";
    }

    return "";
}

function setCreateInstanceFormLocked(locked) {
    createInstanceBatchRunning = locked;
    createInstanceSubmit.disabled = locked;
    createInstanceAddTask.disabled = locked;
}

function updateCreateInstanceSubmitMode() {
    createInstanceSubmit.textContent = createInstanceTasks.some(task => !task.done) ? "Start tasks" : "Create";
}

function renderCreateInstanceTasks() {
    createInstanceTaskList.innerHTML = "";
    updateCreateInstanceSubmitMode();

    if (!createInstanceTasks.length) {
        const empty = document.createElement("p");
        empty.className = "create-instance-task-empty";
        empty.textContent = "No pending instances.";
        createInstanceTaskList.append(empty);
        updateCreateInstanceTotalProgress();
        return;
    }

    for (const task of createInstanceTasks) {
        const item = document.createElement("article");
        item.className = `create-instance-task-item task-${task.state || "pending"}`;

        const summary = document.createElement("div");
        summary.className = "create-instance-task-summary";

        const title = document.createElement("strong");
        title.textContent = task.payload.name || "Unnamed instance";

        const meta = document.createElement("span");
        meta.textContent = taskSubtitle(task.payload);

        const status = document.createElement("small");
        const percent = progressPercent(task.progress, task.total, task.done);
        const count = Number(task.total || 0) > 0 ? ` (${Number(task.progress || 0)}/${Number(task.total || 0)})` : "";
        status.textContent = `${task.status || task.state || "Pending."}${count}`;

        summary.append(title, meta, status);

        const progress = document.createElement("div");
        progress.className = "create-instance-task-progress";
        progress.setAttribute("role", "progressbar");
        progress.setAttribute("aria-valuemin", "0");
        progress.setAttribute("aria-valuemax", "100");
        progress.setAttribute("aria-valuenow", String(percent));
        progress.style.setProperty("--progress", `${percent}%`);
        progress.append(document.createElement("span"));

        item.append(summary, progress);

        if (!createInstanceBatchRunning) {
            const removeButton = document.createElement("button");
            removeButton.type = "button";
            removeButton.textContent = "Remove";
            removeButton.addEventListener("click", () => {
                createInstanceTasks = createInstanceTasks.filter(candidate => candidate.id !== task.id);
                renderCreateInstanceTasks();
                setCreateInstanceStatus(createInstanceTasks.length ? "Task removed." : "Ready.");
            });
            item.append(removeButton);
        }

        createInstanceTaskList.append(item);
    }

    updateCreateInstanceTotalProgress();
}

function updateCreateInstanceTotalProgress() {
    if (!createInstanceTasks.length) {
        setCreateInstanceProgress(0, 0);
        return;
    }

    const trackedTasks = createInstanceBatchRunning
        ? createInstanceTasks.filter(task => createInstanceActiveTaskIds.has(task.id))
        : createInstanceTasks;

    if (!trackedTasks.length) {
        setCreateInstanceProgress(0, 0);
        return;
    }

    const totalPercent = trackedTasks.reduce((sum, task) => {
        return sum + progressPercent(task.progress, task.total, task.done);
    }, 0);
    setCreateInstanceProgress(totalPercent, trackedTasks.length * 100);
}

function addCurrentCreateInstanceTask() {
    const payload = getCreateInstancePayload();
    const validationError = validateCreateInstancePayload(payload);
    if (validationError) {
        setCreateInstanceStatus(validationError);
        return false;
    }

    createInstanceTasks.push(makeCreateInstanceTask(payload));
    renderCreateInstanceTasks();
    createInstanceName.value = "";
    createInstanceName.focus();
    setCreateInstanceStatus("Task added.");
    return true;
}

function setVersionOptions() {
    createClientVersion.innerHTML = "";
    const selectedType = createVersionType.value;
    const versions = minecraftVersions.filter(version => version.type === selectedType);

    if (!versions.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "No versions available";
        createClientVersion.append(option);
        return;
    }

    for (const version of versions) {
        const option = document.createElement("option");
        option.value = version.id;
        option.textContent = `${version.id} (${version.type})`;
        option.dataset.type = version.type;
        createClientVersion.append(option);
    }
}

function syncModLoaderFields() {
    const hasLoader = createModLoader.value !== "none";
    createModLoaderVersionLabel.hidden = !hasLoader;
    createModLoaderVersion.disabled = !hasLoader;

    if (hasLoader) {
        createSkipGameFiles.checked = false;
    }
}

function loadMinecraftVersions() {
    if (!window.pywebview?.api?.get_minecraft_versions) {
        setCreateInstanceStatus("Minecraft version API is not ready.");
        minecraftVersions = [];
        setVersionOptions();
        return;
    }

    if (minecraftVersionsPromise) {
        return minecraftVersionsPromise;
    }

    minecraftVersionsPromise = window.pywebview.api.get_minecraft_versions()
        .then(result => {
            if (!result?.ok) {
                setCreateInstanceStatus(result?.error || "Failed to load Minecraft versions.");
                minecraftVersions = [];
                setVersionOptions();
                return;
            }

            minecraftVersions = Array.isArray(result.versions) ? result.versions : [];
            setVersionOptions();
            setCreateInstanceStatus(minecraftVersions.length ? "Ready." : "No Minecraft versions found.");
        })
        .catch(error => {
            setCreateInstanceStatus("Failed to load Minecraft versions.");
            minecraftVersions = [];
            setVersionOptions();
            console.error("Failed to load Minecraft versions.", error);
        })
        .finally(() => {
            minecraftVersionsPromise = null;
        });

    return minecraftVersionsPromise;
}

function createSingleInstance() {
    if (!window.pywebview?.api?.create_instance) {
        setCreateInstanceStatus("Create instance API is not ready.");
        return;
    }

    const payload = getCreateInstancePayload();
    const validationError = validateCreateInstancePayload(payload);
    if (validationError) {
        setCreateInstanceStatus(validationError);
        return;
    }

    createInstanceSubmit.disabled = true;
    createInstanceAddTask.disabled = true;
    setCreateInstanceStatus("Creating instance...");
    setCreateInstanceProgress(0, 0);

    window.pywebview.api.create_instance(payload)
        .then(result => {
            if (!result?.ok) {
                setCreateInstanceStatus(result?.error || "Failed to create instance.");
                return;
            }

            if (result.jobId) {
                setCreateInstanceStatus("Download started.");
                watchSingleCreateInstanceJob(result.jobId);
                return;
            }

            createInstanceForm.reset();
            setVersionOptions();
            syncModLoaderFields();
            setCreateInstanceProgress(1, 1);
            setCreateInstanceStatus("Instance created.");
        })
        .catch(error => {
            setCreateInstanceStatus("Failed to create instance.");
            console.error("Failed to create instance.", error);
        })
        .finally(() => {
            if (!createInstanceSingleJobTimer) {
                createInstanceSubmit.disabled = false;
                createInstanceAddTask.disabled = false;
            }
        });
}

function watchSingleCreateInstanceJob(jobId) {
    window.clearInterval(createInstanceSingleJobTimer);
    createInstanceSingleJobTimer = null;

    createInstanceSingleJobTimer = window.setInterval(() => {
        if (!window.pywebview?.api?.get_instance_job) {
            return;
        }

        window.pywebview.api.get_instance_job(jobId)
            .then(job => {
                if (!job?.ok) {
                    setCreateInstanceStatus(job?.error || "Download job not found.");
                    window.clearInterval(createInstanceSingleJobTimer);
                    createInstanceSingleJobTimer = null;
                    createInstanceSubmit.disabled = false;
                    createInstanceAddTask.disabled = false;
                    return;
                }

                const total = Number(job.total || 0);
                const progress = Number(job.progress || 0);
                const suffix = total ? ` (${progress}/${total})` : "";
                setCreateInstanceStatus(`${job.status || job.state}${suffix}`);
                setCreateInstanceProgress(progress, total);

                if (job.done) {
                    window.clearInterval(createInstanceSingleJobTimer);
                    createInstanceSingleJobTimer = null;
                    createInstanceSubmit.disabled = false;
                    createInstanceAddTask.disabled = false;

                    if (job.state === "failed") {
                        setCreateInstanceStatus(job.error || "Create failed.");
                    } else {
                        createInstanceForm.reset();
                        setVersionOptions();
                        syncModLoaderFields();
                        setCreateInstanceProgress(1, 1);
                        setCreateInstanceStatus("Instance created.");
                    }
                }
            })
            .catch(error => {
                setCreateInstanceStatus("Failed to read download job.");
                console.error("Failed to read instance job.", error);
            });
    }, 900);
}

function startCreateInstanceBatch() {
    if (!window.pywebview?.api?.create_instance) {
        setCreateInstanceStatus("Create instance API is not ready.");
        return;
    }

    if (!createInstanceTasks.some(task => !task.done) && !addCurrentCreateInstanceTask()) {
        return;
    }

    const pendingTasks = createInstanceTasks.filter(task => !task.done);
    if (!pendingTasks.length) {
        setCreateInstanceStatus("No pending instances.");
        return;
    }

    setCreateInstanceFormLocked(true);
    createInstanceActiveTaskIds = new Set(pendingTasks.map(task => task.id));
    setCreateInstanceStatus("Creating instances...");
    setCreateInstanceProgress(0, pendingTasks.length * 100);

    Promise.all(pendingTasks.map(task => {
        task.state = "starting";
        task.status = "Starting...";
        return window.pywebview.api.create_instance(task.payload)
            .then(result => {
                if (!result?.ok) {
                    task.state = "failed";
                    task.status = result?.error || "Failed to create instance.";
                    task.error = task.status;
                    task.done = true;
                    task.progress = 1;
                    task.total = 1;
                    return;
                }

                if (result.jobId) {
                    task.jobId = result.jobId;
                    task.state = "queued";
                    task.status = "Download started.";
                    return;
                }

                task.state = "finished";
                task.status = "Instance created.";
                task.done = true;
                task.progress = 1;
                task.total = 1;
            })
            .catch(error => {
                task.state = "failed";
                task.status = "Failed to create instance.";
                task.error = String(error?.message || error || task.status);
                task.done = true;
                task.progress = 1;
                task.total = 1;
                console.error("Failed to create instance.", error);
            });
    })).then(() => {
        renderCreateInstanceTasks();
        watchCreateInstanceBatch();
    });
}

createInstanceForm.addEventListener("submit", event => {
    event.preventDefault();
    if (createInstanceTasks.some(task => !task.done)) {
        startCreateInstanceBatch();
    } else {
        createSingleInstance();
    }
});

function watchCreateInstanceBatch() {
    window.clearInterval(createInstanceBatchTimer);
    createInstanceBatchTimer = null;

    createInstanceBatchTimer = window.setInterval(() => {
        if (!window.pywebview?.api?.get_instance_job) {
            return;
        }

        const activeTasks = createInstanceTasks.filter(task => createInstanceActiveTaskIds.has(task.id) && task.jobId && !task.done);
        if (!activeTasks.length) {
            finishCreateInstanceBatch();
            return;
        }

        Promise.all(activeTasks.map(task => {
            return window.pywebview.api.get_instance_job(task.jobId)
                .then(job => {
                    if (!job?.ok) {
                        task.state = "failed";
                        task.status = job?.error || "Download job not found.";
                        task.error = task.status;
                        task.done = true;
                        task.progress = 1;
                        task.total = 1;
                        return;
                    }

                    task.state = job.state || task.state;
                    task.status = job.status || job.state || task.status;
                    task.progress = Number(job.progress || 0);
                    task.total = Number(job.total || 0);
                    task.done = Boolean(job.done);

                    if (task.done && task.state === "failed") {
                        task.error = job.error || task.status || "Create failed.";
                    } else if (task.done) {
                        task.state = "finished";
                        task.status = "Instance created.";
                        task.progress = 1;
                        task.total = 1;
                    }
                })
                .catch(error => {
                    task.state = "failed";
                    task.status = "Failed to read download job.";
                    task.error = String(error?.message || error || task.status);
                    task.done = true;
                    task.progress = 1;
                    task.total = 1;
                    console.error("Failed to read instance job.", error);
                });
        })).then(() => {
            renderCreateInstanceTasks();
            const batchTasks = createInstanceTasks.filter(task => createInstanceActiveTaskIds.has(task.id));
            const finishedCount = batchTasks.filter(task => task.done).length;
            setCreateInstanceStatus(`Creating instances... ${finishedCount}/${batchTasks.length}`);
            if (finishedCount === batchTasks.length) {
                finishCreateInstanceBatch();
            }
        });
    }, 900);
}

function finishCreateInstanceBatch() {
    window.clearInterval(createInstanceBatchTimer);
    createInstanceBatchTimer = null;
    setCreateInstanceFormLocked(false);
    renderCreateInstanceTasks();

    const batchTasks = createInstanceTasks.filter(task => createInstanceActiveTaskIds.has(task.id));
    const failures = batchTasks.filter(task => task.state === "failed");
    createInstanceActiveTaskIds = new Set();
    if (failures.length) {
        setCreateInstanceStatus(`${failures.length} task failed.`);
        const details = failures.map(task => `${task.payload.name}: ${task.error || task.status || "Create failed."}`).join("\n\n");
        showBakeErrorOverlay(`Some instances failed to create.\n\n${details}`);
        return;
    }

    createInstanceForm.reset();
    setVersionOptions();
    syncModLoaderFields();
    setCreateInstanceStatus("All instances created.");
    setCreateInstanceProgress(1, 1);
    createInstanceTasks = [];
    renderCreateInstanceTasks();
}

createInstanceAddTask.addEventListener("click", () => {
    if (!createInstanceBatchRunning) {
        addCurrentCreateInstanceTask();
    }
});

createVersionType.addEventListener("change", setVersionOptions);
createModLoader.addEventListener("change", syncModLoaderFields);
createSkipGameFiles.addEventListener("change", () => {
    if (createSkipGameFiles.checked && createModLoader.value !== "none") {
        createModLoader.value = "none";
        syncModLoaderFields();
    }
});
setCreateInstanceProgress(0, 0);
syncModLoaderFields();
renderCreateInstanceTasks();
window.addEventListener("pywebviewready", () => {
    loadChildBackgroundSettings();
    loadMinecraftVersions();
});
