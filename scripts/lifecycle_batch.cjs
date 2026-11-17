// Python build and browser use the very same availability implementation.
const fs = require("node:fs");
const { availability } = require("../assets/availability.js");
const { models, at } = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(models.map(m => availability(m, at))));
