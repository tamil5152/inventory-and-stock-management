/* Notification bell, stock-check counter and desktop alerts. Polls every 30 s. */

(() => {

    const POLL_MS = 30000;
    const bell = document.getElementById("bell");
    const panel = document.getElementById("notif-panel");
    const list = document.getElementById("notif-list");
    const countBadge = document.getElementById("bell-count");
    const navCount = document.getElementById("nav-check-count");
    const desktopBtn = document.getElementById("desktop-alerts-btn");
    const e = StockFlow.escapeHtml;

    const storageKey = `sf-last-notif-${window.CURRENT_USER.id}`;
    let lastSeenId = 0;
    let items = [];

    try { lastSeenId = Number(localStorage.getItem(storageKey) || 0); } catch (_) { /* storage blocked */ }

    const ICONS = {
        CHECK_ASSIGNED: ["clipboard", "check"],
        CHECK_SUMMARY: ["clipboard", "check"],
        CHECK_OVERDUE: ["alert", "alert"],
        DISCREPANCY: ["alert", "alert"],
        UNKNOWN_BARCODE: ["scan", "alert"],
    };

    function timeAgo(value) {

        const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : value + "Z");
        const seconds = Math.max(0, (Date.now() - date) / 1000);

        if (seconds < 60) return "Just now";
        if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
        return StockFlow.formatDate(value);
    }

    function render() {

        if (!items.length) {
            list.innerHTML = '<p class="empty-state">You have no notifications.</p>';
            return;
        }

        list.innerHTML = items.map((n) => {
            const [icon, tone] = ICONS[n.category] || ["bell", "info"];
            return `
                <button class="notif-item ${n.is_read ? "" : "unread"}" data-id="${n.id}" data-link="${e(n.link || "")}">
                    <span class="notif-icon ${tone}"><svg class="icon"><use href="#i-${icon}"/></svg></span>
                    <span>
                        <div class="notif-title">${e(n.title)}</div>
                        ${n.message ? `<div class="notif-body">${e(n.message)}</div>` : ""}
                        <div class="notif-time">${timeAgo(n.created_at)}</div>
                    </span>
                </button>`;
        }).join("");
    }

    function setCount(el, value) {

        el.hidden = !value;
        el.textContent = value > 99 ? "99+" : value;
    }

    function showDesktop(newItems) {

        if (!("Notification" in window) || Notification.permission !== "granted") return;

        newItems.slice(0, 3).forEach((n) => {
            const note = new Notification(n.title, { body: n.message || "", tag: `sf-${n.id}` });
            note.onclick = () => { window.focus(); if (n.link) window.location.href = n.link; };
        });
    }

    async function poll() {

        try {
            const [notes, checks] = await Promise.all([
                StockFlow.api("/api/notifications/?limit=20"),
                StockFlow.api("/api/checks/summary"),
            ]);

            items = notes.data;
            setCount(countBadge, notes.unread);
            setCount(navCount, checks.data.mine || (StockFlow.hasRole("admin", "manager") ? checks.data.open : 0));

            const fresh = items.filter((n) => !n.is_read && n.id > lastSeenId);

            if (fresh.length && lastSeenId) {
                showDesktop(fresh);
                const first = fresh[0];
                StockFlow.toast(first.title, first.category.includes("OVERDUE") || first.category === "DISCREPANCY" ? "warning" : "success");
            }

            if (notes.latest_id > lastSeenId) {
                lastSeenId = notes.latest_id;
                try { localStorage.setItem(storageKey, String(lastSeenId)); } catch (_) { /* ignore */ }
            }

            if (!panel.hidden) render();
            document.dispatchEvent(new CustomEvent("sf:checks", { detail: checks.data }));

        } catch (_) { /* offline or logged out: try again next tick */ }
    }

    function updateDesktopButton() {

        desktopBtn.hidden = !("Notification" in window) || Notification.permission !== "default";
    }

    bell.addEventListener("click", (event) => {

        event.stopPropagation();
        panel.hidden = !panel.hidden;
        bell.setAttribute("aria-expanded", String(!panel.hidden));
        if (!panel.hidden) render();
    });

    document.addEventListener("click", (event) => {

        if (!panel.hidden && !panel.contains(event.target)) {
            panel.hidden = true;
            bell.setAttribute("aria-expanded", "false");
        }
    });

    list.addEventListener("click", async (event) => {

        const item = event.target.closest(".notif-item");
        if (!item) return;

        try { await StockFlow.api(`/api/notifications/${item.dataset.id}/read`, { method: "POST" }); } catch (_) { /* ignore */ }

        if (item.dataset.link) window.location.href = item.dataset.link;
        else poll();
    });

    document.getElementById("notif-read-all").addEventListener("click", async () => {

        await StockFlow.api("/api/notifications/read-all", { method: "POST" });
        poll();
    });

    desktopBtn.addEventListener("click", async () => {

        const result = await Notification.requestPermission();
        updateDesktopButton();
        StockFlow.toast(result === "granted" ? "Desktop alerts are on." : "Desktop alerts stay off.", result === "granted" ? "success" : "warning");
        document.dispatchEvent(new Event("sf:permission"));
    });

    // Mobile sidebar
    document.querySelectorAll("[data-toggle-nav]").forEach((el) =>
        el.addEventListener("click", () => document.body.classList.toggle("nav-open")));

    window.StockFlowAlerts = { refresh: poll, updateDesktopButton };

    updateDesktopButton();
    poll();
    setInterval(poll, POLL_MS);
})();
