/**
 * IDE Integration Extension for pi
 *
 * Connects pi to a running IDE (VS Code, Antigravity, …) so the LLM knows
 * which file and line range the user is looking at.  Pi does NOT read file
 * contents automatically — it only learns the file path and optional
 * selection range, then decides whether to `read` based on the user's prompt.
 *
 * Usage:
 *   /ide          – scan for running IDEs and connect
 *
 * The extension injects an [IDE Context] message into the conversation via
 * the `before_agent_start` event so the model can decide whether to read the
 * file.
 */

import * as net from "node:net";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import type { ExtensionAPI, ExtensionContext } from "@mariozechner/pi-coding-agent";
import { getSettingsListTheme } from "@mariozechner/pi-coding-agent";
import { Container, type SettingItem, SettingsList } from "@mariozechner/pi-tui";
import type { IdeContext, IdeHello, IdeMessage } from "./protocol.ts";
import { IDE_SOCK_DIR } from "./protocol.ts";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let socket: net.Socket | null = null;
let currentIde: string | null = null;
let latestContext: IdeContext | null = null;

/** Buffer for incomplete lines arriving on the socket. */
let recvBuffer = "";

/** Stored so socket data handlers can update the status bar. */
let currentCtx: ExtensionContext | undefined;

// ---------------------------------------------------------------------------
// Settings (persisted to ~/.pi/agent/ide.json)
// ---------------------------------------------------------------------------

interface IdeSettings {
  autoConnect: boolean;
}

const DEFAULT_SETTINGS: IdeSettings = {
  autoConnect: false,
};

const SETTINGS_PATH = path.join(os.homedir(), ".pi", "agent", "ide.json");

function loadSettings(): IdeSettings {
  try {
    const raw = fs.readFileSync(SETTINGS_PATH, "utf-8");
    const parsed = JSON.parse(raw);
    return { ...DEFAULT_SETTINGS, ...parsed };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

function saveSettings(settings: IdeSettings): void {
  const dir = path.dirname(SETTINGS_PATH);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(SETTINGS_PATH, JSON.stringify(settings, null, 2) + "\n");
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function sockDir(cwd: string): string {
  return path.join(cwd, ".pi", IDE_SOCK_DIR);
}

/** List absolute paths of all `*.sock` files inside `.pi/ide/`. */
function listSockFiles(cwd: string): string[] {
  const dir = sockDir(cwd);
  try {
    return fs
      .readdirSync(dir)
      .filter((f) => f.endsWith(".sock"))
      .map((f) => path.join(dir, f));
  } catch {
    return [];
  }
}

/** Derive a human-readable IDE name from a socket path. */
function ideNameFromSock(sockPath: string): string {
  return path.basename(sockPath, ".sock");
}

/**
 * Test whether a Unix socket is alive (something is listening).
 * Returns `true` if we can connect within 500 ms.
 */
async function isSocketAlive(sockPath: string): Promise<boolean> {
  return new Promise((resolve) => {
    const s = net.createConnection(sockPath);
    const timer = setTimeout(() => {
      s.destroy();
      resolve(false);
    }, 500);
    s.on("connect", () => {
      clearTimeout(timer);
      s.destroy();
      resolve(true);
    });
    s.on("error", () => {
      clearTimeout(timer);
      resolve(false);
    });
  });
}

/** Remove a stale (dead) socket file. */
function removeStaleSocket(sockPath: string): void {
  try {
    fs.unlinkSync(sockPath);
  } catch {
    /* already gone */
  }
}

// ---------------------------------------------------------------------------
// Status bar
// ---------------------------------------------------------------------------

function updateStatus(): void {
  if (!currentCtx) return;
  const theme = currentCtx.ui.theme;

  if (!currentIde) {
    currentCtx.ui.setStatus("ide", undefined);
    return;
  }

  let text = theme.fg("accent", currentIde);
  if (latestContext?.file) {
    text += theme.fg("dim", " | ") + theme.fg("dim", latestContext.file);
    if (latestContext.startLine != null && latestContext.endLine != null) {
      text += theme.fg("dim", ":") + theme.fg("dim", `${latestContext.startLine}-${latestContext.endLine}`);
    }
  }

  currentCtx.ui.setStatus("ide", text);
}

// ---------------------------------------------------------------------------
// Connection management
// ---------------------------------------------------------------------------

function disconnect(): void {
  if (socket) {
    socket.destroy();
    socket = null;
  }
  currentIde = null;
  latestContext = null;
  recvBuffer = "";
  updateStatus();
}

function handleMessage(msg: IdeMessage): void {
  switch (msg.type) {
    case "hello": {
      const hello = msg as IdeHello;
      currentIde = hello.ide;
      updateStatus();
      break;
    }
    case "context": {
      latestContext = msg as IdeContext;
      updateStatus();
      break;
    }
    default:
      // Unknown message type – ignore for forward compat.
      break;
  }
}

function connectTo(sockPath: string): Promise<void> {
  return new Promise((resolve, reject) => {
    // Disconnect any existing connection first.
    disconnect();

    const s = net.createConnection(sockPath);
    socket = s;
    let connected = false;

    s.on("connect", () => {
      connected = true;
      resolve();
    });

    s.on("data", (chunk: Buffer) => {
      recvBuffer += chunk.toString();
      // Process complete lines.
      let nlIdx: number;
      while ((nlIdx = recvBuffer.indexOf("\n")) !== -1) {
        const line = recvBuffer.slice(0, nlIdx).trim();
        recvBuffer = recvBuffer.slice(nlIdx + 1);
        if (!line) continue;
        try {
          const msg: IdeMessage = JSON.parse(line);
          handleMessage(msg);
        } catch {
          // Malformed JSON – skip.
        }
      }
    });

    s.on("close", () => {
      if (socket === s) {
        // Only clear state if this is still the active socket.
        currentIde = null;
        latestContext = null;
        recvBuffer = "";
        updateStatus();
        socket = null;
      }
    });

    s.on("error", (err) => {
      if (socket === s) {
        disconnect();
      }
      // Only reject if we never connected; post-connect errors are
      // handled by the 'close' handler above.
      if (!connected) {
        reject(err);
      }
    });
  });
}

// ---------------------------------------------------------------------------
// Scan & auto-connect (shared by /ide command and auto-connect)
// ---------------------------------------------------------------------------

async function findLiveSockets(cwd: string): Promise<{ name: string; path: string }[]> {
  const socks = listSockFiles(cwd);
  const live: { name: string; path: string }[] = [];
  for (const sp of socks) {
    const alive = await isSocketAlive(sp);
    if (alive) {
      live.push({ name: ideNameFromSock(sp), path: sp });
    } else {
      removeStaleSocket(sp);
    }
  }
  return live;
}

async function autoConnect(cwd: string): Promise<void> {
  if (currentIde) return; // already connected
  const live = await findLiveSockets(cwd);
  if (live.length === 0) return;
  // Connect to the first live socket silently.
  try {
    await connectTo(live[0].path);
  } catch {
    // Silent failure — user can always /ide manually.
  }
}

// ---------------------------------------------------------------------------
// Extension entry point
// ---------------------------------------------------------------------------

export default function ide(pi: ExtensionAPI) {

  let settings = loadSettings();

  // -------------------------------------------------------------------
  // --ide-auto-connect flag (overrides settings for this invocation)
  // -------------------------------------------------------------------

  pi.registerFlag("ide-auto-connect", {
    description: "Auto-connect to a running IDE on startup",
    type: "boolean",
    default: false,
  });

  // -------------------------------------------------------------------
  // /ide-settings command
  // -------------------------------------------------------------------

  pi.registerCommand("ide-settings", {
    description: "Configure IDE integration settings",
    handler: async (_args, ctx) => {
      // Reload in case the file was edited externally.
      settings = loadSettings();

      await ctx.ui.custom((_tui, theme, _kb, done) => {
        const items: SettingItem[] = [
          {
            id: "autoConnect",
            label: "Auto-connect on startup",
            currentValue: settings.autoConnect ? "on" : "off",
            values: ["on", "off"],
          },
        ];

        const container = new Container();
        container.addChild(
          new (class {
            render() {
              return [theme.fg("accent", theme.bold("IDE Settings")), ""];
            }
            invalidate() {}
          })(),
        );

        const list = new SettingsList(
          items,
          Math.min(items.length + 2, 15),
          getSettingsListTheme(),
          (id, newValue) => {
            if (id === "autoConnect") {
              settings.autoConnect = newValue === "on";
            }
            saveSettings(settings);
          },
          () => done(undefined),
        );
        container.addChild(list);

        return {
          render: (w: number) => container.render(w),
          invalidate: () => container.invalidate(),
          handleInput: (data: string) => {
            list.handleInput?.(data);
            _tui.requestRender();
          },
        };
      });
    },
  });

  // -------------------------------------------------------------------
  // /ide command
  // -------------------------------------------------------------------

  pi.registerCommand("ide", {
    description: "Connect to a running IDE (VS Code, Antigravity, …)",
    handler: async (_args, ctx) => {
      const live = await findLiveSockets(ctx.cwd);

      if (live.length === 0) {
        ctx.ui.notify(
          "No IDE found. Start a supported IDE with the pi extension installed.",
          "warning",
        );
        return;
      }

      let chosen: { name: string; path: string } | null = null;

      if (live.length === 1 && !currentIde) {
        // Only one IDE available and not currently connected → auto-connect.
        chosen = live[0];
      } else {
        // Build selection list.
        const items = live.map((l) => {
          const marker = l.name === currentIde ? " (connected)" : "";
          return `${l.name}${marker}`;
        });
        items.push("None (disconnect)");

        const sel = await ctx.ui.select("Connect to IDE", items);
        if (!sel) return; // Cancelled.

        if (sel.startsWith("None")) {
          disconnect();
          ctx.ui.notify("Disconnected from IDE", "info");
          return;
        }

        const rawName = sel.replace(" (connected)", "");
        chosen = live.find((l) => l.name === rawName) ?? null;
      }

      if (!chosen) return;

      try {
        await connectTo(chosen.path);
        ctx.ui.notify(`Connected to ${chosen.name}`, "success");
      } catch {
        ctx.ui.notify(`Failed to connect to ${chosen.name}`, "error");
      }
    },
  });

  // -------------------------------------------------------------------
  // Context injection – before each agent turn
  // -------------------------------------------------------------------

  pi.on("before_agent_start", async (_event, _ctx) => {
    if (!latestContext || !latestContext.file) return;

    let content = `[IDE Context]\nActive file: ${latestContext.file}`;
    if (latestContext.startLine != null && latestContext.endLine != null) {
      content += `\nSelection: lines ${latestContext.startLine}-${latestContext.endLine}`;
    }

    return {
      message: {
        customType: "ide-context",
        content,
        display: false, // visible in status bar; no need to clutter the chat
      },
    };
  });

  // -------------------------------------------------------------------
  // Store ctx on session start so socket handlers can update status.
  // -------------------------------------------------------------------

  pi.on("session_start", async (_event, ctx) => {
    currentCtx = ctx;
    updateStatus();

    // Auto-connect if enabled via flag or settings.
    const flagSet = pi.getFlag("ide-auto-connect");
    if (flagSet || settings.autoConnect) {
      await autoConnect(ctx.cwd);
    }
  });

  // -------------------------------------------------------------------
  // Cleanup on shutdown
  // -------------------------------------------------------------------

  pi.on("session_shutdown", async () => {
    disconnect();
    currentCtx = undefined;
  });
}
