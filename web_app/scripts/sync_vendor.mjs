// Copies the pinned dist files for self-hosted frontend libraries from
// node_modules/ into static/vendor/, so templates/base.html (and the chart
// pages) don't depend on a CDN at runtime. Versions are pinned in
// package.json; after bumping one there, run `npm install && npm run vendor`
// and commit the changed files under static/vendor/.
//
// Run with: node scripts/sync_vendor.mjs  (or `npm run vendor`)

import { existsSync, mkdirSync, copyFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const NODE_MODULES = join(ROOT, 'node_modules');
const VENDOR = join(ROOT, 'static', 'vendor');

// Each entry copies one file, or (with `dir: true`) one directory recursively.
const FILES = [
  ['bootstrap/dist/css/bootstrap.min.css', 'bootstrap/bootstrap.min.css'],
  ['bootstrap/dist/js/bootstrap.bundle.min.js', 'bootstrap/bootstrap.bundle.min.js'],

  // css/ and webfonts/ must stay siblings, matching the npm package layout:
  // all.min.css references fonts via a relative `../webfonts/...` url().
  ['@fortawesome/fontawesome-free/css/all.min.css', 'fontawesome/css/all.min.css'],
  ['@fortawesome/fontawesome-free/webfonts', 'fontawesome/webfonts', { dir: true }],

  ['jquery/dist/jquery.min.js', 'jquery/jquery.min.js'],

  ['datatables.net-dt/css/dataTables.dataTables.min.css', 'datatables/dataTables.dataTables.min.css'],
  ['datatables.net-dt/js/dataTables.dataTables.min.js', 'datatables/dataTables.dataTables.min.js'],
  ['datatables.net/js/dataTables.min.js', 'datatables/dataTables.min.js'],
  ['datatables.net-buttons/js/dataTables.buttons.min.js', 'datatables/dataTables.buttons.min.js'],
  ['datatables.net-buttons/js/buttons.html5.min.js', 'datatables/buttons.html5.min.js'],
  ['datatables.net-buttons-dt/js/buttons.dataTables.min.js', 'datatables/buttons.dataTables.min.js'],

  ['jszip/dist/jszip.min.js', 'jszip/jszip.min.js'],

  // chart.js stopped publishing a pre-minified UMD build to npm (jsdelivr
  // minifies dist/chart.umd.js on the fly for the .min.js CDN URL); ship the
  // unminified file instead. It's identical bytes to what Flask-Minify
  // already produces for our own static/js/*.js in prod, so this costs
  // nothing at runtime.
  ['chart.js/dist/chart.umd.js', 'chartjs/chart.umd.js'],
  ['chartjs-adapter-date-fns/dist/chartjs-adapter-date-fns.bundle.min.js', 'chartjs/chartjs-adapter-date-fns.bundle.min.js'],
];

function copyDir(from, to) {
  mkdirSync(to, { recursive: true });
  for (const entry of readdirSync(from)) {
    const fromPath = join(from, entry);
    const toPath = join(to, entry);
    if (statSync(fromPath).isDirectory()) {
      copyDir(fromPath, toPath);
    } else {
      copyFileSync(fromPath, toPath);
    }
  }
}

let missing = 0;
for (const [from, to, opts] of FILES) {
  const fromPath = join(NODE_MODULES, from);
  const toPath = join(VENDOR, to);
  if (!existsSync(fromPath)) {
    console.error(`missing: ${from} (run \`npm install\` first)`);
    missing++;
    continue;
  }
  mkdirSync(dirname(toPath), { recursive: true });
  if (opts && opts.dir) {
    copyDir(fromPath, toPath);
  } else {
    copyFileSync(fromPath, toPath);
  }
  console.log(`vendored: ${to}`);
}

if (missing > 0) {
  console.error(`${missing} package file(s) missing; vendor sync incomplete.`);
  process.exit(1);
}
