/* Dashboard charts (plain SVG, no chart library). */

(() => {

    const e = StockFlow.escapeHtml;
    const NS = "http://www.w3.org/2000/svg";

    function el(name, attrs, parent) {
        const node = document.createElementNS(NS, name);
        Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
        parent.appendChild(node);
        return node;
    }

    // Round the axis up so the four gridlines land on 1, 2, 2.5 or 5 multiples.
    function niceMax(value) {
        const raw = Math.max(value, 4) / 4;
        const magnitude = 10 ** Math.floor(Math.log10(raw));
        const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw);
        return step * 4;
    }

    function drawTrend(trend) {

        const svg = document.getElementById("trend-chart");
        const width = svg.clientWidth || 600;
        const height = 200;
        const pad = { top: 10, right: 6, bottom: 26, left: 34 };
        const plotW = width - pad.left - pad.right;
        const plotH = height - pad.top - pad.bottom;

        svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
        svg.innerHTML = "";

        const max = niceMax(Math.max(1, ...trend.map((d) => Math.max(d.in, d.out))));

        for (let i = 0; i <= 4; i++) {
            const y = pad.top + plotH - (plotH * i) / 4;
            el("line", { x1: pad.left, x2: width - pad.right, y1: y, y2: y, stroke: "#dde2df", "stroke-dasharray": i ? "3 4" : "" }, svg);
            el("text", { x: pad.left - 6, y: y + 4, "text-anchor": "end" }, svg).textContent = Math.round((max * i) / 4);
        }

        const slot = plotW / trend.length;
        const barW = Math.max(3, Math.min(14, slot / 2 - 3));

        trend.forEach((day, i) => {

            const x = pad.left + slot * i + slot / 2;
            const hIn = (day.in / max) * plotH;
            const hOut = (day.out / max) * plotH;

            const title = `${day.date}: ${day.in} in, ${day.out} out`;
            el("rect", { x: x - barW - 1, y: pad.top + plotH - hIn, width: barW, height: hIn, rx: 2, fill: "#0e7c6b" }, svg)
                .appendChild(document.createElementNS(NS, "title")).textContent = title;
            el("rect", { x: x + 1, y: pad.top + plotH - hOut, width: barW, height: hOut, rx: 2, fill: "#e8a317" }, svg)
                .appendChild(document.createElementNS(NS, "title")).textContent = title;

            if (i % 2 === 0 || trend.length <= 7) {
                const date = new Date(day.date + "T00:00:00");
                el("text", { x, y: height - 8, "text-anchor": "middle" }, svg).textContent =
                    date.toLocaleDateString(undefined, { day: "numeric", month: "short" });
            }
        });
    }

    function drawCategories(categories) {

        const box = document.getElementById("category-bars");

        if (!categories.length) {
            box.innerHTML = '<p class="muted">Add products to see stock value by category.</p>';
            return;
        }

        const max = Math.max(...categories.map((c) => c.value), 1);
        const sorted = [...categories].sort((a, b) => b.value - a.value);

        box.innerHTML = sorted.map((c) => `
            <div class="hbar-row" title="${e(c.category)}: ${c.units} units">
                <span>${e(c.category)}</span>
                <div class="hbar-track"><div class="hbar-fill" style="width:${Math.max(2, (c.value / max) * 100)}%"></div></div>
                <span class="val">${StockFlow.money(c.value).replace(".00", "")}</span>
            </div>`).join("");
    }

    let trendData = [];

    StockFlow.api("/api/charts").then((result) => {
        trendData = result.data.trend;
        drawTrend(trendData);
        drawCategories(result.data.categories);
    }).catch((error) => StockFlow.toast(error.message, "error"));

    window.addEventListener("resize", StockFlow.debounce(() => trendData.length && drawTrend(trendData), 150));
})();
