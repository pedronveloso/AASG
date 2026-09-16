import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { relative, resolve } from 'node:path';

const output = resolve('dist');
const contentRoot = resolve('src/content/docs');
const deploymentBase = '/AASG/';
const requiredFiles = [
  'index.html',
  'llms.txt',
  'overview.md.txt',
  'getting-started/quickstart.md.txt',
  'concepts/android-test-contract.md.txt',
  'guides/capture-workflow.md.txt',
  'guides/rendering.md.txt',
  'guides/device-frames.md.txt',
  'reference/configuration.md.txt',
  'reference/cli.md.txt',
  'reference/semantic-metadata.md.txt',
  'contributing.md.txt',
];

for (const file of requiredFiles) {
  if (!existsSync(resolve(output, file))) {
    throw new Error(`Missing published documentation asset: ${file}`);
  }
}

const index = readFileSync(resolve(output, 'llms.txt'), 'utf8');
const links = [...index.matchAll(/\((https:\/\/pedronveloso\.github\.io\/AASG\/[^)]+\.md\.txt)\)/g)];

if (links.length === 0) {
  throw new Error('llms.txt does not link to any Markdown endpoints');
}

for (const [, url] of links) {
  const path = new URL(url).pathname.replace(/^\/AASG\//, '');
  if (!existsSync(resolve(output, path))) {
    throw new Error(`llms.txt points to a missing Markdown endpoint: ${url}`);
  }
}

function sourceFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name);
    return entry.isDirectory() ? sourceFiles(path) : [path];
  });
}

const routes = new Set(
  sourceFiles(contentRoot)
    .filter((file) => /\.(md|mdx)$/.test(file))
    .map((file) => relative(contentRoot, file).replace(/\.(md|mdx)$/, ''))
    .map((slug) => (slug === 'index' ? '/' : `/${slug}/`)),
);

for (const file of sourceFiles(contentRoot).filter((entry) => /\.(md|mdx)$/.test(entry))) {
  const markdown = readFileSync(file, 'utf8');
  for (const [, target] of markdown.matchAll(/\]\((\/[^)#?\s]+)\)/g)) {
    const route = target.endsWith('/') ? target : `${target}/`;
    if (!routes.has(route)) {
      throw new Error(`Broken internal documentation link in ${file}: ${target}`);
    }
  }
}

for (const file of sourceFiles(output).filter((entry) => entry.endsWith('.html'))) {
  const html = readFileSync(file, 'utf8');
  for (const [, target] of html.matchAll(/\bhref="(\/[^"#?][^"]*)"/g)) {
    if (!target.startsWith(deploymentBase)) {
      throw new Error(`Link is missing the deployment base in ${file}: ${target}`);
    }
  }
}
