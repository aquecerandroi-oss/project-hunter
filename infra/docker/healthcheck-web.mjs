// PROJECT HUNTER — HEALTHCHECK probe for the web image.
//
// No dedicated `/health` route on the Next.js side (that's an api concern,
// see infra/docker/healthcheck.py) — a plain GET of `/` answering with any
// non-5xx status means the standalone server is up and rendering.
const port = process.env.PORT ?? "3000";

try {
  const response = await fetch(`http://127.0.0.1:${port}/`, {
    signal: AbortSignal.timeout(2000),
  });
  process.exit(response.status < 500 ? 0 : 1);
} catch {
  process.exit(1);
}
