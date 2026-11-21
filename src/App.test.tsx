import { it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
vi.mock("./PerformanceChart", () => ({
  default: () => <div data-testid="chart" />,
}));
import { market, instrument, history } from "./test/fixtures";
it("explains calendar quote expiry separately from the old snapshot warning", async () => {
  const clock = vi.spyOn(Date, "now").mockReturnValue(Date.parse("2025-01-12T12:00:00Z"));
  const quote = { ...instrument(), expectedLastDate: "2025-01-03", freshUntil: "2025-01-15T21:05:00Z", calendar: "XNYS" };
  vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => market([quote]) } as Response);
  try {
    render(<App />);
    await screen.findByRole("button", { name: "Details AAA" });
    expect(screen.getByText(/快照已超过 5 个自然日/)).toHaveTextContent("行情是否滞后按各资产交易日历与到期时间判断");
    expect(screen.queryByText(/已将原“已更新”行情标记为滞后/)).not.toBeInTheDocument();
    expect(screen.getByText(/仅无交易日历元数据时/)).toHaveTextContent("长假不会仅因收盘日期较旧而滞后");
    expect(screen.queryByText(/来源与覆盖提醒/)).not.toBeInTheDocument();
  } finally { clock.mockRestore(); }
});
it("displays the snapshot date and clock in UTC even with an Australia/Melbourne default timezone", async () => {
  const generatedAt = "2025-01-04T23:30:00Z";
  const stamp = new Date(generatedAt);
  const dateOptions: Intl.DateTimeFormatOptions = { day: "2-digit", month: "short", year: "numeric" };
  const expectedDate = stamp.toLocaleDateString("zh-CN", { ...dateOptions, timeZone: "UTC" });
  const melbourneDate = stamp.toLocaleDateString("zh-CN", { ...dateOptions, timeZone: "Australia/Melbourne" });
  const expectedTime = stamp.toLocaleTimeString("en-GB", { timeZone: "UTC" });
  expect(expectedDate).not.toBe(melbourneDate);
  const originalDate = Date.prototype.toLocaleDateString;
  const originalTime = Date.prototype.toLocaleTimeString;
  const dateSpy = vi.spyOn(Date.prototype, "toLocaleDateString").mockImplementation(function (this: Date, locales, options) {
    return originalDate.call(this, locales, { timeZone: "Australia/Melbourne", ...options });
  });
  const timeSpy = vi.spyOn(Date.prototype, "toLocaleTimeString").mockImplementation(function (this: Date, locales, options) {
    return originalTime.call(this, locales, { timeZone: "Australia/Melbourne", ...options });
  });
  vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => ({ ...market(), generatedAt }) } as Response);
  try {
    render(<App />);
    await screen.findByRole("button", { name: "Details AAA" });
    const metric = screen.getByText("快照更新时间").parentElement!;
    expect(metric.querySelector(".date-stat")).toHaveTextContent(expectedDate);
    expect(metric.querySelector("p")).toHaveTextContent(`${expectedTime} UTC`);
  } finally { dateSpy.mockRestore(); timeSpy.mockRestore(); }
});
it("expires an offline cached calendar quote on the existing minute tick without fetching", async () => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
  const clock = vi.spyOn(Date, "now").mockReturnValue(Date.parse("2025-01-04T11:59:00Z"));
  const quote = { ...instrument(), expectedLastDate: "2025-01-03", freshUntil: "2025-01-04T12:00:00Z", calendar: "XNYS" };
  vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => ({ ...market([quote]), offlineCached: true }) } as Response);
  const view = render(<App />);
  try {
    await screen.findByRole("button", { name: "Details AAA" });
    expect(screen.getByText(/当前离线/)).toBeInTheDocument();
    expect(screen.queryByText(/来源与覆盖提醒/)).not.toBeInTheDocument();
    clock.mockReturnValue(Date.parse("2025-01-04T12:00:00Z"));
    act(() => { vi.advanceTimersByTime(60000); });
    expect(screen.getByText(/来源与覆盖提醒/)).toHaveTextContent("1 项数据滞后或不可用");
    expect(fetch).toHaveBeenCalledTimes(1);
  } finally { view.unmount(); clock.mockRestore(); vi.useRealTimers(); }
});
it("shows source failures and preserves an explicit stale data warning", async () => {
  const data = {
    ...market(),
    failures: [{ id: "AAA", error: "Upstream source unavailable" }],
  };
  data.instruments[0].status = "stale";
  vi.mocked(fetch).mockResolvedValue({
    ok: true,
    json: async () => data,
  } as Response);
  render(<App />);
  expect(await screen.findByText(/来源与覆盖提醒/)).toBeInTheDocument();
  expect(screen.getByText(/Upstream source unavailable/)).toBeInTheDocument();
});
it("refreshes an open market and keeps the last validated snapshot if a refresh fails", async () => {
  vi.mocked(fetch)
    .mockResolvedValueOnce({ ok: true, json: async () => market() } as Response)
    .mockResolvedValueOnce({ ok: false, status: 503 } as Response)
    .mockResolvedValue({
      ok: true,
      json: async () => market([instrument("NEW")]),
    } as Response);
  render(<App />);
  await screen.findByRole("button", { name: "Details AAA" });
  await userEvent.click(
    screen.getByRole("button", { name: "Refresh market data" }),
  );
  expect(await screen.findByText(/刷新失败/)).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Details AAA" }),
  ).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Refresh market data" }),
  );
  expect(
    await screen.findByRole("button", { name: "Details NEW" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Details AAA" }),
  ).not.toBeInTheDocument();
});
it("opens dividend detail lazily with unknown franking and downloads full raw history, not chart range", async () => {
  const h = { ...history(), dividends: null };
  vi.mocked(fetch).mockImplementation(
    async (url) =>
      ({
        ok: true,
        json: async () => (String(url).includes("market.json") ? market() : h),
      }) as Response,
  );
  vi.stubGlobal(
    "URL",
    Object.assign(URL, {
      createObjectURL: vi.fn(() => "blob:test"),
      revokeObjectURL: vi.fn(),
    }),
  );
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<App />);
  await screen.findByRole("button", { name: "Details AAA" });
  await userEvent.click(screen.getByRole("button", { name: "Details AAA" }));
  const dialog = await screen.findByRole("dialog");
  expect(dialog).toHaveTextContent("抵税比例未知");
  expect(await screen.findByText("分红历史不可用")).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Download full history JSON" }),
  );
  expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
  await userEvent.click(screen.getByRole("button", { name: "Close details" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
it("fetches history only after selection, saves selection and changes chart ranges without re-fetching", async () => {
  vi.mocked(fetch).mockImplementation(
    async (url) =>
      ({
        ok: true,
        json: async () =>
          String(url).includes("market.json")
            ? market()
            : history(String(url).includes("BBB") ? "BBB" : "AAA"),
      }) as Response,
  );
  const view = render(<App />);
  await screen.findByRole("button", { name: "Details AAA" });
  expect(fetch).toHaveBeenCalledTimes(1);
  await userEvent.click(screen.getByRole("checkbox", { name: "Compare AAA" }));
  expect(await screen.findByText(/共同基准： 2025-01-02/)).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(2);
  await userEvent.click(
    screen.getByRole("button", { name: "Chart period ALL" }),
  );
  expect(screen.getByText(/共同基准： 2020-01-02/)).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(2);
  view.unmount();
  render(<App />);
  expect(
    await screen.findByRole("checkbox", { name: "Compare AAA" }),
  ).toBeChecked();
  await screen.findByText(/共同基准：/);
  await userEvent.click(
    screen.getByRole("button", { name: "Clear comparison" }),
  );
  expect(
    screen.getByRole("checkbox", { name: "Compare AAA" }),
  ).not.toBeChecked();
});
it("filters the visible universe and exposes every ranking period plus total-return mode", async () => {
  const high = instrument("HIGH", "AU", 0.08);
  high.returns.price["1y"] = 0.8;
  vi.mocked(fetch).mockResolvedValue({
    ok: true,
    json: async () =>
      market([
        instrument("LOW", "US", 0.02),
        high,
        instrument("MISSING", "CN", null),
      ]),
  } as Response);
  render(<App />);
  await screen.findByRole("button", { name: "Details HIGH" });
  await userEvent.selectOptions(
    screen.getByLabelText("Ranking period"),
    "cashYield",
  );
  expect(
    screen.getAllByRole("button", { name: /Details / })[0],
  ).toHaveAccessibleName("Details HIGH");
  await userEvent.click(screen.getByRole("button", { name: "Sort ascending" }));
  expect(
    screen.getAllByRole("button", { name: /Details / })[0],
  ).toHaveAccessibleName("Details LOW");
  for (const p of ["1m", "3m", "6m", "1y", "3y", "5y", "10y"]) {
    await userEvent.selectOptions(screen.getByLabelText("Ranking period"), p);
  }
  await userEvent.selectOptions(screen.getByLabelText("Country"), "AU");
  expect(
    screen.queryByRole("button", { name: "Details LOW" }),
  ).not.toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Minimum cash yield (%)"), "9");
  expect(screen.getByText("没有符合当前筛选条件的资产。")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Reset filters" }));
  expect(
    screen.getByRole("button", { name: "Details LOW" }),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Total return" }));
  expect(screen.getByRole("button", { name: "Total return" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});
beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("fetch", vi.fn());
});
it("A→B→A ignores late responses and stale errors after the current selection succeeds", async () => {
  let oldResolve!: (r: Response) => void, secondResolve!: (r: Response) => void;
  let aCalls = 0;
  vi.mocked(fetch).mockImplementation((url) => {
    if (String(url).includes("market.json"))
      return Promise.resolve({
        ok: true,
        json: async () => market(),
      } as Response);
    if (String(url).includes("AAA")) {
      aCalls++;
      if (aCalls === 1) return new Promise((r) => (oldResolve = r));
      return Promise.resolve({
        ok: true,
        json: async () => history("AAA", 150),
      } as Response);
    }
    return new Promise((r) => (secondResolve = r));
  });
  render(<App />);
  await screen.findByRole("button", { name: "Details AAA" });
  await userEvent.click(screen.getByRole("checkbox", { name: "Compare AAA" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "Compare AAA" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "Compare BBB" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "Compare BBB" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "Compare AAA" }));
  await screen.findByText(/共同基准：/);
  oldResolve({ ok: true, json: async () => history("AAA", 999) } as Response);
  secondResolve({ ok: false, status: 500 } as Response);
  await waitFor(() =>
    expect(screen.getByTestId("comparison-end-AAA")).toHaveTextContent(
      "+50.00%",
    ),
  );
  expect(screen.queryByText(/HTTP 500/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("checkbox", { name: "Compare AAA" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "Compare AAA" }));
  await waitFor(() =>
    expect(screen.getByTestId("comparison-end-AAA")).toHaveTextContent(
      "+50.00%",
    ),
  );
});
it("has a real missing-data screen and retries into the market ranking without loading histories eagerly", async () => {
  vi.mocked(fetch)
    .mockResolvedValueOnce({ ok: false, status: 404 } as Response)
    .mockResolvedValue({ ok: true, json: async () => market() } as Response);
  render(<App />);
  expect(await screen.findByText(/市场数据暂不可用/)).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Retry market data" }),
  );
  expect(
    await screen.findByRole("button", { name: "Details AAA" }),
  ).toBeInTheDocument();
  expect(screen.getByText("BBB fund")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(screen.getByText(/勾选资产，开启历史对比/)).toBeInTheDocument();
});
