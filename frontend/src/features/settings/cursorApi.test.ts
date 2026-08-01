import { getApiUrl } from "../../lib/api";
import type { CursorCapabilityReport } from "../../domain/cursor";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CursorApiError, fetchCursorCapability } from "./cursorApi";

describe("cursorApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("fetches capability report from /api/cursor/capability", async () => {
    const report: CursorCapabilityReport = {
      status: "available",
      message: "ok",
      executable: "/bin/agent",
      version: "2.0.0",
      versionRaw: "2.0.0",
      minimumVersion: "0.1.0",
      helpExcerpt: "--print",
      features: {
        printMode: true,
        outputFormat: false,
        workspace: true,
        force: false,
        model: false,
        listModels: false,
        trust: false,
        apiKey: false,
        streamPartialOutput: false,
      },
    };

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => report,
      }),
    );

    const result = await fetchCursorCapability();
    expect(result).toEqual(report);
    expect(fetch).toHaveBeenCalledWith(`${getApiUrl()}/api/cursor/capability`);
  });

  it("throws CursorApiError when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    await expect(fetchCursorCapability()).rejects.toBeInstanceOf(CursorApiError);
  });
});
