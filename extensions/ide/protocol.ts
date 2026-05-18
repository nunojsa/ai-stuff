/**
 * IDE ↔ Pi protocol types.
 *
 * All messages are newline-delimited JSON (\n terminated) over a Unix domain
 * socket located at <project-root>/.pi/ide/<ide-name>.sock.
 */

// ---------------------------------------------------------------------------
// IDE → Pi
// ---------------------------------------------------------------------------

/** Sent once by the IDE immediately after a client connects. */
export interface IdeHello {
  type: "hello";
  /** Display name – matches the socket filename without `.sock`. */
  ide: string;
  /** Protocol version for future compatibility. */
  version: string;
}

/**
 * Pushed by the IDE whenever the active editor or selection changes
 * (debounced ~200 ms).
 */
export interface IdeContext {
  type: "context";
  /** Path relative to project root.  `null` / omitted when no file is focused. */
  file?: string | null;
  /** 1-indexed inclusive start line of the selection. Omitted when no selection. */
  startLine?: number;
  /** 1-indexed inclusive end line of the selection. Omitted when no selection. */
  endLine?: number;
}

/** Union of every message the IDE can send to pi. */
export type IdeMessage = IdeHello | IdeContext;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Current protocol version string. */
export const PROTOCOL_VERSION = "1.0.0";

/** Name of the directory under `.pi/` that holds IDE sockets. */
export const IDE_SOCK_DIR = "ide";
