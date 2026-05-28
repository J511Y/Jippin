/**
 * scripts/generate.ts — JSON Schema → TypeScript 타입 생성기.
 *
 * - 입력: ../schemas/*.schema.json
 * - 출력: ../ts/<kebab>.ts + ../ts/index.ts
 * - 결정성: file order, banner, prettier 옵션을 고정해 재실행 시 동일 출력.
 */

import { readdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { compileFromFile, type Options } from "json-schema-to-typescript";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SCHEMAS_DIR = resolve(__dirname, "..", "schemas");
const TS_DIR = resolve(__dirname, "..", "ts");

const BANNER = `/* eslint-disable */
/**
 * THIS FILE IS AUTO-GENERATED — DO NOT EDIT BY HAND.
 * Source: packages/contracts/schemas/*.schema.json
 * Regenerate: pnpm -C packages/contracts run generate
 */`;

const OPTIONS: Partial<Options> = {
  bannerComment: BANNER,
  additionalProperties: false,
  declareExternallyReferenced: true,
  enableConstEnums: false,
  strictIndexSignatures: true,
  style: {
    singleQuote: false,
    semi: true,
    trailingComma: "all",
    printWidth: 100,
    tabWidth: 2,
  },
};

function tsFileNameFor(schemaFile: string): string {
  return schemaFile.replace(/\.schema\.json$/, ".ts");
}

function exportNameFor(schemaFile: string): string {
  return "./" + schemaFile.replace(/\.schema\.json$/, "");
}

async function main(): Promise<void> {
  const entries = (await readdir(SCHEMAS_DIR))
    .filter((f) => f.endsWith(".schema.json"))
    .sort();

  if (entries.length === 0) {
    throw new Error(`No *.schema.json found in ${SCHEMAS_DIR}`);
  }

  for (const file of entries) {
    const inPath = resolve(SCHEMAS_DIR, file);
    const outPath = resolve(TS_DIR, tsFileNameFor(file));
    const compiled = await compileFromFile(inPath, OPTIONS);
    await writeFile(outPath, compiled, "utf8");
    process.stdout.write(`[ok] ts: ${file} -> ${tsFileNameFor(file)}\n`);
  }

  const indexLines = [
    BANNER,
    "",
    ...entries.map((f) => `export * from "${exportNameFor(f)}";`),
    "",
  ];
  await writeFile(resolve(TS_DIR, "index.ts"), indexLines.join("\n"), "utf8");
  process.stdout.write(`[ok] ts: index.ts (${entries.length} exports)\n`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
