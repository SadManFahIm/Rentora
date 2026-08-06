// lint-staged config. Task functions receive ABSOLUTE staged file paths.
// The repo root is derived from this file's own location so the config works
// no matter what cwd lint-staged is invoked from.
import path from "node:path";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const bin = (sub) => path.join(root, "frontend", "node_modules", ".bin", sub);

const python = () => {
  if (process.env.PYTHON) return process.env.PYTHON;
  const venvPython = path.join(root, "backend", "venv", "Scripts", "python.exe");
  return existsSync(venvPython) ? venvPython : "python";
};

const relFiles = (files) => files.map((f) => path.relative(root, f)).join(" ");

export default {
  "backend/**/*.py": (files) => {
    const rel = relFiles(files);
    return [
      `${python()} -m ruff check --fix ${rel}`,
      `${python()} -m ruff format ${rel}`,
    ];
  },
  "frontend/**/*.{ts,tsx}": (files) => {
    const rel = relFiles(files);
    return [
      `${bin("prettier")} --write ${rel}`,
      `${bin("eslint")} ${rel}`,
    ];
  },
  "frontend/**/*.{css,json,md,html}": (files) => {
    const rel = relFiles(files);
    return `${bin("prettier")} --write ${rel}`;
  },
};
