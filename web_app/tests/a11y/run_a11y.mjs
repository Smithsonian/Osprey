import { spawnSync } from 'node:child_process';
import { readdirSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

const cwd = process.cwd();
const outDir = path.join(cwd, 'tests', 'a11y', 'out');

function runRender() {
  const result = spawnSync('python3', [path.join('tests', 'a11y', 'render_a11y_pages.py')], {
    cwd,
    stdio: 'inherit',
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function isSeriousOrWorse(violation) {
  const impact = violation.impact || 'minor';
  return impact === 'serious' || impact === 'critical';
}

runRender();

const files = readdirSync(outDir).filter((f) => f.endsWith('.html'));
if (!files.length) {
  console.error(`No rendered HTML found in ${outDir}`);
  process.exit(1);
}

const browser = await chromium.launch();
const context = await browser.newContext();
try {
  for (const file of files) {
    const page = await context.newPage();
    const url = pathToFileURL(path.join(outDir, file)).toString();
    await page.goto(url);

    const results = await new AxeBuilder({ page }).analyze();
    const serious = results.violations.filter(isSeriousOrWorse);

    if (serious.length) {
      console.error(`\nA11Y violations in ${file}:`);
      for (const v of serious) {
        console.error(`- [${v.impact}] ${v.id}: ${v.help}`);
        for (const n of v.nodes.slice(0, 5)) {
          console.error(`  - ${n.target.join(', ')}: ${n.failureSummary || ''}`);
        }
      }
      process.exitCode = 2;
    } else {
      console.log(`OK: ${file}`);
    }

    await page.close();
  }
} finally {
  await context.close();
  await browser.close();
}

if (process.exitCode) {
  process.exit(process.exitCode);
}

