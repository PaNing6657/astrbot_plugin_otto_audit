const TYPE_LABELS = {
    video: "视频",
    blog: "动态",
    avatar: "头像",
    cover: "封面",
};

let allData = null;
let currentFilter = "";

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

function render(data) {
    allData = data;
    const tbody = $("log-body");
    const empty = $("log-empty");
    const summary = $("log-summary");

    const filtered = data && data.history ? (
        currentFilter ? data.history.filter(i => i.type === currentFilter) : data.history
    ) : [];

    if (!filtered.length) {
        tbody.innerHTML = "";
        empty.style.display = "block";
        summary.textContent = currentFilter
            ? `暂无${TYPE_LABELS[currentFilter] || currentFilter}审核记录`
            : "暂无审核记录";
        return;
    }

    empty.style.display = "none";

    const pass = filtered.filter(i => i.result.includes("✅")).length;
    const warn = filtered.filter(i => i.result.includes("⚠️")).length;
    const skip = filtered.filter(i => i.result.includes("⏭️")).length;
    const total = data.history.length;
    summary.textContent = `共 ${total} 条 | 当前 ${filtered.length} 条 | ✅ 通过 ${pass} | ⚠️ 违规 ${warn} | ⏭️ 跳过 ${skip}`;

    tbody.innerHTML = filtered.map(item => `
        <tr class="${resultClass(item.result)}">
            <td class="col-time">${timeStr(item.time)}</td>
            <td class="col-type">${typeLabel(item.type)}</td>
            <td class="col-id">${item.id}</td>
            <td class="col-result">${item.result}</td>
        </tr>
    `).join("");
}

function setFilter(type) {
    currentFilter = type;
    document.querySelectorAll(".filter-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.type === type);
    });
    if (allData) render(allData);
}

async function loadHistory() {
    const data = window.__OTTO_AUDIT_HISTORY__;
    if (data) {
        render(data);
    } else {
        console.warn("[OTTOhub] 历史数据未加载");
    }
}

async function refreshHistory() {
    return new Promise((resolve) => {
        const old = document.querySelector('script[src*="history_data.js"]');
        if (old) old.remove();
        delete window.__OTTO_AUDIT_HISTORY__;
        const script = document.createElement("script");
        script.src = `./history_data.js?_t=${Date.now()}`;
        script.onload = () => {
            render(window.__OTTO_AUDIT_HISTORY__);
            resolve();
        };
        script.onerror = () => {
            console.warn("[OTTOhub] 刷新历史数据失败");
            resolve();
        };
        document.body.appendChild(script);
    });
}

document.addEventListener("DOMContentLoaded", () => {
    $("btn-refresh").addEventListener("click", refreshHistory);
    document.querySelectorAll(".filter-btn").forEach(btn => {
        btn.addEventListener("click", () => setFilter(btn.dataset.type));
    });
    loadHistory();
});
}

document.addEventListener("DOMContentLoaded", () => {
    $("btn-refresh").addEventListener("click", refreshHistory);
    loadHistory();
});

