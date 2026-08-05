let allBids = [];

function escapeBidHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;").replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function uniqueValues(field) {
    return [...new Set(allBids.map(bid => bid[field]).filter(Boolean))]
        .sort((a, b) => a.localeCompare(b));
}

function fillSelect(id, values) {
    const select = document.getElementById(id);
    const defaults = [...select.options].map(option => option.outerHTML).join("");
    const defaultLabels = new Set([...select.options].map(option => option.textContent));
    select.innerHTML = defaults + values.filter(value => !defaultLabels.has(value)).map(value =>
        `<option value="${escapeBidHtml(value)}">${escapeBidHtml(value)}</option>`
    ).join("");
}

function deadlineTime(bid) {
    const value = Date.parse(bid.due_at || "");
    return Number.isFinite(value) ? value : 0;
}

function daysUntil(bid) {
    return Math.max(0, Math.ceil((deadlineTime(bid) - Date.now()) / 86400000));
}

function filteredBids() {
    const search = document.getElementById("bidSearch").value.trim().toLowerCase();
    const status = document.getElementById("statusFilter").value;
    const match = document.getElementById("matchFilter").value;
    const department = document.getElementById("departmentFilter").value;
    const type = document.getElementById("typeFilter").value;
    const inclusion = document.getElementById("inclusionFilter").value;
    const sort = document.getElementById("sortFilter").value;

    const results = allBids.filter(bid => {
        const text = [bid.bid_number, bid.project_name, bid.department, bid.buyer,
            bid.procurement_type, bid.inclusion, bid.awarded_contractor]
            .join(" ").toLowerCase();
        return (!search || text.includes(search))
            && (!status || (status === "__open__" ? bid.is_open : bid.status === status))
            && (!match || bid.match_type === match)
            && (!department || bid.department === department)
            && (!type || bid.procurement_type === type)
            && (!inclusion || (inclusion === "published"
                ? bid.inclusion !== "None published"
                : bid.inclusion === "None published"));
    });

    results.sort((a, b) => {
        if (sort === "oldest") return deadlineTime(a) - deadlineTime(b);
        if (sort === "name") return a.project_name.localeCompare(b.project_name);
        if (sort === "status") return a.status.localeCompare(b.status);
        return deadlineTime(b) - deadlineTime(a);
    });
    return results;
}

function renderBids() {
    const results = filteredBids();
    document.getElementById("resultCount").textContent = results.length.toLocaleString();
    document.getElementById("emptyMessage").hidden = results.length > 0;
    document.getElementById("bidsTableBody").innerHTML = results.map(bid => {
        const deadlineNote = bid.is_open
            ? `${daysUntil(bid)} day${daysUntil(bid) === 1 ? "" : "s"} left`
            : bid.status;
        return `<tr>
            <td><span class="match-pill">${escapeBidHtml(bid.match_type)}</span></td>
            <td><strong>${escapeBidHtml(bid.project_name)}</strong><span class="secondary">${escapeBidHtml(bid.bid_number)}</span></td>
            <td><span class="status-pill ${bid.is_open ? "open" : ""}">${escapeBidHtml(bid.status)}</span></td>
            <td>${escapeBidHtml(bid.department)}</td>
            <td>${escapeBidHtml(bid.procurement_type)}</td>
            <td>${escapeBidHtml(bid.inclusion)}</td>
            <td><strong>${escapeBidHtml(bid.due_display)}</strong><span class="secondary">${escapeBidHtml(deadlineNote)}</span></td>
            <td>${escapeBidHtml(bid.buyer)}</td>
            <td>${escapeBidHtml(bid.awarded_contractor)}</td>
            <td><a class="source-link" href="${escapeBidHtml(bid.source_url)}" target="_blank" rel="noopener">Official record</a></td>
        </tr>`;
    }).join("");
}

function updateSummary() {
    const open = allBids.filter(bid => bid.is_open);
    document.getElementById("totalCount").textContent = allBids.length.toLocaleString();
    document.getElementById("openCount").textContent = open.length.toLocaleString();
    document.getElementById("closingCount").textContent = open.filter(bid => daysUntil(bid) <= 7).length.toLocaleString();
    document.getElementById("electricalCount").textContent = open.filter(bid => bid.match_type === "Electrical match").length.toLocaleString();
}

async function loadBidIntelligence() {
    const response = await fetch(`bids.json?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`Bid data returned ${response.status}`);
    const payload = await response.json();
    allBids = Array.isArray(payload.bids) ? payload.bids : [];
    fillSelect("statusFilter", uniqueValues("status"));
    fillSelect("departmentFilter", uniqueValues("department"));
    fillSelect("typeFilter", uniqueValues("procurement_type"));
    document.getElementById("sourceStatus").textContent =
        `City of Cincinnati procurement data · updated ${new Date(payload.generated_at).toLocaleString()}`;
    updateSummary();
    renderBids();
}

document.querySelectorAll("#bidFilters input, #bidFilters select").forEach(control => {
    control.addEventListener(control.tagName === "INPUT" ? "input" : "change", renderBids);
});

loadBidIntelligence().catch(error => {
    document.getElementById("sourceStatus").textContent = "Bid data is temporarily unavailable.";
    document.getElementById("emptyMessage").hidden = false;
    console.error("Bid intelligence load failed", error);
});
