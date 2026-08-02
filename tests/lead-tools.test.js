const test = require("node:test");
const assert = require("node:assert/strict");
const tools = require("../lead-tools.js");

const projects = [
    { record_id: "source:1", project: "Office, Phase 1", permit_number: "P-1", county: "Hamilton", market: "Commercial" },
    { record_id: "source:2", project: "Warehouse", permit_number: "P-2", county: "Jefferson", market: "Industrial" }
];

test("selects saved or compared projects in dataset order", () => {
    assert.deepEqual(tools.selectedProjects(projects, ["source:2"]), [projects[1]]);
});

test("exports quoted CSV without losing commas or quotes", () => {
    const csv = tools.projectsToCsv([projects[0]], () => ({ name: 'Builder "A"', role: "Contractor" }));
    assert.match(csv, /"Office, Phase 1"/);
    assert.match(csv, /"Builder ""A"""/);
    assert.match(csv, /"P-1"/);
});
