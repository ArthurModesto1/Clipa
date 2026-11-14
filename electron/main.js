const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const { randomBytes } = require('crypto');

let mainWindow;
let pythonProcess;
let backendPid;

let backendUrl;
const backendToken = randomBytes(32).toString('hex');

function getPythonPath() {
  if (app.isPackaged) {
    const base = process.resourcesPath;
    if (process.platform === 'win32') return path.join(base, 'backend', 'server.exe');
    return path.join(base, 'backend', 'server');
  }
  if (process.env.CLIPA_PYTHON) return process.env.CLIPA_PYTHON;
  const venvPython = path.join(
    __dirname,
    '..',
    '.venv',
    process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'
  );
  if (fs.existsSync(venvPython)) return venvPython;
  return process.platform === 'win32' ? 'python' : 'python3';
}

function startPythonBackend() {
  const pythonPath = getPythonPath();
  const scriptPath = path.join(__dirname, '..', 'python', 'server.py');

  return new Promise((resolve, reject) => {
    const args = app.isPackaged ? [] : [scriptPath];
    pythonProcess = spawn(pythonPath, [...args, '--port', '0'], {
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
      env: {
        ...process.env,
        PYTHONIOENCODING: 'utf-8',
        CLIPA_API_TOKEN: backendToken,
        ...(app.isPackaged
          ? {
              CLIPA_FFMPEG_DIR: path.join(process.resourcesPath, 'tools'),
              CLIPA_NODE_PATH: path.join(
                process.resourcesPath,
                'tools',
                process.platform === 'win32' ? 'node.exe' : 'node'
              ),
            }
          : {}),
      },
    });
    let output = '';
    let errors = '';
    const timeout = setTimeout(() => {
      reject(new Error('O backend Python não iniciou em 30 segundos.'));
    }, 30000);
    pythonProcess.stdout.setEncoding('utf8');
    pythonProcess.stdout.on('data', (chunk) => {
      output += chunk;
      let end;
      while ((end = output.indexOf('\n')) !== -1) {
        const line = output.slice(0, end).trim();
        output = output.slice(end + 1);
        if (!line.startsWith('CLIPA_READY ')) continue;
        try {
          const ready = JSON.parse(line.slice('CLIPA_READY '.length));
          if (
            !Number.isInteger(ready.port) ||
            ready.port < 1 ||
            ready.port > 65535 ||
            !Number.isInteger(ready.pid) ||
            ready.pid < 1
          ) {
            throw new Error('Resposta inválida do backend Python.');
          }
          backendPid = ready.pid;
          backendUrl = `http://127.0.0.1:${ready.port}`;
          clearTimeout(timeout);
          resolve();
        } catch (err) {
          clearTimeout(timeout);
          reject(err);
        }
      }
    });
    // Drain diagnostics without forwarding them to a possibly detached console.
    pythonProcess.stderr.on('data', (chunk) => {
      errors = (errors + chunk.toString('utf8')).slice(-4000);
    });
    pythonProcess.once('error', (err) => {
      clearTimeout(timeout);
      reject(err);
    });
    pythonProcess.once('exit', (code) => {
      clearTimeout(timeout);
      reject(new Error(`O backend Python encerrou (${code}). ${errors}`));
    });
  });
}

function stopPythonBackend() {
  // The Windows Store python launcher may have a different PID from the server.
  if (backendPid) {
    try {
      process.kill(backendPid);
    } catch (err) {
      if (err.code !== 'ESRCH') console.error('Failed to stop backend:', err);
    }
    backendPid = undefined;
  }
  if (pythonProcess) pythonProcess.kill();
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1120,
    height: 800,
    minWidth: 650,
    minHeight: 580,
    frame: false,
    backgroundColor: '#f3f5fc',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
    show: false,
  });

  mainWindow.loadFile(path.join(__dirname, 'index.html'));
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  mainWindow.webContents.on('will-navigate', (event) => event.preventDefault());
  mainWindow.once('ready-to-show', () => mainWindow.show());
}

app.whenReady().then(async () => {
  try {
    await startPythonBackend();
    createWindow();
  } catch (err) {
    dialog.showErrorBox('Não foi possível iniciar o Clipa', err.message);
    app.quit();
  }
});

app.on('before-quit', stopPythonBackend);
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (backendUrl && BrowserWindow.getAllWindows().length === 0) createWindow();
});

// ── IPC: controles da janela ──────────────────────────────────────────────
ipcMain.on('window-minimize', () => mainWindow.minimize());
ipcMain.on('window-maximize', () => {
  mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize();
});
ipcMain.on('window-close', () => mainWindow.close());

// ── IPC: utilitários ──────────────────────────────────────────────────────
ipcMain.handle('get-backend-url', () => backendUrl);
ipcMain.handle('get-backend-config', () => ({ url: backendUrl, token: backendToken }));
ipcMain.handle('open-external', (_, url) => {
  const parsed = new URL(url);
  if (parsed.protocol !== 'https:') throw new Error('Link externo inválido.');
  return shell.openExternal(parsed.href);
});
ipcMain.handle('open-folder', async (_, folder) => {
  if (
    typeof folder !== 'string' ||
    !path.isAbsolute(folder) ||
    !fs.statSync(folder).isDirectory()
  ) {
    throw new Error('Pasta inválida.');
  }
  const error = await shell.openPath(folder);
  if (error) throw new Error(error);
});
ipcMain.handle('choose-cookie-file', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    title: 'Selecionar arquivo de cookies',
    filters: [{ name: 'Cookies Netscape', extensions: ['txt'] }],
  });
  return result.canceled ? null : result.filePaths[0];
});

// ── IPC: seletor de pasta ─────────────────────────────────────────────────
ipcMain.handle('choose-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory', 'createDirectory'],
    title: 'Escolher pasta de destino',
  });
  if (result.canceled || !result.filePaths.length) return null;
  return result.filePaths[0];
});
