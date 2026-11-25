// Extract the third-party credits from the exact Chromium build we ship.
import { readFileSync, writeFileSync } from "node:fs";
import { brotliDecompressSync, gunzipSync, zstdDecompressSync } from "node:zlib";

const [pakPath, outputPath] = process.argv.slice(2);
const pak = readFileSync(pakPath);
if (pak.readUInt32LE(0) !== 5) throw new Error("Unsupported Chromium resource pack version");

const count = pak.readUInt16LE(8);
for (let index = 0; index < count; index += 1) {
  const entry = 12 + index * 6;
  const start = pak.readUInt32LE(entry + 2);
  const end = pak.readUInt32LE(entry + 8);
  let data = pak.subarray(start, end);
  if (data.length < 16) continue;
  if (data.readUInt16LE(0) === 0x8b1f) data = gunzipSync(data);
  else if (data.readUInt16LE(0) === 0x9b1e) data = brotliDecompressSync(data.subarray(8));
  else if (data.readUInt32LE(0) === 0xfd2fb528) data = zstdDecompressSync(data);
  if (data.length > 100_000 && data.includes("Redistribution and use") && data.includes("class=\"license\"")) {
    writeFileSync(outputPath, data);
    process.exit(0);
  }
}
throw new Error("Chromium license credits were not found in resources.pak");
