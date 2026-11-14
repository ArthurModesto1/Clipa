const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electron', {
  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  close: () => ipcRenderer.send('window-close'),
  getBackendUrl: () => ipcRenderer.invoke('get-backend-url'),
  getBackendConfig: () => ipcRenderer.invoke('get-backend-config'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  chooseFolder: () => ipcRenderer.invoke('choose-folder'),
  chooseCookieFile: () => ipcRenderer.invoke('choose-cookie-file'),
  openFolder: (folder) => ipcRenderer.invoke('open-folder', folder),
});
