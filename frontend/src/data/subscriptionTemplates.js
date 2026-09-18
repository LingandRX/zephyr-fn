/**
 * 订阅会员模板数据管理
 * 支持首屏内置底包即时渲染 + 异步拉取后端生效的远程同步模板
 */

import { reactive } from "vue";
import templateData from "./subscriptionTemplates.json";
import { getTemplates } from "../services/api.js";

// 响应式分类元数据
export const templateCategories = reactive({ ...(templateData.categories || {}) });

// 响应式模板列表数据（初始为内置数据，支持热更新）
export const subscriptionTemplates = reactive([...(templateData.templates || [])]);

// 模板元信息（来源、同步时间等）
export const templateMeta = reactive({
  source: "builtin",
  synced_at: null,
  loaded: false,
});

/**
 * 异步从后端加载当前生效的模板（远程同步版或内置版）
 */
export async function fetchRemoteTemplates() {
  try {
    const res = await getTemplates();
    if (res && res.data) {
      if (Array.isArray(res.data.templates)) {
        subscriptionTemplates.splice(0, subscriptionTemplates.length, ...res.data.templates);
      }
      if (res.data.categories && typeof res.data.categories === "object") {
        for (const k of Object.keys(templateCategories)) {
          delete templateCategories[k];
        }
        Object.assign(templateCategories, res.data.categories);
      }
      templateMeta.source = res.source || "builtin";
      templateMeta.synced_at = res.synced_at || null;
      templateMeta.loaded = true;
    }
  } catch (err) {
    // 网络异常时静默保持当前已有数据（无感知降级）
    console.warn("拉取生效模板失败，保持本地数据:", err);
  }
  return {
    source: templateMeta.source,
    synced_at: templateMeta.synced_at,
    count: subscriptionTemplates.length,
  };
}

/**
 * 获取热门模板
 */
export function getPopularTemplates() {
  return subscriptionTemplates.filter((t) => t.popular);
}

/**
 * 按分类获取模板
 */
export function getTemplatesByCategory(category) {
  return subscriptionTemplates.filter((t) => t.category === category);
}

/**
 * 搜索模板
 */
export function searchTemplates(keyword) {
  if (!keyword) return [];
  const kw = keyword.toLowerCase();
  return subscriptionTemplates.filter(
    (t) =>
      t.name.toLowerCase().includes(kw) ||
      (t.notes && t.notes.toLowerCase().includes(kw))
  );
}

/**
 * 获取所有分类
 */
export function getAllCategories() {
  const used = new Set(subscriptionTemplates.map((t) => t.category));
  return Object.entries(templateCategories)
    .filter(([key]) => used.has(key))
    .map(([key, val]) => ({ id: key, ...val }));
}

