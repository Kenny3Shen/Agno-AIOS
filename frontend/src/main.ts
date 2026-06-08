import { createApp } from "vue"
import ElementPlus from "element-plus"
import zhCn from "element-plus/es/locale/lang/zh-cn"
import "element-plus/dist/index.css"
import "element-plus/theme-chalk/dark/css-vars.css"
import "highlight.js/styles/github-dark.css"
import "virtual:uno.css"
import "./style.css"
import App from "./App.vue"
import * as ElementPlusIconsVue from "@element-plus/icons-vue"

const app = createApp(App)

// Use Element Plus with Chinese locale by default
app.use(ElementPlus, { locale: zhCn })

// Ensure the document is marked as Chinese
document.documentElement.lang = "zh-CN"

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.mount("#app")
