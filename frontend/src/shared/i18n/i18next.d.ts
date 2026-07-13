import 'i18next'

declare module 'i18next' {
  interface CustomTypeOptions {
    // Disable strict key typing so multi-namespace `ns:key` and dynamic keys typecheck.
    // Locale JSON under shared/i18n/namespaces remains the source of truth at runtime.
    returnNull: false
  }
}
