const TYPE_LABELS = {
    video: "视频",
    blog: "动态",
    avatar: "头像",
    cover: "封面",
};

const bridge = window.AstrBotPluginPage || {
    ready: async () => ({}),
    apiGet: async (name) => ({ success: true, history: [] }),
};

let allItems = [];

function $(id) { return document.getElementById(id); }

function timeStr(ts) {
    if (!ts) return "-";
    const d = new Date(ts * 1000);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function typeLabel(t) {
    return TYPE_LABELS[t] || t;
}

function resultClass(result) {
    if (result.includes("✅") || result.includes("通过")) return "row-pass";
    if (result.includes("⚠️") || result.includes("违规")) return "row-warn";
    if (result.includes("⏭️") || result.includes("跳过")) return "row-skip";
    return "";
}

function render() {
    const tbody = $("log-body");
    const empty = $("log-empty");
    const summary = $("log-summary");

    if (!allItems.length) {
        tbody.innerHTML = "";
        empty.style.display = "block";
        summary.textContent = "暂无审核记录";
        return;
    }

    empty.style.display = "none";

    const pass = allItems.filter(i => i.result.includes("✅")).length;
    const warn = allItems.filter(i => i.result.includes("⚠️")).length;
    const skip = allItems.filter(i => i.result.includes("⏭️")).length;
    summary.textContent = `共 ${allItems.length} 条 | ✅ 通过 ${pass} | ⚠️ 违规 ${warn} | ⏭️ 跳过 ${skip}`;

    tbody.innerHTML = allItems.map(item => `
        <tr class="${resultClass(item.result)}">
            <td class="col-time">${timeStr(item.time)}</td>
            <td class="col-type">${typeLabel(item.type)}</td>
            <td class="col-id">${item.id}</td>
            <td class="col-result">${item.result}</td>
        </tr>
    `).join("");
}

async function loadHistory() {
    try {
        const data = await bridge.apiGet("get_history");
        if (data && data.success && Array.isArray(data.history)) {
            allItems = data.history;
        }
    } catch (e) {
        console.warn("[OTTOhub] 加载日志失败", e);
    }
    render();
}

document.addEventListener("DOMContentLoaded", () => {
    $("btn-refresh").addEventListener("click", loadHistory);
    loadHistory();
});
