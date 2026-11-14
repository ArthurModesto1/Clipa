const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function launch() {
  const app = new EventEmitter();
  app.whenReady = () => ({
    then(callback) {
      app.start = callback;
    },
  });
  app.quit = () => app.emit('before-quit');
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stdout.setEncoding = () => {};
  child.stderr = new EventEmitter();
  child.kill = () => {
    child.killed = true;
  };
  const handlers = new Map();
  const state = { app, child, handlers, windows: [], errors: [], killed: [] };
  class BrowserWindow extends EventEmitter {
    constructor() {
      super();
      state.windows.push(this);
      this.webContents = { setWindowOpenHandler() {}, on() {} };
    }
    loadFile(file) {
      this.file = file;
    }
    static getAllWindows() {
      return state.windows;
    }
  }
  const electron = {
    app,
    BrowserWindow,
    shell: {},
    ipcMain: {
      on() {},
      handle(name, callback) {
        handlers.set(name, callback);
      },
    },
    dialog: {
      showErrorBox(...args) {
        state.errors.push(args);
      },
    },
  };
  const filename = path.join(__dirname, '../electron/main.js');
  vm.runInNewContext(fs.readFileSync(filename, 'utf8'), {
    require(name) {
      if (name === 'electron') return electron;
      if (name === 'child_process')
        return {
          spawn(command, args, options) {
            state.spawn = { command, args, options };
            return child;
          },
        };
      return require(name);
    },
    __dirname: path.dirname(filename),
    console,
    setTimeout,
    clearTimeout,
    process: {
      platform: 'win32',
      env: {},
      kill(pid) {
        state.killed.push(pid);
      },
    },
  });
  state.started = app.start();
  return state;
}

test('opens the UI only after its own backend is ready and stops the actual Python PID', async () => {
  const s = launch();
  assert.deepEqual(Array.from(s.spawn.args).slice(-2), ['--port', '0']);
  assert.equal(s.windows.length, 0);
  assert.equal(s.spawn.options.windowsHide, true);
  assert.ok(s.spawn.options.env.CLIPA_API_TOKEN.length >= 32);
  assert.equal(s.handlers.get('get-backend-config')().token, s.spawn.options.env.CLIPA_API_TOKEN);
  // A readiness line may be split across pipe chunks and follow other output.
  s.child.stdout.emit('data', 'startup diagnostic\nCLIPA_RE');
  assert.equal(s.windows.length, 0);
  s.child.stdout.emit('data', 'ADY {"port":49187,"pid":12345}\n');
  await s.started;
  assert.equal(s.windows.length, 1);
  assert.equal(s.handlers.get('get-backend-url')(), 'http://127.0.0.1:49187');
  s.app.emit('before-quit');
  assert.deepEqual(s.killed, [12345]);
  assert.equal(s.child.killed, true);
});

test('reports startup failure without opening a UI connected to an old backend', async () => {
  const s = launch();
  s.child.stderr.emit('data', Buffer.from('Python dependency missing'));
  s.child.emit('exit', 1);
  await s.started;
  assert.equal(s.windows.length, 0);
  assert.match(s.errors[0][1], /Python dependency missing/);
  assert.equal(s.child.killed, true);
});

test('rejects malformed readiness data', async () => {
  const s = launch();
  s.child.stdout.emit('data', 'CLIPA_READY {"port":0,"pid":12345}\n');
  await s.started;
  assert.equal(s.windows.length, 0);
  assert.equal(s.errors.length, 1);
  assert.equal(s.child.killed, true);
});
