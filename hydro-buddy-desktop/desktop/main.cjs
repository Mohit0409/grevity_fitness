const { app, BrowserWindow, Menu, Notification, ipcMain, screen } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const REMINDER_TEXT = "Get up, stretch your body, and drink water.";
const INTERVAL_MS = 30 * 60 * 1000;
const SETTINGS_FILE = () => path.join(app.getPath("userData"), "hydro-buddy-settings.json");
const AUTOSTART_FILE = path.join(os.homedir(), ".config", "autostart", "hydro-buddy.desktop");

let mainWindow = null;
let reminderTimer = null;
let restoreTimer = null;
let settings = {
    remindersRunning: true,
    voiceMuted: false,
    bounds: null
};

app.disableHardwareAcceleration();
app.commandLine.appendSwitch("disable-gpu");
app.commandLine.appendSwitch("disable-features", "Vulkan");

function readSettings() {
    try {
        settings = { ...settings, ...JSON.parse(fs.readFileSync(SETTINGS_FILE(), "utf8")) };
    } catch {
        writeSettings();
    }
}

function writeSettings() {
    fs.mkdirSync(path.dirname(SETTINGS_FILE()), { recursive: true });
    fs.writeFileSync(SETTINGS_FILE(), `${JSON.stringify(settings, null, 2)}\n`);
}

function currentLaunchCommand() {
    if (app.isPackaged) return `"${process.execPath}"`;
    return `"${process.execPath}" "${__filename}"`;
}

function enableUbuntuAutostart() {
    const desktopEntry = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        "Name=Hydro Buddy",
        "Comment=Floating hydration and stretch reminder pet",
        `Exec=${currentLaunchCommand()}`,
        "Terminal=false",
        "X-GNOME-Autostart-enabled=true",
        "Categories=Utility;",
        ""
    ].join("\n");

    fs.mkdirSync(path.dirname(AUTOSTART_FILE), { recursive: true });
    fs.writeFileSync(AUTOSTART_FILE, desktopEntry, { mode: 0o644 });
}

function keepOnTop(window) {
    window.setAlwaysOnTop(true, "screen-saver");
    window.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    window.setSkipTaskbar(false);
}

function createWindow() {
    const display = screen.getPrimaryDisplay();
    const defaultBounds = {
        width: 70,
        height: 90,
        x: display.workArea.x + display.workArea.width - 120,
        y: display.workArea.y + 80
    };
    const safeBounds = normalizeBounds(settings.bounds, defaultBounds, display.workArea);

    mainWindow = new BrowserWindow({
        ...safeBounds,
        minWidth: 70,
        minHeight: 90,
        frame: false,
        transparent: true,
        backgroundColor: "#00000000",
        hasShadow: false,
        resizable: false,
        movable: true,
        fullscreenable: false,
        alwaysOnTop: true,
        title: "Hydro Buddy",
        webPreferences: {
            preload: path.join(__dirname, "preload.cjs"),
            contextIsolation: true,
            nodeIntegration: false
        }
    });

    keepOnTop(mainWindow);
    mainWindow.loadFile(path.join(__dirname, "renderer.html"));
    mainWindow.webContents.on("context-menu", () => showContextMenu());
    mainWindow.on("moved", saveWindowBounds);
    mainWindow.on("resized", saveWindowBounds);
    mainWindow.on("blur", () => mainWindow && keepOnTop(mainWindow));
}

function normalizeBounds(bounds, fallback, workArea) {
    if (!bounds || typeof bounds !== "object") return fallback;
    const width = Number(bounds.width);
    const height = Number(bounds.height);
    const x = Number(bounds.x);
    const y = Number(bounds.y);
    const tooLarge = width > 180 || height > 220;
    const tooSmall = width < 60 || height < 80;
    const offscreen = x + width < workArea.x || y + height < workArea.y
        || x > workArea.x + workArea.width || y > workArea.y + workArea.height;
    if ([width, height, x, y].some((value) => !Number.isFinite(value)) || tooLarge || tooSmall || offscreen) {
        settings.bounds = fallback;
        writeSettings();
        return fallback;
    }
    return { width, height, x, y };
}

function saveWindowBounds() {
    if (!mainWindow) return;
    settings.bounds = mainWindow.getBounds();
    writeSettings();
}

function showContextMenu() {
    const menu = Menu.buildFromTemplate([
        {
            label: "Start Reminder",
            enabled: !settings.remindersRunning,
            click: startReminders
        },
        {
            label: "Stop Reminder",
            enabled: settings.remindersRunning,
            click: stopReminders
        },
        { type: "separator" },
        {
            label: "Test Reminder",
            click: () => runReminder({ test: true })
        },
        {
            label: "Mute Voice",
            type: "checkbox",
            checked: settings.voiceMuted,
            click: (item) => {
                settings.voiceMuted = item.checked;
                writeSettings();
                sendState();
            }
        },
        { type: "separator" },
        {
            label: "Exit",
            click: () => app.quit()
        }
    ]);

    menu.popup({ window: mainWindow });
}

function sendState() {
    if (!mainWindow) return;
    mainWindow.webContents.send("hydro-state", {
        remindersRunning: settings.remindersRunning,
        voiceMuted: settings.voiceMuted
    });
}

function setPetState(state, restore = true) {
    if (!mainWindow) return;
    mainWindow.webContents.send("pet-state", state);
    clearTimeout(restoreTimer);
    if (restore) {
        restoreTimer = setTimeout(() => {
            mainWindow?.webContents.send("pet-state", settings.remindersRunning ? "running" : "idle");
        }, 4200);
    }
}

function notify() {
    if (!Notification.isSupported()) return;
    new Notification({
        title: "Hydro Buddy",
        body: REMINDER_TEXT,
        silent: false
    }).show();
}

function speakWithLinuxTts(text) {
    if (settings.voiceMuted) return Promise.resolve(false);
    const candidates = [
        { command: "spd-say", args: [text] },
        { command: "espeak", args: [text] }
    ];

    const tryNext = (index) => new Promise((resolve) => {
        if (index >= candidates.length) {
            resolve(false);
            return;
        }
        const candidate = candidates[index];
        const child = spawn(candidate.command, candidate.args, { stdio: "ignore" });
        child.on("spawn", () => {
            child.unref();
            resolve(true);
        });
        child.on("error", async () => {
            resolve(await tryNext(index + 1));
        });
    });

    return tryNext(0);
}

async function runReminder({ test = false } = {}) {
    if (!settings.remindersRunning && !test) return;
    notify();
    const spokeWithLinuxTts = await speakWithLinuxTts(REMINDER_TEXT);
    mainWindow?.webContents.send("reminder", {
        text: REMINDER_TEXT,
        speakInRenderer: !spokeWithLinuxTts
    });
    setPetState("waiting", true);
}

function scheduleNextReminder() {
    clearTimeout(reminderTimer);
    if (!settings.remindersRunning) return;
    reminderTimer = setTimeout(() => {
        runReminder();
        scheduleNextReminder();
    }, INTERVAL_MS);
}

function startReminders() {
    settings.remindersRunning = true;
    writeSettings();
    scheduleNextReminder();
    setPetState("running", false);
    sendState();
}

function stopReminders() {
    settings.remindersRunning = false;
    writeSettings();
    clearTimeout(reminderTimer);
    setPetState("idle", false);
    sendState();
}

ipcMain.handle("hydro-ready", () => {
    sendState();
    setPetState(settings.remindersRunning ? "running" : "idle", false);
});

app.whenReady().then(() => {
    app.setName("Hydro Buddy");
    readSettings();
    enableUbuntuAutostart();
    createWindow();
    scheduleNextReminder();
});

app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

app.on("before-quit", () => {
    clearTimeout(reminderTimer);
    clearTimeout(restoreTimer);
    saveWindowBounds();
});
