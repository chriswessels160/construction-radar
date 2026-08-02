(function (root, factory) {
    const api = factory();
    if (typeof module === "object" && module.exports) module.exports = api;
    root.ConstructionLeadTools = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
    function projectId(project) {
        return String(project.record_id || `${project.source_id || "source"}:${project.permit_number || "unknown"}`);
    }

    function csvCell(value) {
        const text = String(value ?? "").replaceAll('"', '""');
        return `"${text}"`;
    }

    function projectsToCsv(projects, contactForProject) {
        const headers = ["Project", "Permit Number", "Market", "Area", "Status", "Value", "Project Contact", "Contact Role", "Address", "Issued Date", "Source URL"];
        const rows = projects.map(project => {
            const contact = contactForProject(project);
            return [
                project.project, project.permit_number, project.market,
                project.county !== "Unknown" ? project.county : (project.jurisdiction || project.city),
                project.status, project.value, contact.name, contact.role,
                [project.address, project.city, project.state].filter(Boolean).join(", "),
                project.issued_date, project.source_url
            ].map(csvCell).join(",");
        });
        return [headers.map(csvCell).join(","), ...rows].join("\r\n");
    }

    function selectedProjects(projects, ids) {
        const wanted = new Set(ids);
        return projects.filter(project => wanted.has(projectId(project)));
    }

    return { projectId, projectsToCsv, selectedProjects };
});
