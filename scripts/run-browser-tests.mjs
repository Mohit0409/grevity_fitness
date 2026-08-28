import { spawn } from 'node:child_process';
import { once } from 'node:events';
import path from 'node:path';
import process from 'node:process';

const python = process.env.GRAVITY_E2E_PYTHON || 'python';
const runner = spawn(python, [path.resolve('scripts', 'run-browser-tests.py'), ...process.argv.slice(2)], {
  cwd: process.cwd(),
  env: { ...process.env, GRAVITY_E2E_NODE: process.execPath },
  stdio: 'inherit',
  windowsHide: true,
});

const [exitCode] = await once(runner, 'exit');
process.exitCode = Number.isInteger(exitCode) ? exitCode : 1;
