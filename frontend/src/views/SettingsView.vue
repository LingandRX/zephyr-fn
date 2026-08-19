<script setup>
// 设置视图：常规 / 通知渠道 / 分类管理 / 备份与数据
// 支持子页面（Tabs）切换展示
import { ref, reactive, computed, watch, nextTick, onMounted } from "vue";
import {
  getSettings, saveSettings, getCategories, createCategory, deleteCategory,
  backupNow, getBackupFiles, importJson, importCsv, download,
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

const form = reactive({
  default_currency: "CNY",
  exchange_rate_usd: 7.2,
  exchange_rate_hkd: 0.92,
  notification_days: 3,
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

const newCat = reactive({ name: "", icon: "" });

const CAN_ADD_CAT = computed(() => newCat.name.trim().length > 0);

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
      notification_days: s.notification_days ?? 3,
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
        const payload = {
          ...form,
          exchange_rate_usd: parseFloat(form.exchange_rate_usd) || 7.2,
          exchange_rate_hkd: parseFloat(form.exchange_rate_hkd) || 0.92,
          notification_days: parseInt(form.notification_days, 10) || 3,
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

// ---------- 分类 ----------
async function addCategory() {
  const name = newCat.name.trim();
  if (!name) return toast("请输入分类名称", "err");
  try {
    await createCategory({ name, icon: newCat.icon.trim() || null });
    newCat.name = "";
    newCat.icon = "";
    toast("分类已添加");
    cats.value = await getCategories();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function removeCategory(id, name) {
  if (!confirm(`确定删除分类「${name}」？（订阅保留为未分类）`)) return;
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
          <input v-model="newCat.name" type="text" placeholder="分类名称，如：流媒体、云服务" @keyup.enter="addCategory" />
          <input v-model="newCat.icon" type="text" placeholder="图标 emoji，如 📺" class="cat-icon" />
          <button class="btn btn-primary" :disabled="!CAN_ADD_CAT" @click="addCategory">添加分类</button>
        </div>
      </div>

      <div class="card">
        <h3>现有分类 ({{ cats.length }})</h3>
        <div class="cat-list">
          <span v-for="c in cats" :key="c.id" class="cat-chip">
            <span class="chip-icon">{{ c.icon || "🏷️" }}</span>
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
            <thead><tr><th>备份文件</th><th>大小</th></tr></thead>
            <tbody>
              <tr v-for="f in backupFiles" :key="f.name">
                <td>{{ f.name }}</td><td>{{ (f.size / 1024).toFixed(1) }} KB</td>
              </tr>
              <tr v-if="!backupFiles.length"><td colspan="2" class="muted">暂无备份</td></tr>
            </tbody>
          </table>
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

/* 分类管理 */
.cat-editor {
  display: flex;
  gap: var(--space-2);
  margin-top: 6px;
}
.cat-editor input[type="text"] {
  flex: 1;
}
.cat-editor .cat-icon {
  flex: 0 0 140px;
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
.chip-icon {
  font-size: 14px;
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
  min-width: 320px;
}

@media (max-width: 640px) {
  .form-row {
    flex-direction: column;
    gap: 0;
  }
  .cat-editor {
    flex-direction: column;
  }
  .cat-editor .cat-icon {
    flex: auto;
  }
}
</style>
