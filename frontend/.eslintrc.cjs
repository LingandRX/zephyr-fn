module.exports = {
  root: true,
  env: {
    browser: true,
    es2021: true,
    node: true,
  },
  extends: [
    "eslint:recommended",
    "plugin:vue/vue3-recommended",
  ],
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
  },
  ignorePatterns: ["dist/", "node_modules/"],
  rules: {
    "vue/multi-word-component-names": "off",
    "vue/no-unused-vars": "warn",
    "vue/max-attributes-per-line": "off",
    "vue/singleline-html-element-content-newline": "off",
    "vue/html-self-closing": "off",
    "vue/html-closing-bracket-spacing": "off",
    "vue/html-indent": "off",
    "vue/attributes-order": "off",
    "no-unused-vars": "warn",
    "no-console": "warn",
    "no-debugger": "warn",
  },
};
