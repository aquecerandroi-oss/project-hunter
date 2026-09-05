import { expect, test } from "@playwright/test";

/**
 * `apps/api` base URL -- not `use.baseURL` (that's `apps/web`). Same default
 * host:port as `infra/docker/docker-compose.yml`'s `api` service and
 * `docs/plans/M0.md`'s prerequisites (`curl -s localhost:8000/health`).
 */
const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";

let apiReachable = false;

test.beforeAll(async ({ request }) => {
  try {
    const response = await request.get(`${API_URL}/health`, { timeout: 3_000 });
    apiReachable = response.ok();
  } catch {
    apiReachable = false;
  }
});

test.describe("apps/api health (docker compose stack)", () => {
  test("GET /health is 200", async ({ request }) => {
    test.skip(!apiReachable, `apps/api not reachable at ${API_URL} -- start it with docker compose -f infra/docker/docker-compose.yml up -d`);
    const response = await request.get(`${API_URL}/health`);
    expect(response.status()).toBe(200);
  });

  test("GET /ready is 200", async ({ request }) => {
    test.skip(!apiReachable, `apps/api not reachable at ${API_URL} -- start it with docker compose -f infra/docker/docker-compose.yml up -d`);
    const response = await request.get(`${API_URL}/ready`);
    expect(response.status()).toBe(200);
  });
});
