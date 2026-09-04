/**
 * The only file in apps/web allowed to call `console.*` directly
 * (`quality/no-direct-console` in packages/config/eslint carves out this
 * exact path). Every other module must import `logger` from here instead.
 *
 * Output is a single JSON line: `{ level, msg, ts, ...context }`. `debug` is
 * a no-op in production so verbose client logs never ship to real users.
 */

export type LogLevel = "debug" | "info" | "warn" | "error";

export interface LogContext {
  [key: string]: unknown;
}

interface LogEntry extends LogContext {
  level: LogLevel;
  msg: string;
  ts: string;
}

function write(level: LogLevel, msg: string, context: LogContext): void {
  const entry: LogEntry = { level, msg, ts: new Date().toISOString(), ...context };
  const line = JSON.stringify(entry);
  if (level === "error") {
    console.error(line);
  } else if (level === "warn") {
    console.warn(line);
  } else {
    console.log(line);
  }
}

export const logger = {
  debug(msg: string, context: LogContext = {}): void {
    if (process.env.NODE_ENV === "production") return;
    write("debug", msg, context);
  },
  info(msg: string, context: LogContext = {}): void {
    write("info", msg, context);
  },
  warn(msg: string, context: LogContext = {}): void {
    write("warn", msg, context);
  },
  error(msg: string, context: LogContext = {}): void {
    write("error", msg, context);
  },
};
