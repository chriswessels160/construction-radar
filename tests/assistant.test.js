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
        issued_date: "2026-07-12"
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
