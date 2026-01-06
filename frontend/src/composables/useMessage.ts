import { ref } from 'vue'
import type { MessageType } from '../types'

export function useMessage() {
  const message = ref<MessageType | null>(null)

  const showMessage = (type: MessageType['type'], title: string, description?: string) => {
    message.value = { type, title, description }
  }

  const showSuccess = (title: string, description?: string) => {
    showMessage('success', title, description)
  }

  const showError = (title: string, description?: string) => {
    showMessage('error', title, description)
  }

  const showWarning = (title: string, description?: string) => {
    showMessage('warning', title, description)
  }

  const showInfo = (title: string, description?: string) => {
    showMessage('info', title, description)
  }

  const clear = () => {
    message.value = null
  }

  return {
    message,
    showMessage,
    showSuccess,
    showError,
    showWarning,
    showInfo,
    clear
  }
}
