/**
 * 订阅会员模板数据
 * 数据来源: subscriptionTemplates.json
 */

import templateData from "./subscriptionTemplates.json";

// 模板分类
export const TEMPLATE_CATEGORIES = templateData.categories;

// 订阅模板列表
export const subscriptionTemplates = templateData.templates;

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
  return Object.entries(TEMPLATE_CATEGORIES)
    .filter(([key]) => used.has(key))
    .map(([key, val]) => ({ id: key, ...val }));
}
