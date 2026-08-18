<script setup>
// 设置视图：常规 / 通知渠道 / 分类管理 / 备份与数据
// 移植自 vanilla app.js renderSettings / saveSettings / loadBackupFiles
import { ref, reactive, computed, watch, onMounted } from "vue";
import {
  getSettings, saveSettings, getCategories, createCategory, deleteCategory,
  backupNow, getBackupFiles, importJson, importCsv, download, api,
} from "../api.js";
import { toast } from "../ui.js";

const loaded = ref(false);
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
  smtp_from_address: "",
  pushplus_enabled: false,
  pushplus_token: "",
});

const newCat = reactive({ name: "", icon: "" });

const CAN_ADD_CAT = computed(() => newCat.name.trim().length > 0);

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
      smtp_password: s.smtp_password || "",
      smtp_from_address: s.smtp_from_address || "",
      pushplus_enabled: !!s.pushplus_enabled,
      pushplus_token: s.pushplus_token || "",
    });
    cats.value = c;
    backupFiles.value = files;
    loaded.value = true;
  } catch (err) {
    toast(err.message, "err");
  }
}

// 延迟自动保存（与 vanilla 的 change 事件 debounce 行为一致）
let saveTimer = null;
watch(
  form,
  () => {
    if (!loaded.value) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(async () => {
      try {
        await saveSettings({
          ...form,
          exchange_rate_usd: parseFloat(form.exchange_rate_usd) || 7.2,
          exchange_rate_hkd: parseFloat(form.exchange_rate_hkd) || 0.92,
          notification_days: parseInt(form.notification_days, 10) || 3,
          smtp_port: form.smtp_port ? parseInt(form.smtp_port, 10) : null,
          do_not_disturb_start: form.do_not_disturb_start || null,
          do_not_disturb_end: form.do_not_disturb_end || null,
          smtp_host: form.smtp_host || null,
          smtp_username: form.smtp_username || null,
          smtp_password: form.smtp_password || null,
          smtp_from_address: form.smtp_from_address || null,
          pushplus_token: form.pushplus_token || null,
        });
        toast("设置已保存");
      } catch (err) {
        toast(err.message, "err");
      }
    }, 400);
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
  <div class="page">
    <div class="grid-2">
      <!-- 常规 -->
      <div class="card">
        <h3>常规</h3>
        <label class="field">
          <span>默认货币</span>
          <select v-model="form.default_currency">
            <option value="CNY">CNY (¥)</option>
            <option value="USD">USD ($)</option>
            <option value="HKD">HKD (HK$)</option>
          </select>
        </label>
        <label class="field">
          <span>USD → CNY 汇率</span>
          <input v-model="form.exchange_rate_usd" type="number" step="0.0001" min="0" />
        </label>
        <label class="field">
          <span>HKD → CNY 汇率</span>
          <input v-model="form.exchange_rate_hkd" type="number" step="0.0001" min="0" />
        </label>
        <label class="field">
          <span>到期提醒提前天数</span>
          <input v-model="form.notification_days" type="number" min="0" max="90" />
        </label>
        <label class="field checkbox">
          <input v-model="form.notification_enabled" type="checkbox" />
          <span>启用到期提醒</span>
        </label>
        <div class="field dnd">
          <span>免打扰时段</span>
          <div class="dnd-inputs">
            <input v-model="form.do_not_disturb_start" type="time" />
            <span>—</span>
            <input v-model="form.do_not_disturb_end" type="time" />
          </div>
        </div>
      </div>

      <!-- 通知渠道 -->
      <div class="card">
        <h3>通知渠道</h3>
        <label class="field checkbox">
          <input v-model="form.email_enabled" type="checkbox" />
          <span>邮件通知 (SMTP)</span>
        </label>
        <label class="field"><span>SMTP 服务器</span><input v-model="form.smtp_host" placeholder="smtp.example.com" /></label>
        <label class="field"><span>SMTP 端口</span><input v-model="form.smtp_port" placeholder="465" /></label>
        <label class="field"><span>用户名</span><input v-model="form.smtp_username" /></label>
        <label class="field"><span>密码 / 授权码</span><input v-model="form.smtp_password" type="password" /></label>
        <label class="field"><span>发件人地址</span><input v-model="form.smtp_from_address" placeholder="user@example.com" /></label>
        <hr class="sep" />
        <label class="field checkbox">
          <input v-model="form.pushplus_enabled" type="checkbox" />
          <span>PushPlus 微信推送</span>
        </label>
        <label class="field"><span>PushPlus Token</span><input v-model="form.pushplus_token" /></label>
      </div>
    </div>

    <!-- 分类管理 -->
    <div class="card">
      <h3>分类管理</h3>
      <div class="cat-editor">
        <input v-model="newCat.name" type="text" placeholder="新分类名称" @keyup.enter="addCategory" />
        <input v-model="newCat.icon" type="text" placeholder="图标 emoji，如 📺" class="cat-icon" />
        <button class="btn btn-primary" :disabled="!CAN_ADD_CAT" @click="addCategory">添加</button>
      </div>
      <div class="cat-list">
        <span v-for="c in cats" :key="c.id" class="cat-chip">
          {{ c.icon || "" }} {{ c.name }}
          <button :title="`删除分类 ${c.name}`" @click="removeCategory(c.id, c.name)">✕</button>
        </span>
        <span v-if="!cats.length" class="muted">暂无分类</span>
      </div>
    </div>

    <!-- 备份与数据 -->
    <div class="card">
      <h3>备份与数据</h3>
      <p class="muted">
        数据保存在本机 SQLite。每日自动导出 JSON + 数据库副本到共享目录
        <code>subscription/backups</code>，保留最近 14 份。
      </p>
      <div class="backup-actions">
        <button class="btn" @click="doBackupNow">立即备份</button>
        <button class="btn" @click="doExportJson">导出 JSON</button>
        <button class="btn" @click="doExportCsv">导出 CSV</button>
        <label class="btn file-btn">导入 JSON
          <input type="file" accept=".json" hidden @change="onImportFile('json', $event)" />
        </label>
        <label class="btn file-btn">导入 CSV
          <input type="file" accept=".csv" hidden @change="onImportFile('csv', $event)" />
        </label>
      </div>
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
      <div class="muted" id="save-hint">修改后自动保存</div>
    </div>
  </div>
</template>

<style scoped>
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-4); }
.field { display: flex; flex-direction: column; gap: 5px; margin-bottom: var(--space-3); }
.field span { color: var(--muted); font-size: var(--fs-xs); }
.field.checkbox { flex-direction: row; align-items: center; gap: var(--space-2); }
.field.checkbox span { color: var(--text); font-size: var(--fs-sm); }
.dnd-inputs { display: flex; gap: 6px; align-items: center; }
.sep { border: none; border-top: 1px solid var(--border); margin: var(--space-4) 0; }
.cat-editor { display: flex; gap: var(--space-2); margin-bottom: 10px; }
.cat-editor input[type="text"] { flex: 1; }
.cat-editor .cat-icon { flex: 0 0 90px; }
.cat-list { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.cat-chip {
  display: inline-flex; align-items: center; gap: 6px; background: var(--card-2);
  border: 1px solid var(--border); border-radius: 20px; padding: var(--space-1) var(--space-3);
  font-size: var(--fs-sm);
}
.cat-chip button { background: none; border: none; color: var(--muted); cursor: pointer; padding: 0 0 0 var(--space-1); }
.cat-chip button:hover { color: var(--red); }
.backup-actions { display: flex; gap: var(--space-2); flex-wrap: wrap; margin-bottom: var(--space-3); }
.file-btn { display: inline-block; position: relative; }
.backup-table { min-width: 320px; }
#save-hint { margin-top: var(--space-2); }

@media (max-width: 860px) {
  .grid-2 { grid-template-columns: minmax(0, 1fr); }
}
</style>