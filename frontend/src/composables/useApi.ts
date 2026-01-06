import { ref } from 'vue'
import axios from 'axios'
import type { CveSearchParams, CveSearchResponse, AssetSearchParams, AssetSearchResponse, ChatResponse, Url2MdParseResponse, UpdateResponse } from '../types'

const API_BASE = '/api'

/**
 * CVE 搜索 API
 */
export function useCveApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const searchCve = async (params: CveSearchParams): Promise<CveSearchResponse> => {
    loading.value = true
    error.value = null

    try {
      const response = await axios.post(`${API_BASE}/cve/search`, params)
      return response.data
    } catch (err: any) {
      error.value = err.response?.data?.message || err.message || '搜索失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  const updateDatabase = async (): Promise<UpdateResponse> => {
    loading.value = true
    error.value = null

    try {
      const response = await axios.post(`${API_BASE}/cve/update`)
      return response.data
    } catch (err: any) {
      error.value = err.response?.data?.message || err.message || '更新失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    searchCve,
    updateDatabase
  }
}

/**
 * 资产搜索 API
 */
export function useAssetApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const searchAsset = async (params: AssetSearchParams): Promise<AssetSearchResponse> => {
    loading.value = true
    error.value = null

    try {
      const response = await axios.post(`${API_BASE}/asset/search`, params)
      return response.data
    } catch (err: any) {
      error.value = err.response?.data?.message || err.message || '搜索失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    searchAsset
  }
}

/**
 * LLM 聊天 API
 */
export function useChatApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const sendMessage = async (message: string): Promise<ChatResponse> => {
    loading.value = true
    error.value = null

    try {
      const response = await axios.post(`${API_BASE}/chat`, { message })
      return response.data
    } catch (err: any) {
      error.value = err.response?.data?.message || err.message || '发送失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    sendMessage
  }
}

/**
 * URL2MD API
 */
export function useUrl2MdApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const parseUrl = async (url: string): Promise<Url2MdParseResponse> => {
    loading.value = true
    error.value = null

    try {
      const response = await axios.post(`${API_BASE}/url2md/parse`, { url })
      return response.data
    } catch (err: any) {
      error.value = err.response?.data?.message || err.message || '解析失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    parseUrl
  }
}
