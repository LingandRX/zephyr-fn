<script setup>
// 设置视图：常规 / 通知渠道 / 分类管理 / 备份与数据
// 支持子页面（Tabs）切换展示
import { ref, reactive, computed, watch, nextTick, onMounted } from "vue";
import {
  getSettings, saveSettings, getCategories, createCategory, deleteCategory,
  backupNow, getBackupFiles, importJson, importCsv, download,
  deleteBackupFile, downloadBackupFile,
  testEmailNotification, testPushPlusNotification,
} from "../api.js";
import { toast } from "../ui.js";

const TABS = [
  { key: "general", label: "常规设置", icon: "⚙️" },
  { key: "notifications", label: "通知渠道", icon: "🔔" },
  { key: "categories", label: "分类管理", icon: "🏷️" },
  { key: "backup", label: "数据与备份", icon: "💾" },
];

const activeTab = ref("general");
const loaded = ref(false);
const saving = ref(false);
const saveStatusText = ref("");
const cats = ref([]);
const backupFiles = ref([]);

const testingEmail = ref(false);
const testingPushplus = ref(false);
const testEmailTarget = ref("");

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

function isSecretUpdate(value) {
  const text = String(value ?? "").trim();
  if (!text) return false;
  if (/^(?:\*{3,}|[•·●]{3,})$/.test(text)) return false;
  if (/已配置|configured|redacted|masked/i.test(text)) return false;
  return true;
}

async function loadAll() {
  try {
    const [s, c, files] = await Promise.all([getSettings(), getCategories(), getBackupFiles()]);
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
      pushplus_token: "",
      pushplus_token_configured: !!s.pushplus_token_configured,
    });
    cats.value = c;
    backupFiles.value = files;
    await nextTick();
    loaded.value = true;
  } catch (err) {
    toast(err.message, "err");
  }
}

// 延迟自动保存（防抖 800ms，静默保存状态，避免频繁 toast 打扰）
let saveTimer = null;
let statusTimer = null;
watch(
  form,
  () => {
    if (!loaded.value) return;
    clearTimeout(saveTimer);
    saving.value = true;
    saveStatusText.value = "正在保存...";
    saveTimer = setTimeout(async () => {
      try {
        const smtpSecretDraft = isSecretUpdate(form.smtp_password);
        const pushplusSecretDraft = isSecretUpdate(form.pushplus_token);
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
        };
        // 密钥输入框为空或包含掩码时不发送字段，后端会保留现有密钥。
        delete payload.smtp_password;
        delete payload.pushplus_token;
        delete payload.smtp_password_configured;
        delete payload.pushplus_token_configured;
        if (smtpSecretDraft) payload.smtp_password = form.smtp_password;
        if (pushplusSecretDraft) payload.pushplus_token = form.pushplus_token;

        await saveSettings(payload);
        // 成功后清空前端草稿，降低密钥在页面内存中的停留时间；configured
        // 标志保留，用户仍能看到“已配置，留空保持”的提示。
        if (smtpSecretDraft) {
          form.smtp_password = "";
          form.smtp_password_configured = true;
        }
        if (pushplusSecretDraft) {
          form.pushplus_token = "";
          form.pushplus_token_configured = true;
        }
        saving.value = false;
        saveStatusText.value = "✓ 设置已保存";
        clearTimeout(statusTimer);
        statusTimer = setTimeout(() => {
          saveStatusText.value = "";
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
    const payload = {};
    if (isSecretUpdate(form.pushplus_token)) {
      payload.pushplus_token = form.pushplus_token;
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
async function doBackupNow() {
  try {
    const r = await backupNow();
    toast(`备份完成：${r.file} (${r.count} 条)`);
    backupFiles.value = await getBackupFiles();
  } catch (err) {
    toast(err.message, "err");
  }
}

function doExportJson() { download("/backup/export-json", "subscriptions.json"); }
function doExportCsv() { download("/export/csv", "subscriptions.csv"); }

const delBackupOpen = ref(false);
const delBackupTarget = ref("");
const delBackupBusy = ref(false);

function doDownloadBackup(name) {
  try {
    downloadBackupFile(name);
    toast("已开始下载");
  } catch (err) {
    toast(err.message, "err");
  }
}

function doDeleteBackup(name) {
  delBackupTarget.value = name;
  delBackupBusy.value = false;
  delBackupOpen.value = true;
}

function closeDeleteBackup() {
  if (delBackupBusy.value) return;
  delBackupOpen.value = false;
}

async function confirmDeleteBackup() {
  const name = delBackupTarget.value;
  if (!name || delBackupBusy.value) return;
  delBackupBusy.value = true;
  try {
    await deleteBackupFile(name);
    toast("备份已删除");
    delBackupOpen.value = false;
    backupFiles.value = await getBackupFiles();
  } catch (err) {
    toast(err.message, "err");
  } finally {
    delBackupBusy.value = false;
  }
}

async function onImportFile(kind, event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const text = await file.text();
    const r = kind === "json" ? await importJson(text) : await importCsv(text);
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
        <span class="tab-icon">{{ t.icon }}</span>
        <span class="tab-label">{{ t.label }}</span>
      </button>
    </div>

    <!-- 子页面 1：常规设置 -->
    <div v-show="activeTab === 'general'" class="settings-section">
      <div class="card">
        <h3>通用与汇率</h3>
        <label class="field">
          <span>默认货币</span>
          <select v-model="form.default_currency">
            <option value="CNY">CNY (¥)</option>
            <option value="USD">USD ($)</option>
            <option value="HKD">HKD (HK$)</option>
          </select>
        </label>
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
            <input v-model="form.do_not_disturb_start" type="time" />
            <span>—</span>
            <input v-model="form.do_not_disturb_end" type="time" />
          </div>
        </div>
        <div class="sub-hint-row">
          <div class="muted sub-hint">更改后自动生效并保存</div>
          <span v-if="saveStatusText" class="save-status-badge" :class="{ saving }">{{ saveStatusText }}</span>
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
        <div class="fields-group" :class="{ disabled: !form.email_enabled }">
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
              {{ testingEmail ? "发送中..." : "✉️ 发送测试邮件" }}
            </button>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="section-header">
          <h3>PushPlus 微信推送</h3>
          <label class="field checkbox switch-box">
            <input v-model="form.pushplus_enabled" type="checkbox" />
            <span>启用</span>
          </label>
        </div>
        <div class="fields-group" :class="{ disabled: !form.pushplus_enabled }">
          <label class="field">
            <span>PushPlus Token</span>
            <input
              v-model="form.pushplus_token"
              autocomplete="off"
              :placeholder="form.pushplus_token_configured ? '已配置，留空保持原 Token' : '填写从 pushplus.plus 获取的一对一或群组 Token'"
            />
          </label>
          <div class="test-row single-action">
            <button
              type="button"
              class="btn test-btn"
              :disabled="testingPushplus || (!form.pushplus_token && !form.pushplus_token_configured)"
              @click="testPushPlus"
            >
              {{ testingPushplus ? "发送中..." : "📲 发送测试消息" }}
            </button>
          </div>
        </div>
        <div class="sub-hint-row">
          <div class="muted sub-hint">更改后自动生效并保存</div>
          <span v-if="saveStatusText" class="save-status-badge" :class="{ saving }">{{ saveStatusText }}</span>
        </div>
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
            <button :title="`删除分类 ${c.name}`" @click="removeCategory(c.id, c.name)">✕</button>
          </span>
          <span v-if="!cats.length" class="muted">暂无分类</span>
        </div>
      </div>
    </div>

    <!-- 子页面 4：数据与备份 -->
    <div v-show="activeTab === 'backup'" class="settings-section">
      <div class="card">
        <h3>备份与数据管理</h3>
        <p class="muted">
          数据保存在本机 SQLite。每日自动导出 JSON + 数据库副本到共享目录
          <code>subscription/backups</code>，最多保留最近 5 份（超过自动删除）。
        </p>
        <div class="backup-actions">
          <button class="btn btn-primary" @click="doBackupNow">立即备份</button>
          <button class="btn" @click="doExportJson">导出 JSON</button>
          <button class="btn" @click="doExportCsv">导出 CSV</button>
          <label class="btn file-btn">导入 JSON
            <input type="file" accept=".json" hidden @change="onImportFile('json', $event)" />
          </label>
          <label class="btn file-btn">导入 CSV
            <input type="file" accept=".csv" hidden @change="onImportFile('csv', $event)" />
          </label>
        </div>
      </div>

      <div class="card">
        <h3>备份历史</h3>
        <div class="table-scroll">
          <table class="table backup-table">
            <thead><tr><th>备份文件</th><th>大小</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="f in backupFiles" :key="f.name">
                <td>{{ f.name }}</td><td>{{ (f.size / 1024).toFixed(1) }} KB</td>
                <td class="row-actions">
                  <button class="btn btn-sm" :title="`下载 ${f.name}`" @click="doDownloadBackup(f.name)">下载</button>
                  <button class="btn btn-sm btn-danger" :title="`删除 ${f.name}`" @click="doDeleteBackup(f.name)">删除</button>
                </td>
              </tr>
              <tr v-if="!backupFiles.length"><td colspan="3" class="muted">暂无备份</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 删除备份确认弹窗 -->
    <div v-if="delBackupOpen" class="modal" @click.self="closeDeleteBackup">
      <div class="modal-card modal-confirm">
        <div class="modal-head">
          <h2>删除备份</h2>
          <button class="modal-close" :disabled="delBackupBusy" @click="closeDeleteBackup">✕</button>
        </div>
        <div class="confirm-body">
          <p class="confirm-text">
            确认删除备份文件「<strong>{{ delBackupTarget }}</strong>」？此操作不可恢复。
          </p>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn" :disabled="delBackupBusy" @click="closeDeleteBackup">取消</button>
          <button type="button" class="btn btn-danger" :disabled="delBackupBusy" @click="confirmDeleteBackup">
            {{ delBackupBusy ? "删除中…" : "确认删除" }}
          </button>
        </div>
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
.fields-group.disabled {
  opacity: 0.55;
  pointer-events: none;
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
  gap: 6px;
  align-items: center;
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
.backup-table {
  min-width: 420px;
}
.backup-table .row-actions {
  display: flex;
  gap: var(--space-1);
  white-space: nowrap;
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
</style>
