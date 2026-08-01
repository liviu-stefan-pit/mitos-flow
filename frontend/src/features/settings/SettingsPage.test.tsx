import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CursorCapabilityReport } from "../../domain/cursor";
import { SettingsPage } from "./SettingsPage";

vi.mock("./cursorApi", () => ({
  fetchCursorCapability: vi.fn(),
  CursorApiError: class CursorApiError extends Error {
    status?: number;
    constructor(message: string, status?: number) {
      super(message);
      this.name = "CursorApiError";
      this.status = status;
    }
  },
}));

import { fetchCursorCapability } from "./cursorApi";

const mockedFetch = vi.mocked(fetchCursorCapability);

const availableReport: CursorCapabilityReport = {
  status: "available",
  message: "Cursor CLI available (version 1.2.3).",
  executable: "C:\\tools\\agent.exe",
  version: "1.2.3",
  versionRaw: "1.2.3",
  minimumVersion: "0.1.0",
  helpExcerpt: "--print --workspace",
  features: {
    printMode: true,
    outputFormat: true,
    workspace: true,
    force: false,
    model: true,
    listModels: false,
    trust: true,
    apiKey: false,
    streamPartialOutput: false,
  },
};

const absentReport: CursorCapabilityReport = {
  ...availableReport,
  status: "absent",
  message: "Cursor CLI not found.",
  executable: null,
  version: null,
  versionRaw: null,
  helpExcerpt: null,
  features: {
    printMode: false,
    outputFormat: false,
    workspace: false,
    force: false,
    model: false,
    listModels: false,
    trust: false,
    apiKey: false,
    streamPartialOutput: false,
  },
};

describe("SettingsPage", () => {
  beforeEach(() => {
    mockedFetch.mockReset();
  });

  it("shows available Cursor CLI status from the probe API", async () => {
    mockedFetch.mockResolvedValue(availableReport);
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("cursor-cli-status-value")).toHaveTextContent(
        "Available",
      );
    });

    expect(screen.getByTestId("cursor-cli-version")).toHaveTextContent("1.2.3");
    expect(screen.getByTestId("cursor-cli-executable")).toHaveTextContent(
      "C:\\tools\\agent.exe",
    );
    expect(screen.getByTestId("cursor-feature-printMode")).toHaveClass(
      "feature-on",
    );
    expect(screen.getByTestId("cursor-feature-force")).toHaveClass(
      "feature-off",
    );
  });

  it("shows absent status when CLI is missing", async () => {
    mockedFetch.mockResolvedValue(absentReport);
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("cursor-cli-status-value")).toHaveTextContent(
        "Not found",
      );
    });
    expect(screen.getByTestId("cursor-cli-message")).toHaveTextContent(
      "not found",
    );
  });

  it("shows unsupported version status", async () => {
    mockedFetch.mockResolvedValue({
      ...availableReport,
      status: "unsupported_version",
      message: "Cursor CLI version 0.0.1 is below the minimum supported version 0.1.0.",
      version: "0.0.1",
    });
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("cursor-cli-status-value")).toHaveTextContent(
        "Unsupported version",
      );
    });
  });

  it("refreshes the probe on demand", async () => {
    mockedFetch
      .mockResolvedValueOnce(absentReport)
      .mockResolvedValueOnce(availableReport);

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByTestId("cursor-cli-status-value")).toHaveTextContent(
        "Not found",
      );
    });

    fireEvent.click(screen.getByTestId("cursor-cli-refresh"));

    await waitFor(() => {
      expect(screen.getByTestId("cursor-cli-status-value")).toHaveTextContent(
        "Available",
      );
    });
    expect(mockedFetch).toHaveBeenCalledTimes(2);
  });
});
