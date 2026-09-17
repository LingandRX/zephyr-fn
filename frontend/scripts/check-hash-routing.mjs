/* eslint-disable no-console */
/**
 * Hash 路由回归与双向绑定检查：
 * 1. 纯函数路由映射测试（getViewFromHash / getHashForView）
 * 2. 模拟浏览器环境下的双向绑定测试：
 *    - 页面刷新保活（初始 hash -> ui.view）
 *    - 浏览器前进/后退（hashchange -> ui.view）
 *    - 视图切换同步 URL（ui.view -> window.location.hash）
 *    - 畸形 / 非法 Hash 优雅回退与规范化
 */
import assert from "node:assert/strict";
import { nextTick } from "vue";
import {
  VALID_VIEWS,
  DEFAULT_VIEW,
  getViewFromHash,
  getHashForView,
} from "../src/utils/ui.js";

let passed = 0;
let failed = 0;

function it(name, fn) {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    passed++;
  } catch (err) {
    console.error(`  ✗ ${name}:`, err.message);
    failed++;
  }
}

async function itAsync(name, fn) {
  try {
    await fn();
    console.log(`  ✓ ${name}`);
    passed++;
  } catch (err) {
    console.error(`  ✗ ${name}:`, err.message);
    failed++;
  }
}

console.log("=== 1. Hash 纯函数解析与生成测试 ===");

it("常量完整性定义", () => {
  assert.deepEqual(VALID_VIEWS, ["subscriptions", "calendar", "statistics", "settings"]);
  assert.equal(DEFAULT_VIEW, "subscriptions");
});

it("空 Hash / 根 Hash 回退为默认视图", () => {
  assert.equal(getViewFromHash(""), "subscriptions");
  assert.equal(getViewFromHash("#"), "subscriptions");
  assert.equal(getViewFromHash("#/"), "subscriptions");
  assert.equal(getViewFromHash("  "), "subscriptions");
});

it("标准 Hash 解析为对应视图", () => {
  assert.equal(getViewFromHash("#/subscriptions"), "subscriptions");
  assert.equal(getViewFromHash("#/calendar"), "calendar");
  assert.equal(getViewFromHash("#/statistics"), "statistics");
  assert.equal(getViewFromHash("#/settings"), "settings");
});

it("容错解析：带尾部斜杠、缺失前置斜杠、携带 query 参数", () => {
  assert.equal(getViewFromHash("#/calendar/"), "calendar");
  assert.equal(getViewFromHash("#calendar"), "calendar");
  assert.equal(getViewFromHash("#/calendar?tab=month&year=2026"), "calendar");
  assert.equal(getViewFromHash("#/statistics?filter=annual"), "statistics");
});

it("未知 / 非法 Hash 自动优雅回退为默认视图", () => {
  assert.equal(getViewFromHash("#/unknown_page"), "subscriptions");
  assert.equal(getViewFromHash("#/hacker/path"), "subscriptions");
  assert.equal(getViewFromHash("#!/test"), "subscriptions");
});

it("getHashForView 生成标准 Hash 路径", () => {
  assert.equal(getHashForView("subscriptions"), "#/subscriptions");
  assert.equal(getHashForView("calendar"), "#/calendar");
  assert.equal(getHashForView("statistics"), "#/statistics");
  assert.equal(getHashForView("settings"), "#/settings");
  assert.equal(getHashForView("unknown"), "#/subscriptions");
});

console.log("\n=== 2. 模拟浏览器环境双向绑定测试 ===");

await (async () => {
  const listeners = {};
  let currentHash = "#/calendar";
  let historyEntry = currentHash;

  const mockWindow = {
    location: {
      get hash() {
        return currentHash;
      },
      set hash(val) {
        const oldVal = currentHash;
        currentHash = val;
        historyEntry = val;
        if (oldVal !== val && listeners["hashchange"]) {
          listeners["hashchange"].forEach((cb) => cb({ type: "hashchange" }));
        }
      },
    },
    history: {
      replaceState: (_state, _title, url) => {
        currentHash = url;
        historyEntry = url;
      },
    },
    matchMedia: () => ({ matches: false, addEventListener: () => {} }),
    addEventListener: (event, cb) => {
      listeners[event] = listeners[event] || [];
      listeners[event].push(cb);
    },
    removeEventListener: (event, cb) => {
      if (listeners[event]) {
        listeners[event] = listeners[event].filter((fn) => fn !== cb);
      }
    },
  };

  const mockDocument = {
    documentElement: { dataset: {} },
  };

  globalThis.window = mockWindow;
  globalThis.document = mockDocument;
  globalThis.history = mockWindow.history;

  const { ui, navigateTo } = await import(`../src/utils/ui.js?test=${Date.now()}`);

  await itAsync("页面刷新保活（初始 URL Hash 决定初始 ui.view）", async () => {
    assert.equal(ui.view, "calendar", "刷新打开 #/calendar 时 ui.view 应直接为 calendar");
  });

  await itAsync("ui.view 变动同步到 window.location.hash（内部导航）", async () => {
    ui.view = "statistics";
    await nextTick();
    assert.equal(mockWindow.location.hash, "#/statistics");
    assert.equal(historyEntry, "#/statistics");
  });

  await itAsync("navigateTo 辅助函数正常切换并同步 Hash", async () => {
    navigateTo("settings");
    await nextTick();
    assert.equal(ui.view, "settings");
    assert.equal(mockWindow.location.hash, "#/settings");
  });

  await itAsync("浏览器后退（模拟 hashchange 事件反向同步 ui.view）", async () => {
    mockWindow.location.hash = "#/calendar";
    await nextTick();
    assert.equal(ui.view, "calendar", "后退时 hashchange 应使 ui.view 变为 calendar");
  });

  await itAsync("浏览器前进（模拟 hashchange 事件前进到 #/settings）", async () => {
    mockWindow.location.hash = "#/settings";
    await nextTick();
    assert.equal(ui.view, "settings", "前进时 hashchange 应使 ui.view 变为 settings");
  });

  await itAsync("非法 Hash 自动规范化并回退为默认视图", async () => {
    mockWindow.location.hash = "#/invalid_route";
    await nextTick();
    assert.equal(ui.view, "subscriptions");
    assert.equal(mockWindow.location.hash, "#/subscriptions");
  });

  delete globalThis.window;
  delete globalThis.document;
  delete globalThis.history;
})();

console.log(`\n测试汇总: 通过 ${passed} 个，失败 ${failed} 个`);
if (failed > 0) {
  process.exit(1);
} else {
  console.log("=== Hash 路由双向绑定检查全部通过 ===");
}
