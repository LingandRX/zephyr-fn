import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 统一网关前缀（须与 app/ui/config 的 gatewayPrefix 一致）
const GATEWAY_PREFIX = "/app/subscription";

// base 按模式区分：
//   dev   = "/"             → 避免 proxy 吞掉 Vite 自身模块请求（vite6 下带前缀会被转发到后端）
//   build = GATEWAY_PREFIX  → 构建产物路径对齐网关前缀，真机/后端零改动
// 官方示例 (examples/native.md) 采用 constant base=前缀 + 全前缀 proxy，
// 该写法在 Vite 6 的 dev 模式会冲突，故本骨架改为上述稳健方案。
export default defineConfig(({ command }) => ({
  plugins: [vue()],
  base: command === "build" ? `${GATEWAY_PREFIX}/` : "/",
  server: {
    port: 5173,
    // 仅代理 API 到 Python 后端（TCP 模式后端直接接受 /api/... 路径；
    // 真机则由网关注入前缀后转发，后端 _normalize_path 剥离前缀，两者等效）
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${process.env.BACKEND_PORT || 5001}`,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
}));
