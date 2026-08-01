(function (root, factory) {
    const api = factory();

    if (typeof module === "object" && module.exports) {
        module.exports = api;
    }

    root.ConstructionRadarAssistant = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    const countyAliases = {
        jefferson: "Jefferson",
        louisville: "Jefferson",
        hamilton: "Hamilton",
        cincinnati: "Hamilton",
        cincy: "Hamilton"
    };

    const marketAliases = {
        commercial: "Commercial",
        industrial: "Industrial",
        multifamily: "Multifamily / Residential",
        residential: "Multifamily / Residential",
        warehouse: "Warehouse / Logistics",
        logistics: "Warehouse / Logistics"
    };

    function numericValue(project) {
        const direct = Number(project.value_numeric);

        if (Number.isFinite(direct)) {
            return direct;
        }

        const parsed = Number(String(project.value || "").replace(/[^0-9.-]/g, ""));
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function parseAmount(raw, suffix) {
        let amount = Number(String(raw).replace(/,/g, ""));

        if (suffix === "m" || suffix === "million") {
            amount *= 1000000;
        } else if (suffix === "k" || suffix === "thousand") {
            amount *= 1000;
        }

        return amount;
    }

    function parseQuery(question, now) {
        const text = String(question || "").trim().toLowerCase();
        const filters = {};

        Object.entries(countyAliases).some(([alias, county]) => {
            if (text.includes(alias)) {
                filters.county = county;
                return true;
            }
            return false;
        });

        Object.entries(marketAliases).some(([alias, market]) => {
            if (text.includes(alias)) {
                filters.market = market;
                return true;
            }
            return false;
        });

        if (/unknown|missing|without|no contractor/.test(text) && text.includes("contractor")) {
            filters.unknownContractor = true;
        }

        const amountMatch = text.match(
            /\b(over|above|more than|at least|under|below|less than|up to)\s*\$?([\d,.]+)\s*(million|thousand|m|k)?\b/
        );

        if (amountMatch) {
            const amount = parseAmount(amountMatch[2], amountMatch[3]);
            const lowerBound = ["over", "above", "more than", "at least"].includes(amountMatch[1]);
            filters[lowerBound ? "minimumValue" : "maximumValue"] = amount;
        }

        const contractorMatch = text.match(
            /(?:projects?\s+by|contractor\s+is|contractor[:\s]+)\s*["']?([a-z0-9&.,' -]+?)["']?(?:\s+(?:over|under|above|below|in|issued|projects?))?$/
        );

        if (contractorMatch && !filters.unknownContractor) {
            filters.contractor = contractorMatch[1].trim();
        }

        if (text.includes("this month")) {
            const reference = now instanceof Date ? now : new Date();
            filters.issueYear = reference.getFullYear();
            filters.issueMonth = reference.getMonth();
        }

        if (text.includes("issued")) {
            filters.issued = true;
        }

        const topMatch = text.match(/\btop\s+(\d+)\b/);
        const requestedLimit = topMatch ? Number(topMatch[1]) : 10;

        return {
            text,
            filters,
            limit: Math.min(Math.max(requestedLimit, 1), 50),
            wantsCount: /\bhow many\b|\bcount\b/.test(text),
            wantsContractorRanking:
                /which contractor|top contractors|contractors? (?:have|with) the most|most active contractor/.test(text),
            sortByValue: /highest|largest|biggest|top|most valuable/.test(text)
        };
    }

    function matchesFilters(project, filters) {
        if (filters.county && project.county !== filters.county) {
            return false;
        }

        if (filters.market && project.market !== filters.market) {
            return false;
        }

        const contractor = String(project.contractor || "Unknown").trim();

        if (filters.unknownContractor && contractor.toLowerCase() !== "unknown") {
            return false;
        }

        if (filters.contractor && !contractor.toLowerCase().includes(filters.contractor)) {
            return false;
        }

        const value = numericValue(project);

        if (filters.minimumValue !== undefined && value < filters.minimumValue) {
            return false;
        }

        if (filters.maximumValue !== undefined && value > filters.maximumValue) {
            return false;
        }

        if (filters.issued && !String(project.status || "").toLowerCase().includes("issued")) {
            return false;
        }

        if (filters.issueYear !== undefined) {
            const date = new Date(`${project.issued_date}T00:00:00`);

            if (
                Number.isNaN(date.getTime()) ||
                date.getFullYear() !== filters.issueYear ||
                date.getMonth() !== filters.issueMonth
            ) {
                return false;
            }
        }

        return true;
    }

    function describeFilters(filters) {
        const parts = [];

        if (filters.county) parts.push(`${filters.county} County`);
        if (filters.market) parts.push(filters.market.toLowerCase());
        if (filters.contractor) parts.push(`contractor matching “${filters.contractor}”`);
        if (filters.unknownContractor) parts.push("unknown contractors");
        if (filters.minimumValue !== undefined) parts.push(`value at least $${filters.minimumValue.toLocaleString()}`);
        if (filters.maximumValue !== undefined) parts.push(`value up to $${filters.maximumValue.toLocaleString()}`);
        if (filters.issueYear !== undefined) parts.push("issued this month");
        else if (filters.issued) parts.push("issued status");

        return parts.length ? parts.join(", ") : "all active projects";
    }

    function rankContractors(projects, limit) {
        const counts = new Map();

        projects.forEach(project => {
            const name = String(project.contractor || "Unknown").trim();
            if (!name || name.toLowerCase() === "unknown") return;
            counts.set(name, (counts.get(name) || 0) + 1);
        });

        return [...counts.entries()]
            .map(([name, count]) => ({ name, count }))
            .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
            .slice(0, limit);
    }

    function answer(projects, question, now) {
        const parsed = parseQuery(question, now);

        if (!parsed.text) {
            return {
                type: "help",
                message: "Ask about a county, contractor, market, permit value, issue date, or project ranking.",
                results: []
            };
        }

        const hasSupportedIntent =
            Object.keys(parsed.filters).length > 0 ||
            parsed.wantsCount ||
            parsed.wantsContractorRanking ||
            parsed.sortByValue;

        if (!hasSupportedIntent) {
            return {
                type: "help",
                message: "I can filter by Hamilton or Jefferson County, contractor, market, status, value, and issue month—or rank projects and contractors.",
                results: []
            };
        }

        let matches = projects.filter(project => matchesFilters(project, parsed.filters));

        if (parsed.sortByValue) {
            matches = [...matches].sort((a, b) => numericValue(b) - numericValue(a));
        }

        const description = describeFilters(parsed.filters);

        if (parsed.wantsContractorRanking) {
            const ranking = rankContractors(matches, parsed.limit);
            return {
                type: "contractor-ranking",
                message: ranking.length
                    ? `Top contractors for ${description}.`
                    : `No known contractors matched ${description}.`,
                ranking,
                results: matches
            };
        }

        return {
            type: parsed.wantsCount ? "count" : "projects",
            message: parsed.wantsCount
                ? `${matches.length.toLocaleString()} projects match ${description}.`
                : `${matches.length.toLocaleString()} projects match ${description}. Showing ${Math.min(matches.length, parsed.limit)}.`,
            results: matches,
            displayResults: matches.slice(0, parsed.limit)
        };
    }

    return {
        answer,
        matchesFilters,
        numericValue,
        parseQuery,
        rankContractors
    };
}));
