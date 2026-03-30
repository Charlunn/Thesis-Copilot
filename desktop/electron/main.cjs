const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const BACKEND_PORT = 8000;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const isDev = process.argv.includes("--dev");

let mainWindow = null;
let backendProcess = null;
let backendState = {
  ready: false,
  dataRoot: "",
  workspaceRoot: "",
  backendUrl: BACKEND_URL,
};
let appConfig = {
  workspaceRoot: "",
  lastProjectId: "",
};

function getConfigPath() {
  return path.join(app.getPath("userData"), "app-config.json");
}

function loadAppConfig() {
  const configPath = getConfigPath();
  if (!fs.existsSync(configPath)) {
    return { workspaceRoot: "", lastProjectId: "" };
  }
  try {
    return {
      workspaceRoot: "",
      lastProjectId: "",
      ...JSON.parse(fs.readFileSync(configPath, "utf8")),
    };
  } catch (error) {
    return { workspaceRoot: "", lastProjectId: "" };
  }
}

function saveAppConfig(nextConfig) {
  appConfig = { ...appConfig, ...nextConfig };
  fs.mkdirSync(path.dirname(getConfigPath()), { recursive: true });
  fs.writeFileSync(getConfigPath(), JSON.stringify(appConfig, null, 2), "utf8");
}

function resolveBackendPaths(workspaceRoot) {
  const projectRoot = path.resolve(__dirname, "..", "..");
  const backendRoot = path.join(projectRoot, "backend");
  const backendSrc = path.join(backendRoot, "src");
  const dataRoot = workspaceRoot;
  return { projectRoot, backendRoot, backendSrc, dataRoot, workspaceRoot };
}

function getDefaultWorkspaceRoot() {
  return path.join(app.getPath("documents"), "QNU_Copilot_Workspace");
}

async function promptWorkspaceRoot() {
  const result = await dialog.showOpenDialog({
    title: "选择论文系统工作空间",
    buttonLabel: "使用这个文件夹",
    defaultPath: appConfig.workspaceRoot || getDefaultWorkspaceRoot(),
    properties: ["openDirectory", "createDirectory", "promptToCreate"],
  });
  if (result.canceled || !result.filePaths.length) {
    const fallbackPath = appConfig.workspaceRoot || getDefaultWorkspaceRoot();
    fs.mkdirSync(fallbackPath, { recursive: true });
    saveAppConfig({ workspaceRoot: fallbackPath, lastProjectId: "" });
    return fallbackPath;
  }
  const selected = result.filePaths[0];
  fs.mkdirSync(selected, { recursive: true });
  saveAppConfig({ workspaceRoot: selected, lastProjectId: "" });
  return selected;
}

async function ensureWorkspaceRoot() {
  appConfig = loadAppConfig();
  if (appConfig.workspaceRoot && fs.existsSync(appConfig.workspaceRoot)) {
    return appConfig.workspaceRoot;
  }
  return promptWorkspaceRoot();
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1460,
    height: 980,
    minWidth: 1220,
    minHeight: 840,
    backgroundColor: "#e9e0d2",
    title: "QNU Thesis Copilot",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  if (isDev) {
    mainWindow.loadURL("http://127.0.0.1:5173");
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

async function waitForBackend(timeoutMs = 15000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(`${BACKEND_URL}/health`);
      if (response.ok) {
        backendState.ready = true;
        return;
      }
    } catch (error) {
      // keep polling
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("Backend did not become ready within the expected time.");
}

async function startBackend(workspaceRoot) {
  const { backendRoot, backendSrc, dataRoot } = resolveBackendPaths(workspaceRoot);
  backendState.dataRoot = dataRoot;
  backendState.workspaceRoot = workspaceRoot;

  const pythonExecutable = process.env.PYTHON || "python";
  const pythonPath = [backendSrc, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter);

  backendProcess = spawn(pythonExecutable, ["-m", "qnu_copilot.main"], {
    cwd: backendRoot,
    env: {
      ...process.env,
      PYTHONPATH: pythonPath,
      QNU_COPILOT_DATA_ROOT: dataRoot,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  backendProcess.stdout.on("data", (chunk) => {
    process.stdout.write(`[backend] ${chunk}`);
  });

  backendProcess.stderr.on("data", (chunk) => {
    process.stderr.write(`[backend] ${chunk}`);
  });

  backendProcess.on("exit", (code) => {
    backendState.ready = false;
    if (code !== 0) {
      console.error(`Backend exited with code ${code}`);
    }
  });

  await waitForBackend();
}

function stopBackend() {
  if (!backendProcess || backendProcess.killed) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const processRef = backendProcess;
    backendProcess = null;
    processRef.once("exit", () => {
      resolve();
    });
    processRef.kill();
    setTimeout(resolve, 1500);
  });
}

async function restartBackend(workspaceRoot) {
  await stopBackend();
  backendState.ready = false;
  await startBackend(workspaceRoot);
}

function serializeAppInfo() {
  return {
    ...backendState,
    lastProjectId: appConfig.lastProjectId || "",
    isDev,
  };
}

function installIpcHandlers() {
  ipcMain.handle("app:get-info", async () => serializeAppInfo());
  ipcMain.handle("app:set-last-project", async (_, projectId = "") => {
    saveAppConfig({ lastProjectId: projectId || "" });
    return true;
  });

  ipcMain.handle("dialog:pick-pdf-files", async (_, multiple = false) => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: multiple ? "选择多个 PDF 文件" : "选择 PDF 文件",
      properties: multiple ? ["openFile", "multiSelections"] : ["openFile"],
      filters: [{ name: "PDF", extensions: ["pdf"] }],
    });
    return result.canceled ? [] : result.filePaths;
  });

  ipcMain.handle("shell:show-item-in-folder", async (_, targetPath) => {
    if (fs.existsSync(targetPath) && fs.statSync(targetPath).isDirectory()) {
      await shell.openPath(targetPath);
      return true;
    }
    shell.showItemInFolder(targetPath);
    return true;
  });

  ipcMain.handle("workspace:choose-root", async () => {
    const nextWorkspaceRoot = await promptWorkspaceRoot();
    await restartBackend(nextWorkspaceRoot);
    return serializeAppInfo();
  });
}

app.whenReady().then(async () => {
  try {
    installIpcHandlers();
    const workspaceRoot = await ensureWorkspaceRoot();
    await startBackend(workspaceRoot);
    createWindow();
  } catch (error) {
    console.error(error);
    dialog.showErrorBox(
      "QNU Thesis Copilot 启动失败",
      error instanceof Error ? error.message : String(error),
    );
    app.quit();
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("before-quit", () => {
  void stopBackend();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
