const mockConfig = {
    otto_base_url: "https://api.ottohub.cn",
    otto_uid_email: "",
    otto_password: "",
    llm_base_url: "",
    llm_api_key: "",
    llm_model: "gpt-4o",
    llm_timeout: 60,
    auto_execute: true,
};

const bridge = window.AstrBotPluginPage || {
    ready: async () => ({}),
    apiGet: async () => JSON.parse(JSON.stringify(mockConfig)),
    apiPost: async (name, payload) => {
        console.info(`[OTTO Audit preview] ${name}`, payload);
        return { success: true };
    }
};

let state = { ...mockConfig };

const fieldMap = {
    otto_base_url: "otto_base_url",
    otto_uid_email: "otto_uid_email",
    otto_password: "otto_password",
    llm_base_url: "llm_base_url",
    llm_api_key: "llm_api_key",
    llm_model: "llm_model",
    llm_timeout: "llm_timeout",
    auto_execute: "auto_execute",
};

function $(id) { return document.getElementById(id); }

function bindInput(id, key) {
    const el = $(id);
    if (!el) return;
    if (el.type === "checkbox") {
        el.addEventListener("change", () => { state[key] = el.checked; markDirty(); });
    } else if (el.type === "number") {
        el.addEventListener("input", () => { state[key] = parseInt(el.value) || 0; markDirty(); });
    } else {
        el.addEventListener("input", () => { state[key] = el.value; markDirty(); });
    }
}

function renderState() {
    for (const [id, key] of Object.entries(fieldMap)) {
        const el = $(id);
        if (!el) continue;
        if (el.type === "checkbox") el.checked = !!state[key];
        else if (el.type === "number") el.value = state[key];
        else el.value = state[key] || "";
    }
}

function markDirty() {
    $("save-state").textContent = "⚠️ 有未保存的更改";
}

async function loadConfig() {
    try {
        const data = await bridge.apiGet("get_config");
        if (data && typeof data === "object") {
            state = { ...mockConfig, ...data };
        }
    } catch (e) {
        console.warn("[OTTO Audit] 使用默认配置", e);
    }
    renderState();
}

async function saveConfig() {
    const btn = document.querySelector('[data-action="save-config"]');
    btn.textContent = "保存中...";
    btn.disabled = true;
    try {
        const resp = await bridge.apiPost("save_config", state);
        if (resp && resp.success) {
            $("save-state").textContent = "✅ 配置已保存";
        } else {
            $("save-state").textContent = "❌ 保存失败";
        }
    } catch (e) {
        $("save-state").textContent = "❌ 保存失败: " + (e.message || e);
    }
    btn.textContent = "保存更改";
    btn.disabled = false;
}

function activateTab(tabId) {
    document.querySelectorAll(".tab-pane").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));

    const pane = $(tabId);
    if (pane) pane.classList.add("active");
    const navBtn = document.querySelector(`.nav-item[data-target="${tabId}"]`);
    if (navBtn) navBtn.classList.add("active");

    const title = pane ? pane.dataset.title : "";
    $("active-title").textContent = title || "设置";
}

document.addEventListener("DOMContentLoaded", async () => {
    for (const [id, key] of Object.entries(fieldMap)) bindInput(id, key);

    document.querySelectorAll(".nav-item").forEach(btn => {
        btn.addEventListener("click", () => activateTab(btn.dataset.target));
    });

    document.querySelector('[data-action="save-config"]').addEventListener("click", saveConfig);

    await loadConfig();
});
