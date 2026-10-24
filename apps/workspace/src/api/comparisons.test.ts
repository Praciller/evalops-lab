import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createComparison, getBaseline, listComparisonFailures, NonComparableError, setBaseline,
} from "./client";

const WS = `ws-${"1".repeat(32)}`;
const RUN = `run-${"a".repeat(32)}`;
const CANDIDATE = `run-${"b".repeat(32)}`;
const COMPARISON = `comparison-${"c".repeat(32)}`;
const SHA = "e".repeat(64);

function response(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    clone: () => response(status, body),
  } as Response;
}

afterEach(() => vi.unstubAllGlobals());

describe("private comparison API contracts", () => {
  it("keeps canonical mode as the default and never silently creates exploratory results", async () => {
    const mocked = vi.fn().mockResolvedValue(response(409, {
      error: {
        code: "non_comparable", message: "not compatible", field: null, retryable: false,
      },
      compatibility: {
        status: "NON_COMPARABLE",
        reasons: [{ field: "top_k", baseline: "1", candidate: "2" }],
      },
    }));
    vi.stubGlobal("fetch", mocked);
    await expect(createComparison(WS, CANDIDATE)).rejects.toBeInstanceOf(NonComparableError);
    expect(mocked).toHaveBeenCalledTimes(1);
    expect(JSON.parse(mocked.mock.calls[0][1].body)).toEqual({
      candidate_run_id: CANDIDATE, mode: "CANONICAL",
    });
  });

  it("creates exploratory mode only on an explicit separate request", async () => {
    const record = {
      schema_version: "workspace-comparison-v1",
      comparison_id: COMPARISON,
      workspace_id: WS,
      mode: "EXPLORATORY_ONLY",
      compatibility: { status: "NON_COMPARABLE", reasons: [] },
      baseline_run_id: RUN,
      baseline_result_sha256: SHA,
      candidate_run_id: CANDIDATE,
      candidate_result_sha256: SHA,
      policy_version: "workspace-retrieval-regression-v1",
      regression_report: { passed: false, comparisons: [] },
      created_at: "2026-10-24T00:00:00Z",
    };
    const mocked = vi.fn().mockResolvedValue(response(201, record));
    vi.stubGlobal("fetch", mocked);
    expect((await createComparison(WS, CANDIDATE, "EXPLORATORY_ONLY")).mode).toBe("EXPLORATORY_ONLY");
    expect(JSON.parse(mocked.mock.calls[0][1].body).mode).toBe("EXPLORATORY_ONLY");
  });

  it("requires an explicit replace flag when updating a persisted baseline", async () => {
    const payload = { baseline: {
      run_id: RUN, result_sha256: SHA, pinned_at: "2026-10-24T00:00:00Z",
    } };
    const mocked = vi.fn().mockResolvedValue(response(200, payload));
    vi.stubGlobal("fetch", mocked);
    expect((await getBaseline(WS))?.run_id).toBe(RUN);
    await setBaseline(WS, RUN, true);
    expect(mocked.mock.calls[1][1].method).toBe("PUT");
    expect(JSON.parse(mocked.mock.calls[1][1].body)).toEqual({
      run_id: RUN, confirm_replace: true,
    });
  });

  it("sends only typed server-side failure filters, never evaluator rules", async () => {
    const mocked = vi.fn().mockResolvedValue(response(200, {
      comparison_id: COMPARISON, total_count: 0, transitions: [],
    }));
    vi.stubGlobal("fetch", mocked);
    const data = await listComparisonFailures(WS, COMPARISON, {
      transition: "REGRESSED", category: "RETRIEVAL_MISS", queryId: "q/1", exact: false,
    });
    expect(data.total_count).toBe(0);
    const url = String(mocked.mock.calls[0][0]);
    expect(url).toContain("transition=REGRESSED");
    expect(url).toContain("category=RETRIEVAL_MISS");
    expect(url).toContain("query_id=q%2F1");
    expect(url).toContain("exact=false");
    expect(url).not.toContain("metric_rule");
  });

  it("rejects invalid API content rather than using unverified comparison evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(201, { mode: "CANONICAL" })));
    await expect(createComparison(WS, CANDIDATE)).rejects.toThrow();
  });
});
