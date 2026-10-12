/**
 * Predictive Idle-Compute Scheduler - Client Dashboard Controller
 * Handles WebSocket telemetry stream, real-time UI rendering, and preemption controls.
 */

let ws = null;
let currentActiveJobId = null;
let isTerminalScrolledToBottom = true;

// Initialize WebSocket connection on load
document.addEventListener("DOMContentLoaded", () => {
    initWebSocket();
    setupDragAndDrop();

    // Auto-scroll watcher for terminal
    const term = document.getElementById("terminal-output");
    term.addEventListener("scroll", () => {
        isTerminalScrolledToBottom = term.scrollHeight - term.scrollTop <= term.clientHeight + 40;
    });
});

function initWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log("[WebSocket] Connected to grid telemetry stream.");
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            renderClusterNodes(data.nodes || []);
            renderJobsTable(data.jobs || []);
            updateSummaryStats(data.nodes || [], data.jobs || []);
            updateTerminalLogs(data.logs || {}, data.jobs || []);
        } catch (err) {
            console.error("Error processing telemetry message:", err);
        }
    };

    ws.onclose = () => {
        console.warn("[WebSocket] Disconnected. Retrying in 2 seconds...");
        setTimeout(initWebSocket, 2000);
    };

    ws.onerror = (err) => {
        console.error("[WebSocket Error]", err);
    };
}

function updateSummaryStats(nodes, jobs) {
    document.getElementById("stat-active-nodes").textContent = `${nodes.length} Laptops`;
    document.getElementById("stat-total-jobs").textContent = jobs.length;

    const idleCount = nodes.filter(n => n.status === "IDLE_SAFE" || n.status === "IDLE_RISKY").length;
    const capacity = nodes.length > 0 ? Math.round((idleCount / nodes.length) * 100) : 0;
    document.getElementById("stat-idle-capacity").textContent = `${capacity}%`;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

// Card class, badge class and label for every NodeStatus in the contract.
const NODE_STATUS_VIEW = {
    IDLE_SAFE:     { card: "idle-safe",     badge: "badge-idle-safe",     text: "🟢 IDLE (SAFE)" },
    IDLE_RISKY:    { card: "idle-risky",    badge: "badge-idle-risky",    text: "🟡 IDLE (RISKY)" },
    HOST_ACTIVE:   { card: "host-active",   badge: "badge-host-active",   text: "🔴 HOST ACTIVE" },
    HOST_BUSY:     { card: "host-busy",     badge: "badge-host-busy",     text: "🟠 HOST BUSY" },
    RUNNING_JOB:   { card: "busy",          badge: "badge-busy",          text: "⚡ RUNNING JOB" },
    DRAINING:      { card: "busy",          badge: "badge-busy",          text: "⏳ DRAINING" },
    UNSCHEDULABLE: { card: "offline",       badge: "badge-offline",       text: "⛔ UNSCHEDULABLE" },
    OFFLINE:       { card: "offline",       badge: "badge-offline",       text: "⚫ OFFLINE" },
};

function oracleHintFor(node) {
    switch (node.status) {
        case "IDLE_SAFE":
            return `🎯 <strong>Safe Bet:</strong> ${Math.round((node.predicted_idle_window_seconds || 0) / 60)} min safe window`;
        case "IDLE_RISKY":
            return `🤔 <strong>Idle, not yet trusted:</strong> waiting for the oracle`;
        case "HOST_ACTIVE":
            return node.source === "agent"
                ? `⌨️ <strong>Owner is using this laptop</strong>`
                : `⚠️ <strong>Host Typing:</strong> Preempted (0m window)`;
        case "HOST_BUSY":
            return `🔥 <strong>Owner's own work is using the CPU</strong>`;
        case "RUNNING_JOB":
            return `⚙️ Running: <code>${escapeHtml(node.current_job_id || "Job")}</code>`;
        case "OFFLINE":
            return `📴 <strong>No heartbeat</strong> in the last 15 s`;
        default:
            return `ℹ️ ${escapeHtml(node.status)}`;
    }
}

function renderClusterNodes(nodes) {
    const container = document.getElementById("nodes-container");
    if (!container) return;

    container.innerHTML = nodes.map(node => {
        const view = NODE_STATUS_VIEW[node.status] || NODE_STATUS_VIEW.UNSCHEDULABLE;
        const isAgent = node.source === "agent";
        const isActive = node.status === "HOST_ACTIVE";
        const cpu = Number(node.cpu_percent) || 0;
        const ramPct = Number(node.ram_percent) || 0;
        const ramUsed = Number(node.ram_used_mb) || 0;
        const ramTotal = Number(node.ram_total_mb) || 0;
        const subtitle = [node.ip_address, node.os_name].filter(Boolean).map(escapeHtml).join(" · ");

        // Real laptops report their own state, so they get a label instead of the simulate button.
        const footer = isAgent
            ? `<div class="node-live-label">📡 Live laptop (real agent)</div>`
            : `<button class="btn-toggle-host" onclick="toggleHostActivity('${escapeHtml(node.node_id)}')">
                    ${isActive ? "💤 Host Went Idle" : "🖱️ Simulate Host Moved Mouse"}
               </button>`;

        return `
            <div class="node-card ${view.card}">
                <div class="node-top">
                    <div>
                        <div class="node-name">${escapeHtml(node.hostname)}</div>
                        <div class="node-ip">${subtitle}</div>
                    </div>
                    <span class="node-status-badge ${view.badge}">${view.text}</span>
                </div>

                <!-- CPU Metric -->
                <div class="metric-row">
                    <div class="metric-header">
                        <span>CPU Utilization</span>
                        <strong>${cpu.toFixed(1)}%</strong>
                    </div>
                    <div class="bar-bg">
                        <div class="bar-fill bar-cpu" style="width: ${Math.min(100, Math.max(5, cpu))}%"></div>
                    </div>
                </div>

                <!-- RAM Metric -->
                <div class="metric-row">
                    <div class="metric-header">
                        <span>Memory (RAM)</span>
                        <strong>${(ramUsed / 1024).toFixed(1)} / ${(ramTotal / 1024).toFixed(0)} GB</strong>
                    </div>
                    <div class="bar-bg">
                        <div class="bar-fill bar-ram" style="width: ${Math.min(100, Math.max(5, ramPct))}%"></div>
                    </div>
                </div>

                <!-- ML Oracle Prediction -->
                <div class="oracle-pill">
                    <span class="oracle-icon">🔮</span>
                    <span class="oracle-text">${oracleHintFor(node)}</span>
                </div>

                ${footer}
            </div>
        `;
    }).join("");
}

function renderJobsTable(jobs) {
    const tbody = document.getElementById("jobs-table-body");
    if (!tbody) return;

    if (!jobs || jobs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-row">No compute jobs submitted yet. Click a demo button above to launch!</td></tr>`;
        return;
    }

    tbody.innerHTML = jobs.slice().reverse().map(job => {
        const st = job.status || "QUEUED";
        let pillClass = "status-queued";
        if (st === "RUNNING") pillClass = "status-running";
        else if (st === "PAUSED") pillClass = "status-paused";
        else if (st === "COMPLETED") pillClass = "status-completed";
        else if (st === "FAILED") pillClass = "status-failed";

        const assignedText = job.assigned_hostname || job.assigned_node_id || "Routing...";
        const durationText = job.duration_seconds > 0 ? `${job.duration_seconds.toFixed(2)}s` : "-";
        const pausesText = job.pause_count > 0 ? `${job.pause_count} (${job.total_pause_duration_sec.toFixed(1)}s)` : "0";
        const ramText = job.peak_ram_mb > 0 ? `${job.peak_ram_mb.toFixed(0)} MB` : "-";

        let actionHtml = `
            <button class="btn-action-sm" onclick="selectActiveJob('${job.job_id}')" title="View Logs">👁️ Logs</button>
        `;

        if (st === "COMPLETED") {
            actionHtml += ` <a class="btn-action-sm" href="/api/jobs/${job.job_id}/download" download title="Download results.zip">📥 Results</a>`;
        } else if (st === "RUNNING") {
            actionHtml += ` <button class="btn-action-sm" onclick="pauseJob('${job.job_id}')">⏸ Pause</button>`;
        } else if (st === "PAUSED") {
            actionHtml += ` <button class="btn-action-sm" onclick="resumeJob('${job.job_id}')">▶ Resume</button>`;
        }

        return `
            <tr>
                <td>
                    <strong>${job.job_name}</strong><br>
                    <small style="color:var(--text-muted);font-family:var(--font-mono)">${job.job_id}</small>
                </td>
                <td style="color:var(--text-secondary)">${assignedText}</td>
                <td><span class="job-pill ${pillClass}">${st}</span></td>
                <td>${durationText}</td>
                <td>${pausesText}</td>
                <td>${ramText}</td>
                <td>${actionHtml}</td>
            </tr>
        `;
    }).join("");
}

function updateTerminalLogs(logsMap, jobs) {
    const term = document.getElementById("terminal-output");
    const termTitle = document.getElementById("terminal-active-job");
    if (!term) return;

    // Pick active job or newest job if not set
    if (!currentActiveJobId && jobs.length > 0) {
        currentActiveJobId = jobs[jobs.length - 1].job_id;
    }

    if (currentActiveJobId && logsMap[currentActiveJobId]) {
        termTitle.textContent = `Sandbox Output: ${currentActiveJobId}`;
        term.textContent = logsMap[currentActiveJobId];
    }

    if (isTerminalScrolledToBottom) {
        term.scrollTop = term.scrollHeight;
    }
}

function selectActiveJob(jobId) {
    currentActiveJobId = jobId;
    fetch(`/api/jobs/${jobId}/logs`)
        .then(r => r.json())
        .then(data => {
            const term = document.getElementById("terminal-output");
            const termTitle = document.getElementById("terminal-active-job");
            termTitle.textContent = `Sandbox Output: ${jobId}`;
            term.textContent = data.logs || "(No logs captured yet)";
            term.scrollTop = term.scrollHeight;
        });
}

function toggleHostActivity(nodeId) {
    fetch(`/api/cluster/nodes/${nodeId}/toggle-host-activity`, { method: "POST" })
        .then(r => r.json())
        .catch(err => console.error("Error toggling host activity:", err));
}

function submitDemoJob(type) {
    const formData = new FormData();
    formData.append("job_type", type);

    fetch("/api/jobs/submit", {
        method: "POST",
        body: formData
    })
    .then(r => r.json())
    .then(data => {
        currentActiveJobId = data.job_id;
        console.log("Demo job submitted:", data);
    })
    .catch(err => alert("Submission failed: " + err));
}

function handleFileSelected(event) {
    const file = event.target.files[0];
    if (!file) return;

    uploadJobFile(file);
}

function setupDragAndDrop() {
    const dropZone = document.getElementById("drop-zone");
    if (!dropZone) return;

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.style.borderColor = 'var(--primary)', false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.style.borderColor = 'rgba(255, 255, 255, 0.12)', false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const file = dt.files[0];
        if (file) {
            uploadJobFile(file);
        }
    });
}

function uploadJobFile(file) {
    const formData = new FormData();
    formData.append("bundle", file);

    fetch("/api/jobs/submit", {
        method: "POST",
        body: formData
    })
    .then(r => r.json())
    .then(data => {
        currentActiveJobId = data.job_id;
        alert(`✓ Job '${data.job_name}' packaged and dispatched successfully!`);
    })
    .catch(err => alert("File upload error: " + err));
}

function pauseJob(jobId) {
    fetch(`/api/jobs/${jobId}/pause`, { method: "POST" });
}

function resumeJob(jobId) {
    fetch(`/api/jobs/${jobId}/resume`, { method: "POST" });
}

function clearConsole() {
    const term = document.getElementById("terminal-output");
    if (term) term.textContent = "[CONSOLE CLEARED]";
}
