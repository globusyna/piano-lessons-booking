#!/usr/bin/env node
/**
 * Guards against the Node defect that broke the production build (issue #54).
 *
 * Vite's `vite:css-post` plugin encodes the module id of every `*.css?url`
 * import as hex inside a `__VITE_CSS_URL__<hex>__` placeholder, then at
 * `renderChunk` regex-matches that hex back out of the rendered chunk and
 * decodes it with `Buffer.from(hex, "hex")`.
 *
 * A single character above U+00FF anywhere in a chunk (this app has an em dash
 * in the "Studio admin — piano lesson calendar" title) forces V8 to back the
 * whole chunk string with two-byte UTF-16 storage, so the regex capture is a
 * sliced substring over a two-byte parent. On Node v23.2.0 `Buffer.from()`
 * returns an EMPTY buffer for exactly that shape of string, even though it is
 * pure ASCII and compares `===` equal to the same string built flat. The module
 * id therefore decodes to "", and the build dies with the useless message:
 *
 *     [plugin vite:css-post] Error: css content for "" was not found
 *
 * This checks the behaviour rather than the version number, so it keeps working
 * if the defect reappears on a release we have not enumerated.
 */

const payload = "/src/styles.css?transform-only";
const hex = Buffer.from(payload).toString("hex");

// A flat, freshly built string: the control.
const flat = hex.split("").join("");

// A slice of a parent string that contains one non-Latin-1 character, which is
// what vite hands to Buffer.from() during renderChunk.
const twoByteParent = "—".repeat(20000) + hex + "z".repeat(20000);
const sliced = twoByteParent.substring(20000, 20000 + hex.length);

const expected = Buffer.byteLength(payload);
const flatBytes = Buffer.from(flat, "hex").length;
const slicedBytes = Buffer.from(sliced, "hex").length;

if (sliced !== flat) {
  console.error("check-node-buffer: test setup is wrong, the two strings differ");
  process.exit(2);
}

if (flatBytes === expected && slicedBytes === expected) {
  process.exit(0);
}

console.error(`
Node ${process.version} cannot build this project.

Buffer.from(str, "hex") decodes a two-byte-backed sliced string incorrectly:

  expected bytes        : ${expected}
  flat string   decoded : ${flatBytes}
  sliced string decoded : ${slicedBytes}   <-- should equal ${expected}

Both strings are === equal, so this is a Node defect, not a project problem.
It makes vite's css-post plugin fail the production build with the misleading
error: [plugin vite:css-post] Error: css content for "" was not found

Known bad: v23.2.0. Use a Node matching the "engines" range in package.json
(see frontend/.nvmrc):

  nvm use

`);
process.exit(1);
