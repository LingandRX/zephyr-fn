<script setup>
// 设置视图：常规 / 通知渠道 / 分类管理 / 备份与数据
// 支持子页面（Tabs）切换展示
import { ref, reactive, computed, watch, nextTick, onMounted } from "vue";
import {
  getSettings, saveSettings, getCategories, createCategory, deleteCategory,
  importCsv, download,
  testEmailNotification, testPushPlusNotification,
  getLogTail,
} from "../services/api.js";
import { toast } from "../utils/ui.js";

import CustomSelect from "../components/CustomSelect.vue";
import CustomTimePicker from "../components/CustomTimePicker.vue";

const CURRENCY_OPTIONS = [
  { label: "CNY (¥)", value: "CNY" },
  { label: "USD ($)", value: "USD" },
  { label: "HKD (HK$)", value: "HKD" },
];

const TABS = [
  { key: "general", label: "常规设置", svg: [
    "M904.533333 422.4l-85.333333-14.933333-17.066667-38.4 49.066667-70.4c14.933333-21.333333 12.8-49.066667-6.4-68.266667l-53.333333-53.333333c-19.2-19.2-46.933333-21.333333-68.266667-6.4l-70.4 49.066666-38.4-17.066666-14.933333-85.333334c-2.133333-23.466667-23.466667-42.666667-49.066667-42.666666h-74.666667c-25.6 0-46.933333 19.2-53.333333 44.8l-14.933333 85.333333-38.4 17.066667L296.533333 170.666667c-21.333333-14.933333-49.066667-12.8-68.266666 6.4l-53.333334 53.333333c-19.2 19.2-21.333333 46.933333-6.4 68.266667l49.066667 70.4-17.066667 38.4-85.333333 14.933333c-21.333333 4.266667-40.533333 25.6-40.533333 51.2v74.666667c0 25.6 19.2 46.933333 44.8 53.333333l85.333333 14.933333 17.066667 38.4L170.666667 727.466667c-14.933333 21.333333-12.8 49.066667 6.4 68.266666l53.333333 53.333334c19.2 19.2 46.933333 21.333333 68.266667 6.4l70.4-49.066667 38.4 17.066667 14.933333 85.333333c4.266667 25.6 25.6 44.8 53.333333 44.8h74.666667c25.6 0 46.933333-19.2 53.333333-44.8l14.933334-85.333333 38.4-17.066667 70.4 49.066667c21.333333 14.933333 49.066667 12.8 68.266666-6.4l53.333334-53.333334c19.2-19.2 21.333333-46.933333 6.4-68.266666l-49.066667-70.4 17.066667-38.4 85.333333-14.933334c25.6-4.266667 44.8-25.6 44.8-53.333333v-74.666667c-4.266667-27.733333-23.466667-49.066667-49.066667-53.333333z m-19.2 117.333333l-93.866666 17.066667c-10.666667 2.133333-19.2 8.533333-23.466667 19.2l-29.866667 70.4c-4.266667 10.666667-2.133333 21.333333 4.266667 29.866667l53.333333 76.8-40.533333 40.533333-76.8-53.333333c-8.533333-6.4-21.333333-8.533333-29.866667-4.266667L576 768c-10.666667 4.266667-17.066667 12.8-19.2 23.466667l-17.066667 93.866666h-57.6l-17.066666-93.866666c-2.133333-10.666667-8.533333-19.2-19.2-23.466667l-70.4-29.866667c-10.666667-4.266667-21.333333-2.133333-29.866667 4.266667l-76.8 53.333333-40.533333-40.533333 53.333333-76.8c6.4-8.533333 8.533333-21.333333 4.266667-29.866667L256 576c-4.266667-10.666667-12.8-17.066667-23.466667-19.2l-93.866666-17.066667v-57.6l93.866666-17.066666c10.666667-2.133333 19.2-8.533333 23.466667-19.2l29.866667-70.4c4.266667-10.666667 2.133333-21.333333-4.266667-29.866667l-53.333333-76.8 40.533333-40.533333 76.8 53.333333c8.533333 6.4 21.333333 8.533333 29.866667 4.266667L448 256c10.666667-4.266667 17.066667-12.8 19.2-23.466667l17.066667-93.866666h57.6l17.066666 93.866666c2.133333 10.666667 8.533333 19.2 19.2 23.466667l70.4 29.866667c10.666667 4.266667 21.333333 2.133333 29.866667-4.266667l76.8-53.333333 40.533333 40.533333-53.333333 76.8c-6.4 8.533333-8.533333 21.333333-4.266667 29.866667L768 448c4.266667 10.666667 12.8 17.066667 23.466667 19.2l93.866666 17.066667v55.466666z",
    "M512 394.666667c-64 0-117.333333 53.333333-117.333333 117.333333s53.333333 117.333333 117.333333 117.333333 117.333333-53.333333 117.333333-117.333333-53.333333-117.333333-117.333333-117.333333z m0 170.666666c-29.866667 0-53.333333-23.466667-53.333333-53.333333s23.466667-53.333333 53.333333-53.333333 53.333333 23.466667 53.333333 53.333333-23.466667 53.333333-53.333333 53.333333z",
  ] },
  { key: "notifications", label: "通知渠道", svg: [
    "M800 625.066667V448c0-117.333333-70.4-217.6-170.666667-262.4-4.266667-61.866667-55.466667-110.933333-117.333333-110.933333s-113.066667 49.066667-117.333333 110.933333c-100.266667 44.8-170.666667 145.066667-170.666667 262.4v177.066667c-57.6 46.933333-85.333333 110.933333-85.333333 185.6 0 17.066667 14.933333 32 32 32h206.933333c14.933333 61.866667 70.4 106.666667 134.4 106.666666s119.466667-44.8 134.4-106.666666H853.333333c17.066667 0 32-14.933333 32-32 0-76.8-27.733333-138.666667-85.333333-185.6zM512 138.666667c19.2 0 36.266667 10.666667 44.8 25.6-14.933333-2.133333-29.866667-4.266667-44.8-4.266667-14.933333 0-29.866667 2.133333-44.8 4.266667 8.533333-14.933333 25.6-25.6 44.8-25.6z m0 746.666666c-29.866667 0-55.466667-17.066667-66.133333-42.666666h134.4c-12.8 25.6-38.4 42.666667-68.266667 42.666666z m-307.2-106.666666c6.4-46.933333 29.866667-83.2 70.4-113.066667 8.533333-6.4 12.8-14.933333 12.8-25.6v-192c0-123.733333 100.266667-224 224-224S736 324.266667 736 448v192c0 10.666667 4.266667 19.2 12.8 25.6 40.533333 29.866667 64 66.133333 70.4 113.066667H204.8z",
  ] },
  { key: "categories", label: "分类管理", svg: [
    "M405.333333 458.666667H149.333333c-29.866667 0-53.333333-23.466667-53.333333-53.333334V149.333333c0-29.866667 23.466667-53.333333 53.333333-53.333333h256c29.866667 0 53.333333 23.466667 53.333334 53.333333v256c0 29.866667-23.466667 53.333333-53.333334 53.333334z m-245.333333-64h234.666667v-234.666667h-234.666667v234.666667zM874.666667 458.666667H618.666667c-29.866667 0-53.333333-23.466667-53.333334-53.333334V149.333333c0-29.866667 23.466667-53.333333 53.333334-53.333333h256c29.866667 0 53.333333 23.466667 53.333333 53.333333v256c0 29.866667-23.466667 53.333333-53.333333 53.333334z m-245.333334-64h234.666667v-234.666667h-234.666667v234.666667zM874.666667 928H618.666667c-29.866667 0-53.333333-23.466667-53.333334-53.333333V618.666667c0-29.866667 23.466667-53.333333 53.333334-53.333334h256c29.866667 0 53.333333 23.466667 53.333333 53.333334v256c0 29.866667-23.466667 53.333333-53.333333 53.333333z m-245.333334-64h234.666667v-234.666667h-234.666667v234.666667zM405.333333 928H149.333333c-29.866667 0-53.333333-23.466667-53.333333-53.333333V618.666667c0-29.866667 23.466667-53.333333 53.333333-53.333334h256c29.866667 0 53.333333 23.466667 53.333334 53.333334v256c0 29.866667-23.466667 53.333333-53.333334 53.333333z m-245.333333-64h234.666667v-234.666667h-234.666667v234.666667z",
  ] },
  { key: "backup", label: "数据与备份", svg: [
    "M906.666667 298.666667L725.333333 117.333333c-14.933333-14.933333-32-21.333333-53.333333-21.333333H170.666667C130.133333 96 96 130.133333 96 170.666667v682.666666c0 40.533333 34.133333 74.666667 74.666667 74.666667h682.666666c40.533333 0 74.666667-34.133333 74.666667-74.666667V349.866667c0-19.2-8.533333-38.4-21.333333-51.2zM652.8 864H371.2V648.533333h281.6v215.466667z m211.2-10.666667c0 6.4-4.266667 10.666667-10.666667 10.666667h-140.8V618.666667c0-17.066667-12.8-29.866667-29.866666-29.866667H341.333333c-17.066667 0-29.866667 12.8-29.866666 29.866667v245.333333H170.666667c-6.4 0-10.666667-4.266667-10.666667-10.666667V170.666667c0-6.4 4.266667-10.666667 10.666667-10.666667h140.8V320c0 17.066667 12.8 29.866667 29.866666 29.866667h277.333334c17.066667 0 29.866667-12.8 29.866666-29.866667s-12.8-29.866667-29.866666-29.866667H371.2V160h302.933333c2.133333 0 6.4 2.133333 8.533334 2.133333l179.2 179.2c2.133333 2.133333 2.133333 4.266667 2.133333 8.533334V853.333333z",
  ] },
  { key: "logs", label: "运行日志", svg: [
    "M832 74.666667H192c-17.066667 0-32 14.933333-32 32v765.866666c0 12.8 4.266667 23.466667 12.8 34.133334 8.533333 10.666667 21.333333 17.066667 36.266667 19.2h6.4c12.8 0 23.466667-4.266667 34.133333-12.8l264.533333-213.333334 264.533334 213.333334c8.533333 8.533333 21.333333 12.8 34.133333 12.8 29.866667 0 53.333333-23.466667 53.333333-53.333334V106.666667c-2.133333-17.066667-17.066667-32-34.133333-32z m-32 776.533333L531.2 633.6c-10.666667-8.533333-27.733333-8.533333-40.533333 0L224 851.2V138.666667h576v712.533333z",
    "M341.333333 341.333333h320c17.066667 0 32-14.933333 32-32S678.4 277.333333 661.333333 277.333333H341.333333c-17.066667 0-32 14.933333-32 32S324.266667 341.333333 341.333333 341.333333zM341.333333 512h213.333334c17.066667 0 32-14.933333 32-32S571.733333 448 554.666667 448H341.333333c-17.066667 0-32 14.933333-32 32S324.266667 512 341.333333 512z",
  ] },
];

const activeTab = ref("general");
const loaded = ref(false);
const saving = ref(false);
const saveStatusText = ref("");
const cats = ref([]);

const testingEmail = ref(false);
const testingPushplus = ref(false);
const testEmailTarget = ref("");

// ---------- 运行日志 ----------
const LOG_LINES = 200;
const logLines = ref([]);
const logFile = ref("");
const logError = ref("");
const logLoading = ref(false);

async function loadLogTail() {
  logLoading.value = true;
  logError.value = "";
  try {
    const r = await getLogTail(LOG_LINES);
    logLines.value = r.lines || [];
    logFile.value = r.file || "";
  } catch (err) {
    logError.value = err.message;
  } finally {
    logLoading.value = false;
  }
}

// 切到「运行日志」页签时自动加载
watch(activeTab, (t) => {
  if (t === "logs") loadLogTail();
});

const form = reactive({
  default_currency: "CNY",
  exchange_rate_usd: 7.2,
  exchange_rate_hkd: 0.92,
  notification_days: 7,
  notification_enabled: true,
  do_not_disturb_start: "",
  do_not_disturb_end: "",
  email_enabled: false,
  smtp_host: "",
  smtp_port: "",
  smtp_username: "",
  smtp_password: "",
  smtp_password_configured: false,
  smtp_from_address: "",
  pushplus_enabled: false,
  pushplus_token: "",
  pushplus_token_configured: false,
  // PushPlus 专用 SMTP 配置
  pushplus_smtp_host: "",
  pushplus_smtp_port: "",
  pushplus_smtp_username: "",
  pushplus_smtp_password: "",
  pushplus_smtp_password_configured: false,
  pushplus_smtp_from_address: "",
});

const newCat = reactive({ name: "" });
const adding = ref(false);
const nameErr = ref("");

const MAX_CAT_NAME_LEN = 20;
const MAX_CAT_COUNT = 50;

const CAN_ADD_CAT = computed(() => newCat.name.trim().length > 0 && !nameErr.value && !adding.value);

function normalizeCatName(s) {
  // NFC 归一并做全角转半角，便于重名判断（与后端 _normalize_category_name 保持一致）
  let t = String(s ?? "").normalize("NFC").trim();
  // 全角转半角
  t = t.replace(/[\uFF01-\uFF5E]/g, ch => String.fromCharCode(ch.charCodeAt(0) - 0xFEE0));
  // 全角空格转半角后再 trim，保证空名（含全角空格）能被正确识别
  t = t.replace(/\u3000/g, " ").trim();
  return t;
}

function validateCat(name) {
  const rawName = String(name ?? "");
  const trimmed = rawName.trim();
  const normalized = normalizeCatName(trimmed);
  // 空值用归一化后的 codepoint 长度判断，避免空白字符/全角空格绕过
  if ([...normalized].length === 0) return "请输入分类名称";
  if ([...normalized].length > MAX_CAT_NAME_LEN) return `分类名称最多${MAX_CAT_NAME_LEN}字`;
  if (/[<>"'&]/.test(normalized)) return "分类名称不能包含 < > \" \' &";
  if (cats.value.length >= MAX_CAT_COUNT) return `分类数量已达上限(${MAX_CAT_COUNT})`;
  // 重名：大小写+全半角不敏感
  const low = normalized.toLowerCase();
  if (cats.value.some(c => normalizeCatName(c.name).toLowerCase() === low)) return "分类已存在";
  return null;
}

// pushplus Token 掩码：显示星号个数与真实 Token 长度一致（输入多少显示多少），
// 后端只下发 *_masked 掩码串，绝不回传明文。
function isPushplusMask(v) {
  return typeof v === "string" && /^\*+$/.test(v.trim());
}

function isSecretUpdate(value) {
  const text = String(value ?? "").trim();
  if (!text) return false;
  // 任意长度的纯掩码字符（* • · ●）都不视为新密钥，避免把 `**`、`****abc` 等
  // 中间态当成真实输入提交；掩码由前端兜底防误存，后端 is_secret_placeholder 同样有保护。
  if (/^(?:\*|[•·●])+$/.test(text)) return false;
  if (/已配置|configured|redacted|masked/i.test(text)) return false;
  return true;
}

async function loadAll() {
  try {
    const [s, c] = await Promise.all([getSettings(), getCategories()]);
    Object.assign(form, {
      default_currency: s.default_currency || "CNY",
      exchange_rate_usd: s.exchange_rate_usd ?? 7.2,
      exchange_rate_hkd: s.exchange_rate_hkd ?? 0.92,
      notification_days: s.notification_days ?? 7,
      notification_enabled: !!s.notification_enabled,
      do_not_disturb_start: s.do_not_disturb_start || "",
      do_not_disturb_end: s.do_not_disturb_end || "",
      email_enabled: !!s.email_enabled,
      smtp_host: s.smtp_host || "",
      smtp_port: s.smtp_port || "",
      smtp_username: s.smtp_username || "",
      // 后端只返回 configured 标志，不再返回密钥原文。
      smtp_password: "",
      smtp_password_configured: !!s.smtp_password_configured,
      smtp_from_address: s.smtp_from_address || "",
      pushplus_enabled: !!s.pushplus_enabled,
      pushplus_token: s.pushplus_token_configured ? (s.pushplus_token_masked || "***") : "",
      pushplus_token_configured: !!s.pushplus_token_configured,
      // PushPlus 专用 SMTP 配置
      pushplus_smtp_host: s.pushplus_smtp_host || "",
      pushplus_smtp_port: s.pushplus_smtp_port || "",
      pushplus_smtp_username: s.pushplus_smtp_username || "",
      pushplus_smtp_password: "",
      pushplus_smtp_password_configured: !!s.pushplus_smtp_password_configured,
      pushplus_smtp_from_address: s.pushplus_smtp_from_address || "",
    });
    savedForm = snapshotForm();
    cats.value = c;
    await nextTick();
    loaded.value = true;
  } catch (err) {
    toast(err.message, "err");
  }
}

// 延迟自动保存（防抖 800ms，静默保存状态，避免频繁 toast 打扰）
let saveTimer = null;
let statusTimer = null;

// 保存状态按卡片作用域显示：只有被修改的卡片才出现「保存中/保存成功」，
// 避免在 SMTP 卡片上编辑、却在 PushPlus 卡片上看到保存提示。
const SCOPE_FIELDS = {
  general: [
    "default_currency", "exchange_rate_usd", "exchange_rate_hkd",
    "notification_days", "notification_enabled",
    "do_not_disturb_start", "do_not_disturb_end",
  ],
  smtp: [
    "email_enabled", "smtp_host", "smtp_port", "smtp_username",
    "smtp_password", "smtp_password_configured", "smtp_from_address",
  ],
  pushplus: [
    "pushplus_enabled", "pushplus_token", "pushplus_token_configured",
    "pushplus_smtp_host", "pushplus_smtp_port", "pushplus_smtp_username",
    "pushplus_smtp_password", "pushplus_smtp_password_configured",
    "pushplus_smtp_from_address",
  ],
};
const saveScopes = ref(new Set());
let savedForm = {};

function snapshotForm() {
  const snap = {};
  for (const key of Object.keys(form)) snap[key] = form[key];
  return snap;
}

function dirtyScopes() {
  const scopes = new Set();
  for (const [scope, fields] of Object.entries(SCOPE_FIELDS)) {
    if (fields.some((f) => savedForm[f] !== form[f])) scopes.add(scope);
  }
  return scopes;
}

watch(
  form,
  () => {
    if (!loaded.value) return;
    clearTimeout(saveTimer);
    const scopes = dirtyScopes();
    // 保存成功后内部字段回写（掩码 / configured 等）触发的变化不再进入保存流程
    if (!scopes.size) return;
    saveScopes.value = scopes;
    saving.value = true;
    saveStatusText.value = "正在保存...";
    saveTimer = setTimeout(async () => {
      try {
        const smtpSecretDraft = isSecretUpdate(form.smtp_password);
        const pushplusDraft = isSecretUpdate(form.pushplus_token);
        const pushplusSmtpSecretDraft = isSecretUpdate(form.pushplus_smtp_password);
        // 输入框被清空且此前已配置 → 显式移除已保存的 Token 并保存
        const pushplusCleared =
          !pushplusDraft &&
          String(form.pushplus_token ?? "").trim() === "" &&
          form.pushplus_token_configured;
        const parsedNotificationDays = parseInt(form.notification_days, 10);
        const payload = {
          ...form,
          exchange_rate_usd: parseFloat(form.exchange_rate_usd) || 7.2,
          exchange_rate_hkd: parseFloat(form.exchange_rate_hkd) || 0.92,
          notification_days: Number.isNaN(parsedNotificationDays) ? 7 : parsedNotificationDays,
          smtp_port: form.smtp_port ? parseInt(form.smtp_port, 10) : null,
          do_not_disturb_start: form.do_not_disturb_start || null,
          do_not_disturb_end: form.do_not_disturb_end || null,
          smtp_host: form.smtp_host || null,
          smtp_username: form.smtp_username || null,
          smtp_from_address: form.smtp_from_address || null,
          // PushPlus SMTP 配置
          pushplus_smtp_host: form.pushplus_smtp_host || null,
          pushplus_smtp_port: form.pushplus_smtp_port ? parseInt(form.pushplus_smtp_port, 10) : null,
          pushplus_smtp_username: form.pushplus_smtp_username || null,
          pushplus_smtp_from_address: form.pushplus_smtp_from_address || null,
        };
        // 密钥输入框为空或包含掩码时不发送字段，后端会保留现有密钥；
        // 显式清空时发送 *_clear 标记，让后端移除已保存的密钥。
        delete payload.smtp_password;
        delete payload.pushplus_token;
        delete payload.pushplus_smtp_password;
        delete payload.smtp_password_configured;
        delete payload.pushplus_token_configured;
        delete payload.pushplus_smtp_password_configured;
        if (smtpSecretDraft) payload.smtp_password = form.smtp_password;
        if (pushplusDraft) payload.pushplus_token = form.pushplus_token;
        if (pushplusSmtpSecretDraft) payload.pushplus_smtp_password = form.pushplus_smtp_password;
        if (pushplusCleared) payload.pushplus_token_clear = true;

        await saveSettings(payload);
        // 成功后收尾：SMTP 清空前端草稿；pushplus 用掩码 *** 代替显示已保存的
        // Token，降低密钥在页面内存中的停留时间。
        if (smtpSecretDraft) {
          form.smtp_password = "";
          form.smtp_password_configured = true;
        }
        if (pushplusDraft) {
          const typed = String(form.pushplus_token ?? "");
          form.pushplus_token = typed ? "*".repeat(typed.length) : "";
          form.pushplus_token_configured = true;
        } else if (pushplusCleared) {
          form.pushplus_token = "";
          form.pushplus_token_configured = false;
        }
        if (pushplusSmtpSecretDraft) {
          form.pushplus_smtp_password = "";
          form.pushplus_smtp_password_configured = true;
        }
        // 与回写后的表单状态对齐，避免回写再次触发保存
        savedForm = snapshotForm();
        saving.value = false;
        saveStatusText.value = "✓ 设置已保存";
        clearTimeout(statusTimer);
        statusTimer = setTimeout(() => {
          saveStatusText.value = "";
          saveScopes.value = new Set();
        }, 2000);
      } catch (err) {
        saving.value = false;
        saveStatusText.value = "保存失败";
        toast(err.message, "err");
      }
    }, 800);
  },
  { deep: true },
);

// ---------- 测试通知 ----------

// pushplus 掩码输入辅助：聚焦时全选，从掩码开始输入时以新输入为准（防止拼接脏草稿）。
let pushplusLastValue = "";

function onPushplusFocus(e) {
  pushplusLastValue = e.target.value;
  if (isPushplusMask(form.pushplus_token)) e.target.select();
}

function onPushplusInput(e) {
  const el = e.target;
  const prev = pushplusLastValue;
  const v = el.value;
  pushplusLastValue = v;
  // 掩码状态下继续输入：去掉星号前缀，避免“***abc”这类拼接内容被当成新 Token。
  if (isPushplusMask(prev) && v !== "" && !isPushplusMask(v)) {
    const fresh = v.replace(/^\*+/, "");
    if (fresh) {
      el.value = fresh;
      form.pushplus_token = fresh;
      pushplusLastValue = fresh;
    }
  }
}

async function testEmail() {
  if (testingEmail.value) return;
  testingEmail.value = true;
  try {
    const payload = {
      smtp_host: form.smtp_host || undefined,
      smtp_port: form.smtp_port ? parseInt(form.smtp_port, 10) : undefined,
      smtp_username: form.smtp_username || undefined,
      smtp_from_address: form.smtp_from_address || undefined,
      to_address: testEmailTarget.value.trim() || undefined,
    };
    if (isSecretUpdate(form.smtp_password)) {
      payload.smtp_password = form.smtp_password;
    }
    const res = await testEmailNotification(payload);
    toast(res.message || "测试邮件发送成功");
  } catch (err) {
    toast(err.message, "err");
  } finally {
    testingEmail.value = false;
  }
}

async function testPushPlus() {
  if (testingPushplus.value) return;
  testingPushplus.value = true;
  try {
    const payload = {
      // PushPlus 专用 SMTP 配置（优先）
      pushplus_smtp_host: form.pushplus_smtp_host || undefined,
      pushplus_smtp_port: form.pushplus_smtp_port ? parseInt(form.pushplus_smtp_port, 10) : undefined,
      pushplus_smtp_username: form.pushplus_smtp_username || undefined,
      pushplus_smtp_from_address: form.pushplus_smtp_from_address || undefined,
      // 通用 SMTP 配置（回退）
      smtp_host: form.smtp_host || undefined,
      smtp_port: form.smtp_port ? parseInt(form.smtp_port, 10) : undefined,
      smtp_username: form.smtp_username || undefined,
      smtp_from_address: form.smtp_from_address || undefined,
    };
    if (isSecretUpdate(form.pushplus_token)) {
      payload.pushplus_token = form.pushplus_token;
    }
    if (isSecretUpdate(form.pushplus_smtp_password)) {
      payload.pushplus_smtp_password = form.pushplus_smtp_password;
    } else if (isSecretUpdate(form.smtp_password)) {
      payload.smtp_password = form.smtp_password;
    }
    const res = await testPushPlusNotification(payload);
    toast(res.message || "测试推送发送成功");
  } catch (err) {
    toast(err.message, "err");
  } finally {
    testingPushplus.value = false;
  }
}

// ---------- 分类 ----------
watch(() => newCat.name, (v) => {
  // 清空输入时直接清空错误，避免添加成功后立刻出现“请输入分类名称”
  nameErr.value = v ? (validateCat(v) || "") : "";
});

async function addCategory() {
  const err = validateCat(newCat.name);
  if (err) {
    nameErr.value = err;
    return toast(err, "err");
  }
  if (adding.value) return;
  adding.value = true;
  try {
    await createCategory({ name: newCat.name.trim() });
    newCat.name = "";
    nameErr.value = "";
    toast("分类已添加");
    cats.value = await getCategories();
  } catch (err) {
    toast(err.message, "err");
  } finally {
    adding.value = false;
  }
}

async function removeCategory(id, name) {
  if (!confirm(`确定删除分类「${name}」？（关联订阅将保留为未分类）`)) return;
  try {
    await deleteCategory(id);
    toast("已删除");
    cats.value = await getCategories();
  } catch (err) {
    toast(err.message, "err");
  }
}

// ---------- 备份 ----------

function doExportCsv() { download("/export/csv", "subscriptions.csv"); }

function doDownloadTemplate() {
  download("/backup/import-template", "import_template.csv");
}

async function onImportFile(kind, event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const text = await file.text();
    const r = await importCsv(text);
    const failed = (r.failed_rows || []).length;
    toast(
      `导入完成：新增 ${r.success_count}，跳过重复 ${r.skipped_duplicates}` +
        (failed ? `，失败 ${failed}` : ""),
    );
    cats.value = await getCategories();
  } catch (err) {
    toast(err.message, "err");
  } finally {
    if (event.target) event.target.value = "";
  }
}

onMounted(loadAll);
</script>

<template>
  <div class="page settings-page">
    <!-- 子页面导航栏 -->
    <div class="settings-tabs-nav">
      <button
        v-for="t in TABS"
        :key="t.key"
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === t.key }"
        @click="activeTab = t.key"
      >
        <span class="tab-icon" aria-hidden="true">
          <svg v-if="t.svg" class="tab-item-icon" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true">
            <path v-for="(d, i) in t.svg" :key="i" :d="d" />
          </svg>
          <template v-else>{{ t.icon }}</template>
        </span>
        <span class="tab-label">{{ t.label }}</span>
      </button>
    </div>

    <!-- 子页面 1：常规设置 -->
    <div v-show="activeTab === 'general'" class="settings-section">
      <div class="card">
        <h3>通用与汇率</h3>
        <div class="field">
          <span>默认货币</span>
          <CustomSelect
            v-model="form.default_currency"
            :options="CURRENCY_OPTIONS"
            :clearable="false"
          />
        </div>
        <div class="form-row">
          <label class="field">
            <span>USD → CNY 汇率</span>
            <input v-model="form.exchange_rate_usd" type="number" step="0.0001" min="0" />
          </label>
          <label class="field">
            <span>HKD → CNY 汇率</span>
            <input v-model="form.exchange_rate_hkd" type="number" step="0.0001" min="0" />
          </label>
        </div>
      </div>

      <div class="card">
        <h3>提醒偏好</h3>
        <label class="field checkbox">
          <input v-model="form.notification_enabled" type="checkbox" />
          <span>启用到期提醒</span>
        </label>
        <label class="field">
          <span>到期提醒提前天数</span>
          <input v-model="form.notification_days" type="number" min="0" max="90" />
        </label>
        <div class="field dnd">
          <span>免打扰时段</span>
          <div class="dnd-inputs">
            <CustomTimePicker v-model="form.do_not_disturb_start" placeholder="开始时间" />
            <span class="dnd-separator">—</span>
            <CustomTimePicker v-model="form.do_not_disturb_end" placeholder="结束时间" />
          </div>
        </div>
        <div class="sub-hint-row">
          <div class="muted sub-hint">更改后自动生效并保存</div>
          <span v-if="saveStatusText && saveScopes.has('general')" class="save-status-badge" :class="{ saving }">{{ saveStatusText }}</span>
        </div>
      </div>
    </div>

    <!-- 子页面 2：通知渠道 -->
    <div v-show="activeTab === 'notifications'" class="settings-section">
      <div class="card">
        <div class="section-header">
          <h3>邮件通知 (SMTP)</h3>
          <label class="field checkbox switch-box">
            <input v-model="form.email_enabled" type="checkbox" />
            <span>启用</span>
          </label>
        </div>
        <Transition name="ch-collapse">
          <div v-if="form.email_enabled" class="fields-group">
            <div class="form-row">
              <label class="field flex-2">
                <span>SMTP 服务器</span>
                <input v-model="form.smtp_host" placeholder="smtp.example.com" />
              </label>
              <label class="field flex-1">
                <span>SMTP 端口</span>
                <input v-model="form.smtp_port" placeholder="465" />
              </label>
            </div>
            <div class="form-row">
              <label class="field">
                <span>用户名</span>
                <input v-model="form.smtp_username" />
              </label>
              <label class="field">
                <span>密码 / 授权码</span>
                <input
                  v-model="form.smtp_password"
                  type="password"
                  autocomplete="new-password"
                  :placeholder="form.smtp_password_configured ? '已配置，留空保持原密码' : '输入 SMTP 密码 / 授权码'"
                />
              </label>
            </div>
            <label class="field">
              <span>发件人地址</span>
              <input v-model="form.smtp_from_address" placeholder="user@example.com" />
            </label>
            <div class="test-row">
              <label class="field test-target-field">
                <span>测试收件邮箱（选填，默认同发件人/用户名）</span>
                <input v-model="testEmailTarget" placeholder="test@example.com" />
              </label>
              <button
                type="button"
                class="btn test-btn"
                :disabled="testingEmail || (!form.smtp_host && !form.smtp_username)"
                @click="testEmail"
              >
                {{ testingEmail ? "发送中..." : "" }}
                <svg v-if="!testingEmail" class="test-btn-icon" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true"><path d="M874.666667 181.333333H149.333333c-40.533333 0-74.666667 34.133333-74.666666 74.666667v512c0 40.533333 34.133333 74.666667 74.666666 74.666667h725.333334c40.533333 0 74.666667-34.133333 74.666666-74.666667V256c0-40.533333-34.133333-74.666667-74.666666-74.666667z m-725.333334 64h725.333334c6.4 0 10.666667 4.266667 10.666666 10.666667v25.6L512 516.266667l-373.333333-234.666667V256c0-6.4 4.266667-10.666667 10.666666-10.666667z m725.333334 533.333334H149.333333c-6.4 0-10.666667-4.266667-10.666666-10.666667V356.266667l356.266666 224c4.266667 4.266667 10.666667 4.266667 17.066667 4.266666s12.8-2.133333 17.066667-4.266666l356.266666-224V768c0 6.4-4.266667 10.666667-10.666666 10.666667z"/></svg>
                <span>发送测试邮件</span>
              </button>
            </div>
            <div class="sub-hint-row">
              <div class="muted sub-hint">更改后自动生效并保存</div>
              <span v-if="saveStatusText && saveScopes.has('smtp')" class="save-status-badge" :class="{ saving }">{{ saveStatusText }}</span>
            </div>
          </div>
        </Transition>
      </div>

      <div class="card">
        <div class="section-header">
          <h3>PushPlus 微信推送</h3>
          <label class="field checkbox switch-box">
            <input v-model="form.pushplus_enabled" type="checkbox" />
            <span>启用</span>
          </label>
        </div>
        <Transition name="ch-collapse">
          <div v-if="form.pushplus_enabled" class="channel-body">
            <div class="fields-group">
              <label class="field">
                <span>PushPlus Token</span>
                <input
                  v-model="form.pushplus_token"
                  autocomplete="off"
                  spellcheck="false"
                  @focus="onPushplusFocus"
                  @input="onPushplusInput"
                  :placeholder="form.pushplus_token_configured ? '已配置 Token（星号数量与 Token 长度一致）' : '填写从 pushplus.plus 获取的一对一或群组 Token'"
                />
              </label>
              <details class="smtp-details">
                <summary>邮件推送配置（可选，用于通过邮件发送到 PushPlus）</summary>
                <div class="fields-group smtp-fields">
                  <div class="muted sub-hint">如需通过邮件方式发送到 PushPlus，请填写以下配置。留空则使用 HTTP API 方式。</div>
                  <div class="form-row">
                    <label class="field flex-2">
                      <span>SMTP 服务器</span>
                      <input v-model="form.pushplus_smtp_host" placeholder="留空则使用通用 SMTP 配置" />
                    </label>
                    <label class="field flex-1">
                      <span>SMTP 端口</span>
                      <input v-model="form.pushplus_smtp_port" placeholder="465" />
                    </label>
                  </div>
                  <div class="form-row">
                    <label class="field">
                      <span>用户名</span>
                      <input v-model="form.pushplus_smtp_username" />
                    </label>
                    <label class="field">
                      <span>密码 / 授权码</span>
                      <input
                        v-model="form.pushplus_smtp_password"
                        type="password"
                        autocomplete="new-password"
                        :placeholder="form.pushplus_smtp_password_configured ? '已配置，留空保持原密码' : '输入 SMTP 密码 / 授权码'"
                      />
                    </label>
                  </div>
                  <label class="field">
                    <span>发件人地址</span>
                    <input v-model="form.pushplus_smtp_from_address" placeholder="user@example.com" />
                  </label>
                </div>
              </details>
              <div class="test-row single-action">
                <button
                  type="button"
                  class="btn test-btn"
                  :disabled="testingPushplus || (!form.pushplus_token && !form.pushplus_token_configured)"
                  @click="testPushPlus"
                >
                  {{ testingPushplus ? "发送中..." : "" }}
                  <svg v-if="!testingPushplus" class="test-btn-icon" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true"><path d="M746.666667 949.333333H277.333333c-40.533333 0-74.666667-34.133333-74.666666-74.666666V149.333333c0-40.533333 34.133333-74.666667 74.666666-74.666666h469.333334c40.533333 0 74.666667 34.133333 74.666666 74.666666v725.333334c0 40.533333-34.133333 74.666667-74.666666 74.666666z m-469.333334-810.666666c-6.4 0-10.666667 4.266667-10.666666 10.666666v725.333334c0 6.4 4.266667 10.666667 10.666666 10.666666h469.333334c6.4 0 10.666667-4.266667 10.666666-10.666666V149.333333c0-6.4-4.266667-10.666667-10.666666-10.666666H277.333333z"/><path d="M512 768m-42.666667 0a42.666667 42.666667 0 1 0 85.333334 0 42.666667 42.666667 0 1 0-85.333334 0Z"/><path d="M597.333333 245.333333h-170.666666c-17.066667 0-32-14.933333-32-32s14.933333-32 32-32h170.666666c17.066667 0 32 14.933333 32 32s-14.933333 32-32 32z"/></svg>
                  <span>发送测试消息</span>
                </button>
              </div>
            </div>
            <div class="sub-hint-row">
              <div class="muted sub-hint">更改后自动生效并保存</div>
              <span v-if="saveStatusText && saveScopes.has('pushplus')" class="save-status-badge" :class="{ saving }">{{ saveStatusText }}</span>
            </div>
          </div>
        </Transition>
      </div>
    </div>

    <!-- 子页面 3：分类管理 -->
    <div v-show="activeTab === 'categories'" class="settings-section">
      <div class="card">
        <h3>新增分类</h3>
        <div class="cat-editor">
          <input
            v-model="newCat.name"
            type="text"
            maxlength="20"
            :aria-invalid="!!nameErr"
            placeholder="分类名称，如：流媒体、云服务"
          />
          <button class="btn btn-primary" :disabled="!CAN_ADD_CAT" @click="addCategory">{{ adding ? '添加中...' : '添加分类' }}</button>
        </div>
        <div v-if="nameErr" class="field-err">{{ nameErr }}</div>
        <div class="muted sub-hint" style="margin-top:6px">最多{{ MAX_CAT_COUNT }}个</div>
      </div>

      <div class="card">
        <h3>现有分类 ({{ cats.length }})</h3>
        <div class="cat-list">
          <span v-for="c in cats" :key="c.id" class="cat-chip">
            <span class="chip-name">{{ c.name }}</span>
            <button :title="`删除分类 ${c.name}`" @click="removeCategory(c.id, c.name)"><svg width="11" height="11" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true"><path d="M556.8 512L832 236.8c12.8-12.8 12.8-32 0-44.8-12.8-12.8-32-12.8-44.8 0L512 467.2l-275.2-277.333333c-12.8-12.8-32-12.8-44.8 0-12.8 12.8-12.8 32 0 44.8l275.2 277.333333-277.333333 275.2c-12.8 12.8-12.8 32 0 44.8 6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466667-8.533333L512 556.8 787.2 832c6.4 6.4 14.933333 8.533333 23.466667 8.533333s17.066667-2.133333 23.466666-8.533333c12.8-12.8 12.8-32 0-44.8L556.8 512z"/></svg></button>
          </span>
          <span v-if="!cats.length" class="muted">暂无分类</span>
        </div>
      </div>
    </div>

    <!-- 子页面 4：数据与备份 -->
    <div v-show="activeTab === 'backup'" class="settings-section">
      <div class="card">
        <h3>数据与备份</h3>
        <p class="muted">
          数据保存在本机 SQLite，支持 CSV 导入导出。先「下载导入模板」，
          按模板内的填写说明填好数据后「导入 CSV」。
        </p>
        <div class="backup-actions">
          <button class="btn" @click="doDownloadTemplate">下载导入模板</button>
          <button class="btn" @click="doExportCsv">导出 CSV</button>
          <label class="btn file-btn">导入 CSV
            <input type="file" accept=".csv" hidden @change="onImportFile('csv', $event)" />
          </label>
        </div>
      </div>
    </div>

    <!-- 子页面 5：运行日志 -->
    <div v-show="activeTab === 'logs'" class="settings-section">
      <div class="card">
        <div class="section-header">
          <h3>运行日志</h3>
          <button class="btn btn-sm" :disabled="logLoading" @click="loadLogTail">
            {{ logLoading ? "加载中…" : "刷新" }}
          </button>
        </div>
        <p class="muted">
          最近 {{ LOG_LINES }} 行（{{ logFile || "app.log" }}）。日志按大小轮转（单文件 2MB，保留 5 份），
          超过 30 天自动清理。
        </p>
        <pre v-if="logLines.length" class="log-view">{{ logLines.join("\n") }}</pre>
        <div v-else-if="logError" class="empty">加载失败：{{ logError }}</div>
        <div v-else-if="logLoading" class="empty">加载中…</div>
        <div v-else class="empty">暂无日志</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* 子页面切换选项卡导航 */
.settings-tabs-nav {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  background: var(--bg-2);
  border: 1px solid var(--border);
  padding: 4px;
  border-radius: var(--radius-md);
  margin-bottom: var(--space-2);
  overflow-x: auto;
}
.tab-btn {
  flex: 1 1 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-width: 100px;
  padding: 8px 14px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  color: var(--muted);
  font-size: var(--fs-sm);
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s ease;
}
.tab-btn:hover {
  color: var(--text);
  background: var(--card);
}
.tab-btn.active {
  background: var(--card);
  color: var(--text);
  border-color: var(--border);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}
.tab-icon {
  font-size: 15px;
  line-height: 1;
}
.tab-item-icon {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
}

/* 子页面内容容器 */
.settings-section {
  display: flex;
  flex-direction: column;
}

/* 表单与布局 */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}
.section-header h3 {
  margin: 0;
}
.switch-box {
  margin-bottom: 0;
}

.form-row {
  display: flex;
  gap: var(--space-3);
}
.form-row .field {
  flex: 1;
}
.form-row .flex-2 {
  flex: 2;
}
.form-row .flex-1 {
  flex: 1;
}

.fields-group {
  transition: opacity 0.2s ease;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: var(--space-3);
}
.field span {
  color: var(--muted);
  font-size: var(--fs-xs);
}
.field.checkbox {
  flex-direction: row;
  align-items: center;
  gap: var(--space-2);
}
.field.checkbox span {
  color: var(--text);
  font-size: var(--fs-sm);
}
.dnd-inputs {
  display: flex;
  gap: 8px;
  align-items: center;
}
.dnd-inputs :deep(.custom-time-picker) {
  flex: 1;
  min-width: 0;
}
.dnd-separator {
  color: var(--muted);
  flex-shrink: 0;
  font-size: var(--fs-sm);
}

.sub-hint-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: var(--space-2);
}
.sub-hint {
  font-size: var(--fs-xs);
}
.save-status-badge {
  font-size: var(--fs-xs);
  color: var(--primary);
  font-weight: 500;
  transition: opacity 0.2s ease;
}
.save-status-badge.saving {
  color: var(--muted);
}

.test-row {
  display: flex;
  align-items: flex-end;
  gap: var(--space-3);
  margin-top: var(--space-1);
}
.test-row.single-action {
  justify-content: flex-start;
}
.test-target-field {
  flex: 1;
  margin-bottom: 0;
}
.test-btn {
  white-space: nowrap;
  height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.test-btn-icon {
  width: 14px;
  height: 14px;
}

/* 分类管理 */
.field-err {
  color: var(--red, #ef4444);
  font-size: var(--fs-xs);
  margin-top: 6px;
}
.cat-editor {
  display: flex;
  gap: var(--space-2);
  margin-top: 6px;
}
.cat-editor input[type="text"] {
  flex: 1;
}
.cat-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: 4px;
}
.cat-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: var(--space-1) var(--space-3);
  font-size: var(--fs-sm);
}
.cat-chip button {
  background: none;
  border: none;
  color: var(--muted);
  cursor: pointer;
  padding: 0 0 0 var(--space-1);
}
.cat-chip button:hover {
  color: var(--red);
}

/* 备份与数据 */
.backup-actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin: var(--space-3) 0 var(--space-2);
}
.file-btn {
  display: inline-block;
  position: relative;
}
.btn.btn-sm {
  padding: 4px 10px;
  font-size: var(--fs-xs);
}
.btn-danger {
  background: var(--red);
  border-color: var(--red);
  color: #fff;
}
.btn-danger:hover:not(:disabled) { filter: brightness(0.92); }
.btn-danger:disabled { opacity: 0.6; cursor: not-allowed; }
.modal-confirm { width: 420px; }
.confirm-body { padding: 4px 0 2px; }
.confirm-text {
  margin: 0;
  font-size: var(--fs-sm);
  line-height: 1.6;
  color: var(--text);
  word-break: break-all;
}
.confirm-text strong { color: var(--text); font-weight: 600; }

@media (max-width: 640px) {
  .form-row {
    flex-direction: column;
    gap: 0;
  }
  .cat-editor {
    flex-direction: column;
  }
}
/* 通知渠道启用/关闭的内容折叠过渡 */
.ch-collapse-enter-active,
.ch-collapse-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.ch-collapse-enter-from,
.ch-collapse-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* 运行日志展示区 */
.log-view {
  margin: 0;
  padding: 12px;
  max-height: 420px;
  overflow-y: auto;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-all;
  scrollbar-width: thin;
}

/* PushPlus SMTP 配置折叠区域 */
.smtp-details {
  margin-top: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.smtp-details summary {
  padding: var(--space-2) var(--space-3);
  background: var(--card-2);
  cursor: pointer;
  font-size: var(--fs-sm);
  color: var(--muted);
  user-select: none;
}
.smtp-details summary:hover {
  color: var(--text);
}
.smtp-details[open] summary {
  border-bottom: 1px solid var(--border);
}
.smtp-fields {
  padding: var(--space-3);
  background: var(--card);
}
.smtp-fields .sub-hint {
  margin-bottom: var(--space-2);
}

</style>
