const test = require("node:test");
const assert = require("node:assert/strict");
const assistant = require("../assistant.js");

const projects = [
    {
        record_id: "louisville:1",
        county: "Jefferson",
        market: "Commercial",
        status: "Issued",
        value_numeric: 3000000,
        contractor: "WODA CONSTRUCTION INC",
        issued_date: "2026-07-12",
        latitude: 38.2,
        longitude: -85.7
    },
    {
        record_id: "cincinnati:1",
        county: "Hamilton",
        market: "Commercial",
        status: "Permit Issued",
        value_numeric: 2000000,
        contractor: "HGC CONSTRUCTION",
        issued_date: "2026-07-20"
    },
    {
        record_id: "louisville:2",
        county: "Jefferson",
        market: "Industrial",
        status: "Issued",
        value_numeric: 500000,
        contractor: "Unknown",
        issued_date: "2026-06-03"
    }
];

test("filters Louisville aliases and value thresholds", () => {
    const answer = assistant.answer(
        projects,
        "Show Louisville projects over $2 million"
    );

    assert.equal(answer.results.length, 1);
    assert.equal(answer.results[0].record_id, "louisville:1");
});

test("counts projects with unknown contractors", () => {
    const answer = assistant.answer(
        projects,
        "How many Jefferson projects have unknown contractors?"
    );

    assert.equal(answer.type, "count");
    assert.equal(answer.results.length, 1);
});

test("filters projects with known contractors", () => {
    const answer = assistant.answer(
        projects,
        "Show Jefferson projects with known contractors"
    );

    assert.equal(answer.results.length, 1);
    assert.equal(answer.results[0].record_id, "louisville:1");
    assert.match(answer.message, /known contractors/);
});

test("ranks known contractors without fabricating missing names", () => {
    const answer = assistant.answer(
        projects,
        "Which contractor has the most projects?"
    );

    assert.equal(answer.type, "contractor-ranking");
    assert.equal(answer.ranking.length, 2);
    assert.equal(answer.ranking.some(item => item.name === "Unknown"), false);
});

test("filters records issued in the reference month", () => {
    const answer = assistant.answer(
        projects,
        "How many projects were issued this month?",
        new Date("2026-07-31T12:00:00Z")
    );

    assert.equal(answer.results.length, 2);
});

test("returns guidance for unsupported questions", () => {
    const answer = assistant.answer(projects, "Tell me a joke");
    assert.equal(answer.type, "help");
    assert.equal(answer.results.length, 0);
});

test("answers contractor-specific counts", () => {
    const answer = assistant.answer(projects, "How many projects does HGC Construction have?");
    assert.equal(answer.type, "count");
    assert.equal(answer.results.length, 1);
});

test("filters value ranges", () => {
    const answer = assistant.answer(projects, "Show projects between $1 million and $4 million");
    assert.equal(answer.results.length, 2);
});

test("sorts the newest projects first", () => {
    const answer = assistant.answer(projects, "Show the newest projects");
    assert.equal(answer.results[0].record_id, "cincinnati:1");
});

test("filters projects after a calendar date", () => {
    const answer = assistant.answer(projects, "Show projects after July 15, 2026");
    assert.equal(answer.results.length, 1);
    assert.equal(answer.results[0].record_id, "cincinnati:1");
});

test("compares Hamilton and Jefferson", () => {
    const answer = assistant.answer(projects, "Compare Hamilton versus Jefferson");
    assert.equal(answer.type, "comparison");
    assert.deepEqual(answer.comparison.map(item => item.count), [1, 2]);
});

test("compares commercial and industrial markets", () => {
    const answer = assistant.answer(projects, "Compare commercial vs industrial projects");
    assert.equal(answer.type, "comparison");
    assert.deepEqual(answer.comparison.map(item => item.count), [2, 1]);
});

test("filters projects with map coordinates", () => {
    const answer = assistant.answer(projects, "Show projects with map coordinates");
    assert.equal(answer.results.length, 1);
    assert.equal(answer.results[0].record_id, "louisville:1");
});
