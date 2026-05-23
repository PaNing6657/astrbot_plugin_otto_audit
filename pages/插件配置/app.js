const bridge = window.AstrBotPluginPage || {
    ready: async () => ({}),
    apiGet: async () => ({}),
    apiPost: async () => ({ success: true }),
};

function $(id) { return document.getElementById(id); }

const TYPE_LABELS = { video: "视频", blog: "动态", avatar: "头像", cover: "封面" };

function formatTime(ts) {
    if (!ts) return "-";
    const d = new Date(ts * 1000);
    return d.toLocaleString("zh-CN", { hour12: false });
}

function getResultClass(result) {
    if (result.includes("✅")) return "result-pass";
    if (result.includes("⚠️")) return "result-warn";
    if (result.includes("⏭️")) return "result-skip";
    if (result.includes("❌")) return "result-error";
    return "";
}

function truncate(s, n = 60) {
    return s && s.length > n ? s.slice(0, n) + "…" : s || "";
}

async function loadHistory() {
    const data = await bridge.apiGet("get_history");
    const records = data && typeof data === "object" ? data : {};
    const keys = Object.keys(records).sort((a, b) => (records[b].time || 0) - (records[a].time || 0));

    const tbody = $("history-body");
    const empty = $("empty-state");
    const countEl = $("record-count");

    tbody.innerHTML = "";
    countEl.textContent = keys.length;

    if (!keys.length) {
        empty.style.display = "block";
        return;
    }
    empty.style.display = "none";

    for (const key of keys) {
        const r = records[key];
        const tr = document.createElement("tr");
        const typeLabel = TYPE_LABELS[r.type] || r.type || "-";
        const resultClass = getResultClass(r.result || "");

        tr.innerHTML = `
            <td>${typeLabel}</td>
            <td>${r.id ?? "-"}</td>
            <td class="${resultClass}">${truncate(r.result || "", 80)}</td>
            <td>${formatTime(r.time)}</td>
            <td><button class="btn-sm" data-action="delete" data-key="${key}">删除</button></td>
        `;
        tbody.appendChild(tr);
    }

    tbody.querySelectorAll('[data-action="delete"]').forEach(btn => {
        btn.addEventListener("click", async () => {
            const key = btn.dataset.key;
            await bridge.apiPost("delete_history", { key });
            loadHistory();
            $("save-state").textContent = "✅ 已删除";
        });
    });
}

async function clearAll() {
    if (!confirm("确定清空全部审核记录？")) return;
    await bridge.apiPost("clear_history", {});
    await loadHistory();
    $("save-state").textContent = "✅ 已清空";
}

document.addEventListener("DOMContentLoaded", async () => {
    await bridge.ready();
    document.querySelector('[data-action="clear-all"]').addEventListener("click", clearAll);
    await loadHistory();
});
