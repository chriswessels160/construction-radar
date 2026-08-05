let allOpenBids = [];

function bidEscape(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function bidDaysRemaining(dueAt) {
    const milliseconds = new Date(dueAt).getTime() - Date.now();
    return Math.max(0, Math.ceil(milliseconds / 86400000));
}

function renderOpenBids() {
    const query = document.getElementById("bidSearch").value.trim().toLowerCase();
    const match = document.getElementById("bidMatchFilter").value;
    const visible = allOpenBids.filter(bid => {
        const searchable = [
            bid.bid_number, bid.project_name, bid.department, bid.buyer,
            bid.procurement_type, bid.inclusion, bid.match_type
        ].join(" ").toLowerCase();
        return (!query || searchable.includes(query)) && (!match || bid.match_type === match);
    });

    document.getElementById("openBidCount").textContent = allOpenBids.length.toLocaleString();
    document.getElementById("visibleBidCount").textContent = visible.length.toLocaleString();
    document.getElementById("bidEmptyMessage").style.display = visible.length ? "none" : "block";
    document.getElementById("bidsTableBody").innerHTML = visible.map(bid => {
        const days = bidDaysRemaining(bid.due_at);
        const urgency = days <= 3 ? "bid-deadline urgent" : "bid-deadline";
        return `
            <tr>
                <td><span class="bid-match">${bidEscape(bid.match_type)}</span></td>
                <td><strong>${bidEscape(bid.project_name)}</strong><div class="cell-secondary">${bidEscape(bid.bid_number)}</div></td>
                <td>${bidEscape(bid.department)}</td>
                <td>${bidEscape(bid.procurement_type)}</td>
                <td>${bidEscape(bid.inclusion)}</td>
                <td><span class="${urgency}">${bidEscape(bid.due_display)}</span><div class="cell-secondary">${days} day${days === 1 ? "" : "s"} left</div></td>
                <td>${bidEscape(bid.buyer)}</td>
                <td><a class="bid-link" href="${bidEscape(bid.source_url)}" target="_blank" rel="noopener">View bid</a></td>
            </tr>`;
    }).join("");
}

async function loadOpenBids() {
    const status = document.getElementById("bidLoadStatus");
    try {
        const response = await fetch(`bids.json?ts=${Date.now()}`, { cache: "no-store" });
        if (!response.ok) throw new Error(`Bid data returned ${response.status}`);
        const payload = await response.json();
        allOpenBids = Array.isArray(payload.bids) ? payload.bids : [];
        status.textContent = payload.generated_at
            ? `Official City of Cincinnati feed · updated ${new Date(payload.generated_at).toLocaleString()}`
            : "Official City of Cincinnati feed";
        renderOpenBids();
    } catch (error) {
        status.textContent = "Open bids are temporarily unavailable. Permit data is unaffected.";
        document.getElementById("bidEmptyMessage").textContent = "Could not load open bids. Try refreshing shortly.";
        document.getElementById("bidEmptyMessage").style.display = "block";
        console.error("Open bid load failed", error);
    }
}

document.getElementById("bidSearch").addEventListener("input", renderOpenBids);
document.getElementById("bidMatchFilter").addEventListener("change", renderOpenBids);
loadOpenBids();
