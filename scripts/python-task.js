// Use the same Python environment for tests, builds and the application.
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const root = path.join(__dirname, '..');
const local = path.join(
  root,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'
);
const python =
  process.env.CLIPA_PYTHON ||
  (fs.existsSync(local) ? local : process.platform === 'win32' ? 'python' : 'python3');
const task = process.argv[2];
const args =
  task === 'test'
    ? ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-v']
    : task === 'build'
      ? ['scripts/build-backend.py']
      : null;
if (!args) throw new Error('Tarefa Python inválida.');
const result = spawnSync(python, args, {
  cwd: root,
  stdio: 'inherit',
  windowsHide: true,
  env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
});
if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}
process.exit(result.status ?? 1);
