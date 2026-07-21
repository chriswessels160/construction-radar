let allProjects = [];

async function loadProjects() {

    try {

        const response = await fetch("projects.json");

        if (!response.ok) {
            throw new Error("Could not load projects.json");
        }

        allProjects = await response.json();

        populateFilters();
        updateSummary(allProjects);
        renderProjects(allProjects);

    } catch (error) {

        console.error(error);

        document.getElementById("emptyMessage").style.display = "block";

        document.getElementById("emptyMessage").innerText =
            "Unable to load project data.";

    }
}


function populateFilters() {

    const markets = [
        ...new Set(
            allProjects
                .map(project => project.market)
                .filter(Boolean)
        )
    ].sort();

    const counties = [
        ...new Set(
            allProjects
                .map(project => project.county)
                .filter(Boolean)
        )
    ].sort();

    const statuses = [
        ...new Set(
            allProjects
                .map(project => project.status)
                .filter(Boolean)
        )
    ].sort();

    addOptions("marketFilter", markets);
    addOptions("countyFilter", counties);
    addOptions("statusFilter", statuses);
}


function addOptions(selectId, values) {

    const select = document.getElementById(selectId);

    values.forEach(value => {

        const option = document.createElement("option");

        option.value = value;
        option.textContent = value;

        select.appendChild(option);

    });
}


function updateSummary(projects) {

    document.getElementById("totalProjects").innerText =
        projects.length;

    document.getElementById("industrialProjects").innerText =
        projects.filter(
            project => project.market === "Industrial"
        ).length;

    document.getElementById("commercialProjects").innerText =
        projects.filter(
            project => project.market === "Commercial"
        ).length;

    document.getElementById("highOpportunityProjects").innerText =
        projects.filter(
            project =>
                Number(project.opportunity_score || 0) >= 8
        ).length;
}


function renderProjects(projects) {

    const tableBody =
        document.getElementById("projectsTableBody");

    const emptyMessage =
        document.getElementById("emptyMessage");

    tableBody.innerHTML = "";

    if (projects.length === 0) {

        emptyMessage.style.display = "block";

        return;

    }

    emptyMessage.style.display = "none";

    projects.forEach(project => {

        const row = document.createElement("tr");

        row.innerHTML = `
            <td>
                ${escapeHtml(project.project || "Unknown")}
            </td>

            <td>
                ${escapeHtml(project.market || "Other")}
            </td>

            <td>
                ${escapeHtml(project.county || "Unknown")}
            </td>

            <td>
                ${escapeHtml(project.status || "Unknown")}
            </td>

            <td>
                ${escapeHtml(project.value || "Unknown")}
            </td>

            <td>
                ${escapeHtml(project.contractor || "Unknown")}
            </td>
            
            <td class="${Number(project.opportunity_score || 0) >= 8 ? "score-high" : ""}">
                ${escapeHtml(project.opportunity || "Unknown")}
            </td>
        `;

        tableBody.appendChild(row);

    });
}


function applyFilters() {

    const search =
        document
            .getElementById("searchInput")
            .value
            .toLowerCase();

    const market =
        document.getElementById("marketFilter").value;

    const county =
        document.getElementById("countyFilter").value;

    const status =
        document.getElementById("statusFilter").value;

    const filtered = allProjects.filter(project => {

        const searchableText = `
            ${project.project || ""}
            ${project.address || ""}
            ${project.city || ""}
            ${project.description || ""}
            ${project.contractor || ""}
        `.toLowerCase();

        const matchesSearch =
            searchableText.includes(search);

        const matchesMarket =
            !market || project.market === market;

        const matchesCounty =
            !county || project.county === county;

        const matchesStatus =
            !status || project.status === status;

        return (
            matchesSearch &&
            matchesMarket &&
            matchesCounty &&
            matchesStatus
        );

    });

    updateSummary(filtered);
    renderProjects(filtered);
}


function escapeHtml(value) {

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


document
    .getElementById("searchInput")
    .addEventListener(
        "input",
        applyFilters
    );


document
    .getElementById("marketFilter")
    .addEventListener(
        "change",
        applyFilters
    );


document
    .getElementById("countyFilter")
    .addEventListener(
        "change",
        applyFilters
    );


document
    .getElementById("statusFilter")
    .addEventListener(
        "change",
        applyFilters
    );


loadProjects();
