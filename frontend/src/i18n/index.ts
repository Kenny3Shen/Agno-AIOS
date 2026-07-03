import { createI18n } from "vue-i18n"
import { enUS } from "./locales/en-US"
import { zhCN } from "./locales/zh-CN"
import type { LocaleCode } from "../stores/shell"

export const i18n = createI18n({
  legacy: false,
  locale: "zh-CN",
  fallbackLocale: "en-US",
  messages: {
    "zh-CN": zhCN,
    "en-US": enUS,
  },
})

export const setI18nLocale = (locale: LocaleCode) => {
  i18n.global.locale.value = locale
  document.documentElement.lang = locale
}
