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

    const monthNumbers = {
        january: 0, february: 1, march: 2, april: 3, may: 4, june: 5,
        july: 6, august: 7, september: 8, october: 9, november: 10, december: 11
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

    function matchedAliasValues(text, aliases) {
        return Object.entries(aliases)
            .filter(([alias]) => text.includes(alias))
            .sort(([first], [second]) => text.indexOf(first) - text.indexOf(second))
            .map(([, value]) => value)
            .filter((value, index, values) => values.indexOf(value) === index);
    }

    function parseQuery(question, now) {
        const text = String(question || "").trim().toLowerCase();
        const filters = {};

        const matchedCounties = matchedAliasValues(text, countyAliases);

        if (matchedCounties.length === 1) filters.county = matchedCounties[0];

        const matchedMarkets = matchedAliasValues(text, marketAliases);

        if (matchedMarkets.length === 1) filters.market = matchedMarkets[0];

        if (/unknown|missing|without|no contractor/.test(text) && text.includes("contractor")) {
            filters.unknownContractor = true;
        } else if (/known|identified|verified/.test(text) && text.includes("contractor")) {
            filters.knownContractor = true;
        }

        const rangeMatch = text.match(
            /\b(?:between|from)\s*\$?([\d,.]+)\s*(million|thousand|m|k)?\s*(?:and|to|-)\s*\$?([\d,.]+)\s*(million|thousand|m|k)?\b/
        );

        if (rangeMatch) {
            const first = parseAmount(rangeMatch[1], rangeMatch[2]);
            const second = parseAmount(rangeMatch[3], rangeMatch[4]);
            filters.minimumValue = Math.min(first, second);
            filters.maximumValue = Math.max(first, second);
        }

        const amountMatch = !rangeMatch && text.match(
            /\b(over|above|more than|at least|under|below|less than|up to)\s*\$?([\d,.]+)\s*(million|thousand|m|k)?\b/
        );

        if (amountMatch) {
            const amount = parseAmount(amountMatch[2], amountMatch[3]);
            const lowerBound = ["over", "above", "more than", "at least"].includes(amountMatch[1]);
            filters[lowerBound ? "minimumValue" : "maximumValue"] = amount;
        }

        const contractorMatch =
            text.match(/\bhow many projects? (?:does|do)\s+(.+?)\s+(?:have|has)\??$/) ||
            text.match(
                /(?:projects?\s+(?:by|for)|contractor\s+is|contractor[:\s]+|builder\s+is|gc\s+is)\s*["']?([a-z0-9&.,' -]+?)["']?(?:\s+(?:over|under|above|below|in|issued|projects?))?$/
            );

        if (contractorMatch && !filters.unknownContractor) {
            filters.contractor = contractorMatch[1].trim();
        }

        if (text.includes("this month")) {
            const reference = now instanceof Date ? now : new Date();
            filters.issueYear = reference.getFullYear();
            filters.issueMonth = reference.getMonth();
        }

        if (text.includes("this week") || text.includes("last 7 days")) {
            const reference = now instanceof Date ? now : new Date();
            const cutoff = new Date(reference);
            cutoff.setDate(cutoff.getDate() - 7);
            filters.issueAfter = cutoff;
        }

        const dateMatch = text.match(
            /\b(after|since|before)\s+(?:(\d{4})-(\d{1,2})-(\d{1,2})|([a-z]+)\s+(\d{1,2})(?:,?\s+(\d{4}))?)\b/
        );

        if (dateMatch) {
            const reference = now instanceof Date ? now : new Date();
            let date;

            if (dateMatch[2]) {
                date = new Date(Number(dateMatch[2]), Number(dateMatch[3]) - 1, Number(dateMatch[4]));
            } else if (monthNumbers[dateMatch[5]] !== undefined) {
                date = new Date(
                    Number(dateMatch[7] || reference.getFullYear()),
                    monthNumbers[dateMatch[5]],
                    Number(dateMatch[6])
                );
            }

            if (date && !Number.isNaN(date.getTime())) {
                filters[dateMatch[1] === "before" ? "issueBefore" : "issueAfter"] = date;
            }
        }

        if (/with (?:map )?coordinates|mapped projects|on the map/.test(text)) {
            filters.hasCoordinates = true;
        } else if (/without (?:map )?coordinates|missing coordinates|not mapped/.test(text)) {
            filters.hasCoordinates = false;
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
            compareCounties: /compare|versus|\bvs\.?\b/.test(text) && matchedCounties.length > 1
                ? matchedCounties
                : [],
            compareMarkets: /compare|versus|\bvs\.?\b/.test(text) && matchedMarkets.length > 1
                ? matchedMarkets
                : [],
            sortByValue: /highest|largest|biggest|top|most valuable/.test(text),
            sortByDate: /newest|most recent|latest/.test(text)
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

        if (filters.knownContractor && contractor.toLowerCase() === "unknown") {
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

        const issuedDate = new Date(`${project.issued_date}T00:00:00`);

        if (filters.issueAfter && (Number.isNaN(issuedDate.getTime()) || issuedDate < filters.issueAfter)) {
            return false;
        }

        if (filters.issueBefore && (Number.isNaN(issuedDate.getTime()) || issuedDate >= filters.issueBefore)) {
            return false;
        }

        if (filters.hasCoordinates !== undefined) {
            const latitude = Number(project.latitude);
            const longitude = Number(project.longitude);
            const hasCoordinates =
                project.latitude !== null &&
                project.latitude !== undefined &&
                project.latitude !== "" &&
                project.longitude !== null &&
                project.longitude !== undefined &&
                project.longitude !== "" &&
                Number.isFinite(latitude) &&
                Number.isFinite(longitude);
            if (hasCoordinates !== filters.hasCoordinates) return false;
        }

        return true;
    }

    function describeFilters(filters) {
        const parts = [];

        if (filters.county) parts.push(`${filters.county} County`);
        if (filters.market) parts.push(filters.market.toLowerCase());
        if (filters.contractor) parts.push(`contractor matching “${filters.contractor}”`);
        if (filters.unknownContractor) parts.push("unknown contractors");
        if (filters.knownContractor) parts.push("known contractors");
        if (filters.minimumValue !== undefined) parts.push(`value at least $${filters.minimumValue.toLocaleString()}`);
        if (filters.maximumValue !== undefined) parts.push(`value up to $${filters.maximumValue.toLocaleString()}`);
        if (filters.issueYear !== undefined) parts.push("issued this month");
        else if (filters.issued) parts.push("issued status");
        if (filters.issueAfter && filters.issueYear === undefined) parts.push(`issued after ${filters.issueAfter.toLocaleDateString()}`);
        if (filters.issueBefore) parts.push(`issued before ${filters.issueBefore.toLocaleDateString()}`);
        if (filters.hasCoordinates === true) parts.push("with map coordinates");
        if (filters.hasCoordinates === false) parts.push("without map coordinates");

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
            parsed.compareCounties.length > 0 ||
            parsed.compareMarkets.length > 0 ||
            parsed.sortByValue ||
            parsed.sortByDate;

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

        if (parsed.sortByDate) {
            matches = [...matches].sort(
                (a, b) => new Date(b.issued_date || 0) - new Date(a.issued_date || 0)
            );
        }

        const description = describeFilters(parsed.filters);

        if (parsed.compareCounties.length) {
            const comparison = parsed.compareCounties.map(name => ({
                name: `${name} County`,
                count: projects.filter(project =>
                    project.county === name && matchesFilters(project, {...parsed.filters, county: undefined})
                ).length
            }));
            return {
                type: "comparison",
                message: `Project comparison: ${comparison.map(item => `${item.name} has ${item.count.toLocaleString()}`).join("; ")}.`,
                comparison,
                results: matches
            };
        }

        if (parsed.compareMarkets.length) {
            const comparison = parsed.compareMarkets.map(name => ({
                name,
                count: projects.filter(project =>
                    project.market === name && matchesFilters(project, {...parsed.filters, market: undefined})
                ).length
            }));
            return {
                type: "comparison",
                message: `Market comparison: ${comparison.map(item => `${item.name} has ${item.count.toLocaleString()}`).join("; ")}.`,
                comparison,
                results: matches
            };
        }

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
