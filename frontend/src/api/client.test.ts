import { afterEach, describe, expect, it, vi } from "vitest";

import { deletePaper, explainRegion, getCurrentUser, login, uploadPaper } from "./client";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("uploadPaper", () => {
  it("sends multipart data without setting Content-Type manually", async () => {
    const responseBody = {
      paper: {
        paper_id: "a".repeat(64),
        filename: "paper.pdf",
        title: null,
        page_count: 1,
        status: "queued",
        stage: "queued",
        error: null,
        created_at: "2026-07-15T00:00:00Z",
        updated_at: "2026-07-15T00:00:00Z",
      },
      task_id: "11111111-1111-4111-8111-111111111111",
      deduplicated: false,
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => responseBody,
    } as Response);

    await uploadPaper(new File(["pdf"], "paper.pdf", { type: "application/pdf" }));

    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.method).toBe("POST");
    expect(init?.body).toBeInstanceOf(FormData);
    expect(init?.credentials).toBe("include");
    expect(init?.headers).toBeUndefined();
  });
});

describe("auth requests", () => {
  it("sends credentials for session cookie requests", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        user_id: "11111111-1111-4111-8111-111111111111",
        username: "admin",
        role: "admin",
        created_at: "2026-07-15T00:00:00Z",
      }),
    } as Response);

    await getCurrentUser();
    await login({ username: "admin", password: "password123" });

    expect(fetchMock.mock.calls[0]?.[1]?.credentials).toBe("include");
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
    });
  });
});

describe("explainRegion", () => {
  it("sends image multipart without setting Content-Type manually", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        asset_id: "11111111-1111-4111-8111-111111111111",
        explanation: "result",
        page: 1,
        bbox: [0, 0, 1, 1],
        viewport_rotation: 0,
        model: "vision",
      }),
    } as Response);
    await explainRegion("a".repeat(64), {
      image: new Blob(["image"], { type: "image/png" }),
      page: 1,
      bbox: [0, 0, 1, 1],
      viewportRotation: 0,
      nearbyText: "",
      question: "explain",
    });
    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.body).toBeInstanceOf(FormData);
    expect(init?.credentials).toBe("include");
    expect(init?.headers).toBeUndefined();
  });
});

describe("deletePaper", () => {
  it("sends an empty DELETE request and does not parse a 204 response", async () => {
    const json = vi.fn();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 204,
      json,
    } as unknown as Response);

    await deletePaper("a".repeat(64));

    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.method).toBe("DELETE");
    expect(init?.body).toBeUndefined();
    expect(init?.credentials).toBe("include");
    expect(init?.headers).toBeUndefined();
    expect(json).not.toHaveBeenCalled();
  });
});
