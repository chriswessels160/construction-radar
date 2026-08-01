let allProjects = [];
let mapMarkers = [];


/* =========================================================
   MAP SETUP
========================================================= */

const constructionMap = L.map(
    "constructionMap",
    {
        zoomControl: true
    }
).setView(
    [39.1031, -84.5120],
    11
);


const constructionTiles = L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    {
        attribution:
            "&copy; OpenStreetMap contributors &copy; CARTO",
        subdomains: "abcd",
        maxZoom: 20
    }
).addTo(constructionMap);


const projectMarkerLayer =
    typeof L.markerClusterGroup === "function"
        ? L.markerClusterGroup({
            showCoverageOnHover: false,
            maxClusterRadius: 58,
            spiderfyOnMaxZoom: true,
            iconCreateFunction(cluster) {
                const count = cluster.getChildCount();
                const size = count >= 100 ? 52 : count >= 20 ? 46 : 40;
                const sizeClass = count >= 100
                    ? "project-cluster-large"
                    : count >= 20
                        ? "project-cluster-medium"
                        : "project-cluster-small";

                return L.divIcon({
                    html: `<span>${count.toLocaleString()}</span>`,
                    className: `project-cluster ${sizeClass}`,
                    iconSize: L.point(size, size)
                });
            }
        })
        : L.layerGroup();


projectMarkerLayer.addTo(constructionMap);


/* =========================================================
   THEME
========================================================= */

function applyTheme(theme, persist = true) {

    const nextTheme = theme === "light" ? "light" : "dark";
    const lightMode = nextTheme === "light";

    document.documentElement.dataset.theme = nextTheme;
    document.getElementById("themeIcon").textContent = lightMode ? "☾" : "☀";
    document.getElementById("themeLabel").textContent = lightMode ? "Dark mode" : "Light mode";
    document.getElementById("themeToggle").setAttribute(
        "aria-label",
        lightMode ? "Switch to dark mode" : "Switch to light mode"
    );

    constructionTiles.setUrl(
        lightMode
            ? "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
            : "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
    );

    if (persist) {
        try {
            localStorage.setItem("construction-radar-theme", nextTheme);
        } catch (_error) {
            // Theme switching still works when browser storage is unavailable.
        }
    }
}


function initializeTheme() {

    applyTheme(
        document.documentElement.dataset.theme || "dark",
        false
    );
}


/* =========================================================
   LOAD PROJECT DATA
========================================================= */

async function loadProjects() {

    try {

        const response = await fetch(
            `projects.json?v=${Date.now()}`,
            { cache: "no-store" }
        );

        if (!response.ok) {
            throw new Error("Could not load projects.json");
        }

        allProjects = await response.json();

        populateFilters();
        applyFilters();
        setAssistantReady(true);

    } catch (error) {

        console.error(error);

        document.getElementById("emptyMessage").style.display =
            "block";

        document.getElementById("emptyMessage").innerText =
            "Unable to load project data.";

        setAssistantReady(false, true);

    }
}


/* =========================================================
   FILTER OPTIONS
========================================================= */

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
                .map(project => getProjectArea(project))
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


    addOptions(
        "marketFilter",
        markets
    );

    addOptions(
        "countyFilter",
        counties
    );

    addOptions(
        "statusFilter",
        statuses
    );
}


function addOptions(
    selectId,
    values
) {

    const select =
        document.getElementById(selectId);


    values.forEach(value => {

        const option =
            document.createElement("option");

        option.value = value;
        option.textContent = value;

        select.appendChild(option);

    });
}


/* =========================================================
   SUMMARY CARDS
========================================================= */

function updateSummary(projects) {

    document
        .getElementById("totalProjects")
        .innerText = projects.length;


    document
        .getElementById("industrialProjects")
        .innerText = projects.filter(
            project =>
                project.market === "Industrial"
        ).length;


    document
        .getElementById("commercialProjects")
        .innerText = projects.filter(
            project =>
                project.market === "Commercial"
        ).length;


    document
        .getElementById("highOpportunityProjects")
        .innerText = projects.filter(
            project =>
                Number(
                    project.opportunity_score || 0
                ) >= 8
        ).length;
}


/* =========================================================
   PROJECT TABLE
========================================================= */

function renderProjects(projects) {

    const tableBody =
        document.getElementById(
            "projectsTableBody"
        );

    const emptyMessage =
        document.getElementById(
            "emptyMessage"
        );


    tableBody.innerHTML = "";


    if (projects.length === 0) {

        emptyMessage.style.display =
            "block";

        return;

    }


    emptyMessage.style.display =
        "none";


    projects.forEach(project => {

        const row =
            document.createElement("tr");


        row.innerHTML = `
            <td>
                ${escapeHtml(
                    project.project || "Unknown"
                )}
            </td>

            <td>
                ${escapeHtml(
                    project.market || "Other"
                )}
            </td>

            <td>
                ${escapeHtml(
                    getProjectArea(project)
                )}
            </td>

            <td>
                ${escapeHtml(
                    project.status || "Unknown"
                )}
            </td>

            <td>
                ${escapeHtml(
                    project.value || "Unknown"
                )}
            </td>

            <td>
                <div class="project-contact">
                    <span>${escapeHtml(getProjectContact(project).name)}</span>
                    ${getProjectContact(project).role !== "Unknown"
                        ? `<span class="contact-role">${escapeHtml(getProjectContact(project).role)}</span>`
                        : ""
                    }
                </div>
            </td>

            <td class="${
                Number(
                    project.opportunity_score || 0
                ) >= 8
                    ? "score-high"
                    : ""
            }">
                ${escapeHtml(
                    project.opportunity || "Unknown"
                )}
            </td>
        `;


        row.addEventListener(
            "click",
            () => focusProjectOnMap(project)
        );


        tableBody.appendChild(row);

    });
}


/* =========================================================
   MAP MARKERS
========================================================= */

function renderMapMarkers(projects) {

    clearMapMarkers();


    const markerCoordinates = [];


    projects.forEach(project => {

      if (
          project.latitude === null ||
          project.longitude === null ||
          project.latitude === undefined ||
          project.longitude === undefined ||
          project.latitude === "" ||
          project.longitude === ""
      ) {
          return;
      }

const latitude =
    Number(project.latitude);

const longitude =
    Number(project.longitude);


if (
    !Number.isFinite(latitude) ||
    !Number.isFinite(longitude) ||
    latitude < 20 ||
    latitude > 55 ||
    longitude < -130 ||
    longitude > -60
) {
    return;
}


        const opportunityScore =
            Number(
                project.opportunity_score || 0
            );


        const markerColor =
            getMarkerColor(opportunityScore);


        const marker = L.circleMarker(
            [latitude, longitude],
            {
                radius:
                    opportunityScore >= 8
                        ? 9
                        : opportunityScore >= 5
                            ? 7
                            : 6,

                color: markerColor,
                fillColor: markerColor,
                fillOpacity: 0.82,

                weight: 2,
                opacity: 1
            }
        );


        marker.bindPopup(
            createProjectPopup(project),
            {
                maxWidth: 330,
                className:
                    "construction-popup"
            }
        );


        projectMarkerLayer.addLayer(marker);


        marker.projectPermitNumber =
            project.permit_number;

        marker.projectRecordId =
            project.record_id;


        mapMarkers.push(marker);

        markerCoordinates.push(
            [latitude, longitude]
        );

    });


    if (markerCoordinates.length > 0) {

        const bounds =
            L.latLngBounds(
                markerCoordinates
            );


        constructionMap.fitBounds(
            bounds,
            {
                padding: [35, 35],
                maxZoom: 13
            }
        );

    }
}


function clearMapMarkers() {

    projectMarkerLayer.clearLayers();
    mapMarkers = [];
}


function getMarkerColor(score) {

    if (score >= 8) {
        return "#8b5cf6";
    }

    if (score >= 5) {
        return "#f59e0b";
    }

    return "#4f7cff";
}


function createProjectPopup(project) {

    const score =
        Number(
            project.opportunity_score || 0
        );


    const projectContact = getProjectContact(project);


    const sourceButton =
        project.source_url
            ? `
                <a
                    href="${escapeHtml(
                        project.source_url
                    )}"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="popup-source-link"
                >
                    View Original Permit ↗
                </a>
            `
            : "";


    return `
        <div class="project-popup">

            <div class="popup-label">
                Construction Opportunity
            </div>

            <div class="popup-title">
                ${escapeHtml(
                    project.project || "Unknown Project"
                )}
            </div>

            <div class="popup-address">
                ${escapeHtml(
                    project.address || "Unknown Address"
                )},
                ${escapeHtml(
                    project.city || ""
                )}
            </div>

            <div class="popup-grid">

                <div>
                    <span>Market</span>
                    <strong>
                        ${escapeHtml(
                            project.market || "Unknown"
                        )}
                    </strong>
                </div>

                <div>
                    <span>Value</span>
                    <strong>
                        ${escapeHtml(
                            project.value || "Unknown"
                        )}
                    </strong>
                </div>

                <div>
                    <span>Project Contact</span>
                    <strong>
                        ${escapeHtml(
                            projectContact.name
                        )}
                    </strong>
                    <small>${escapeHtml(projectContact.role)}</small>
                </div>

                <div>
                    <span>Status</span>
                    <strong>
                        ${escapeHtml(
                            project.status || "Unknown"
                        )}
                    </strong>
                </div>

            </div>

            <div class="popup-opportunity">
                <span>Opportunity Score</span>

                <strong>
                    ${score}/10
                </strong>
            </div>

            <div class="popup-reason">
                ${escapeHtml(
                    project.opportunity_reason ||
                    "Potential construction opportunity."
                )}
            </div>

            ${sourceButton}

        </div>
    `;
}


function focusProjectOnMap(project) {

    const latitude =
        Number(project.latitude);

    const longitude =
        Number(project.longitude);


    if (
        !Number.isFinite(latitude) ||
        !Number.isFinite(longitude)
    ) {
        return;
    }


    constructionMap.flyTo(
        [latitude, longitude],
        15,
        {
            duration: 0.8
        }
    );


    const marker =
        mapMarkers.find(
            currentMarker =>
                currentMarker.projectRecordId === project.record_id
        );


    if (marker && typeof projectMarkerLayer.zoomToShowLayer === "function") {
        projectMarkerLayer.zoomToShowLayer(marker, () => marker.openPopup());
    } else if (marker) {
        marker.openPopup();
    }
}


function getProjectArea(project) {

    if (project.county && project.county !== "Unknown") {
        return project.county;
    }

    return project.jurisdiction || project.city || "Unknown";
}


function getProjectContact(project) {

    const contractor = String(project.contractor || "").trim();

    if (contractor && contractor.toLowerCase() !== "unknown") {
        return {
            name: contractor,
            role: "Contractor",
            source: project.contractor_source || project.source || "Unknown"
        };
    }

    const applicant = String(project.applicant || "").trim();

    if (applicant && applicant.toLowerCase() !== "unknown") {
        return {
            name: applicant,
            role: "Applicant",
            source: project.applicant_source || project.source || "Unknown"
        };
    }

    return {
        name: "Unknown",
        role: "Unknown",
        source: "Unknown"
    };
}


function setAssistantReady(isReady, loadFailed = false) {

    const input =
        document.getElementById("assistantInput");

    input.disabled = !isReady;
    input.placeholder = loadFailed
        ? "Project data could not be loaded"
        : isReady
            ? "Try: Show Jefferson projects over $2 million"
            : "Loading project data...";

    document.getElementById("assistantSubmit").disabled = !isReady;

    document
        .querySelectorAll(".assistant-suggestion")
        .forEach(button => {
            button.disabled = !isReady;
        });

    if (loadFailed) {
        const response = document.getElementById("assistantResponse");
        response.classList.add("is-visible");
        document.getElementById("assistantMessage").textContent =
            "Project data is unavailable. Refresh the dashboard to try again.";
    }
}


/* =========================================================
   ASK CONSTRUCTION RADAR
========================================================= */

function runAssistantQuery(question) {

    if (allProjects.length === 0) {
        return;
    }

    const response =
        document.getElementById("assistantResponse");

    const message =
        document.getElementById("assistantMessage");

    const resultsContainer =
        document.getElementById("assistantResults");

    const answer =
        ConstructionRadarAssistant.answer(
            allProjects,
            question,
            new Date()
        );

    response.classList.add("is-visible");
    message.textContent = answer.message;
    resultsContainer.innerHTML = "";

    if (answer.type === "contractor-ranking" || answer.type === "applicant-ranking") {
        answer.ranking.forEach(item => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "assistant-result";
            button.innerHTML = `
                <strong>${escapeHtml(item.name)}</strong>
                <span>${item.count.toLocaleString()} projects</span>
            `;
            button.addEventListener("click", () => {
                document.getElementById("searchInput").value = item.name;
                applyFilters();
                document.querySelector(".projects-section").scrollIntoView({ behavior: "smooth" });
            });
            resultsContainer.appendChild(button);
        });
        return;
    }

    if (answer.type === "comparison") {
        answer.comparison.forEach(item => {
            const card = document.createElement("div");
            card.className = "assistant-result";
            card.innerHTML = `
                <strong>${escapeHtml(item.name)}</strong>
                <span>${item.count.toLocaleString()} projects</span>
            `;
            resultsContainer.appendChild(card);
        });
        return;
    }

    if (answer.type === "projects" || answer.type === "count") {
        updateSummary(answer.results);
        renderProjects(answer.results);
        renderMapMarkers(answer.results);

        (answer.displayResults || answer.results.slice(0, 5)).slice(0, 5).forEach(project => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "assistant-result";
            button.innerHTML = `
                <strong>${escapeHtml(project.project || "Unknown project")}</strong>
                <span>${escapeHtml(getProjectArea(project))} · ${escapeHtml(project.value || "Unknown")} · ${escapeHtml(getProjectContact(project).name)} (${escapeHtml(getProjectContact(project).role)})</span>
            `;
            button.addEventListener("click", () => focusProjectOnMap(project));
            resultsContainer.appendChild(button);
        });
    }
}


/* =========================================================
   FILTERING
========================================================= */

function applyFilters() {

    const search =
        document
            .getElementById("searchInput")
            .value
            .toLowerCase();


    const market =
        document
            .getElementById("marketFilter")
            .value;


    const county =
        document
            .getElementById("countyFilter")
            .value;


    const status =
        document
            .getElementById("statusFilter")
            .value;


    const contractorAvailability =
        document
            .getElementById("contractorFilter")
            .value;


    const filtered =
        allProjects.filter(project => {

            const searchableText = `
                ${project.project || ""}
                ${project.address || ""}
                ${project.city || ""}
                ${project.description || ""}
                ${project.contractor || ""}
                ${project.applicant || ""}
            `.toLowerCase();


            const matchesSearch =
                searchableText.includes(search);


            const matchesMarket =
                !market ||
                project.market === market;


            const matchesCounty =
                !county ||
                getProjectArea(project) === county;


            const matchesStatus =
                !status ||
                project.status === status;


            const hasKnownContact =
                getProjectContact(project).role !== "Unknown";


            const matchesContractorAvailability =
                !contractorAvailability ||
                (contractorAvailability === "known" && hasKnownContact);


            return (
                matchesSearch &&
                matchesMarket &&
                matchesCounty &&
                matchesStatus &&
                matchesContractorAvailability
            );

        });


    updateSummary(filtered);
    renderProjects(filtered);
    renderMapMarkers(filtered);
}


/* =========================================================
   HTML SAFETY
========================================================= */

function escapeHtml(value) {

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


/* =========================================================
   EVENT LISTENERS
========================================================= */

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


document
    .getElementById("contractorFilter")
    .addEventListener(
        "change",
        applyFilters
    );


document
    .getElementById("assistantForm")
    .addEventListener("submit", event => {
        event.preventDefault();
        runAssistantQuery(
            document.getElementById("assistantInput").value
        );
    });


document
    .querySelectorAll(".assistant-suggestion")
    .forEach(button => {
        button.addEventListener("click", () => {
            const question = button.textContent.trim();
            document.getElementById("assistantInput").value = question;
            runAssistantQuery(question);
        });
    });


document
    .getElementById("themeToggle")
    .addEventListener("click", () => {
        const currentTheme = document.documentElement.dataset.theme;
        applyTheme(currentTheme === "light" ? "dark" : "light");
    });


initializeTheme();
loadProjects();
