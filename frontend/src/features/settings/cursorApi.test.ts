import { getApiUrl } from "../../lib/api";
import type {
  CursorCapabilityReport,
  CursorDryRunResponse,
} from "../../domain/cursor";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CursorApiError,
  fetchCursorCapability,
  postCursorDryRun,
} from "./cursorApi";

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

  it("fetches models from /api/cursor/models", async () => {
    const report = {
      status: "available" as const,
      models: [
        { id: "composer-2.5", label: "composer-2.5" },
        { id: "gpt-5.2", label: "GPT-5.2" },
      ],
      defaultModel: "composer-2.5",
      message: "ok",
    };

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => report,
      }),
    );

    const { fetchCursorModels } = await import("./cursorApi");
    const result = await fetchCursorModels();
    expect(result.defaultModel).toBe("composer-2.5");
    expect(result.models.map((m) => m.id)).not.toContain("auto");
    expect(fetch).toHaveBeenCalledWith(`${getApiUrl()}/api/cursor/models`);
  });

  it("throws CursorApiError when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    await expect(fetchCursorCapability()).rejects.toBeInstanceOf(CursorApiError);
  });

  it("posts dry-run requests to /api/cursor/dry-run", async () => {
    const response: CursorDryRunResponse = {
      ok: true,
      errors: [],
      preview: {
        argv: ["agent", "--print", "--api-key", "***"],
        commandDisplay: "agent --print --api-key ***",
        stdin: "# Skill: x\n",
        stdinPreview: "# Skill: x\n",
        timeoutMs: 120000,
        workspace: "C:\\repo",
        executable: "agent",
      },
      confirmationRequired: true,
      confirmed: false,
      message: "review",
      spawned: false,
    };

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => response,
      }),
    );

    const result = await postCursorDryRun({
      request: {
        skillNodeId: "skill-1",
        skillLabel: "x",
        inputPayload: "y",
      },
      options: { apiKey: "sk-secret", confirmed: false },
    });

    expect(result).toEqual(response);
    expect(fetch).toHaveBeenCalledWith(
      `${getApiUrl()}/api/cursor/dry-run`,
      expect.objectContaining({ method: "POST" }),
    );
    const init = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toMatchObject({
      options: { apiKey: "sk-secret", confirmed: false },
    });
  });
});
