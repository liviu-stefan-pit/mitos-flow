import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { App } from "./App";

vi.mock("./features/health/healthApi", () => ({
  checkBackendHealth: vi.fn(),
}));

vi.mock("./features/library/libraryApi", () => ({
  listLibraryAssets: vi.fn().mockReturnValue(new Promise(() => {})),
  previewLibraryFile: vi.fn(),
  importLibraryFile: vi.fn(),
  importLibraryBatch: vi.fn(),
  getLibraryAsset: vi.fn(),
  isLibraryMarkdownFilename: (name: string) =>
    /\.(md|mdc|markdown)$/i.test(name),
  LibraryApiError: class LibraryApiError extends Error {
    status?: number;
    constructor(message: string, status?: number) {
      super(message);
      this.name = "LibraryApiError";
      this.status = status;
    }
  },
}));

import { checkBackendHealth } from "./features/health/healthApi";
import * as libraryApi from "./features/library/libraryApi";

const mockedCheck = vi.mocked(checkBackendHealth);

beforeAll(() => {
  class ResizeObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = ResizeObserverMock;

  Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
    configurable: true,
    value() {
      return {
        width: 800,
        height: 600,
        top: 0,
        left: 0,
        bottom: 600,
        right: 800,
        x: 0,
        y: 0,
        toJSON() {},
      };
    },
  });
});

describe("App", () => {
  beforeEach(() => {
    mockedCheck.mockReset();
    vi.mocked(libraryApi.listLibraryAssets).mockReturnValue(new Promise(() => {}));
  });

  it("renders the Mitos Flow header", () => {
    mockedCheck.mockResolvedValue(false);
    render(<App />);
    expect(screen.getByText("Mitos Flow")).toBeInTheDocument();
  });

  it("shows connected status when backend is healthy", async () => {
    mockedCheck.mockResolvedValue(true);
    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("connection-status")).toHaveTextContent(
        "Backend connected",
      );
    });
  });

  it("shows disconnected status when backend is unreachable", async () => {
    mockedCheck.mockResolvedValue(false);
    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("connection-status")).toHaveTextContent(
        "Backend disconnected",
      );
    });
  });

  it("renders the workflow canvas with an empty state and node palette", () => {
    mockedCheck.mockResolvedValue(false);
    render(<App />);
    expect(screen.getByTestId("workflow-canvas")).toBeInTheDocument();
    expect(screen.getByTestId("node-palette")).toBeInTheDocument();
    expect(screen.queryByTestId("node-input")).not.toBeInTheDocument();
  });
});
