const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("hydroBuddy", {
    ready: () => ipcRenderer.invoke("hydro-ready"),
    onReminder: (callback) => ipcRenderer.on("reminder", (_event, text) => callback(text)),
    onPetState: (callback) => ipcRenderer.on("pet-state", (_event, state) => callback(state)),
    onState: (callback) => ipcRenderer.on("hydro-state", (_event, state) => callback(state))
});
