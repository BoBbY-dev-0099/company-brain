import axios from "axios"

export type TokenGetter = (options?: { skipCache?: boolean }) => Promise<string | null>

let getTokenRef: TokenGetter | null = null

export function setAuthTokenGetter(getter: TokenGetter) {
  getTokenRef = getter
}

export const apiClient = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
})

apiClient.interceptors.request.use(async (config) => {
  if (getTokenRef) {
    // Always ask Clerk for a fresh token per request. Cached tokens can drift
    // ahead of the local clock and fail JWT iat verification on the backend.
    const token = await getTokenRef({ skipCache: true })
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
  }
  return config
})

export async function apiGet<T = any>(path: string, options?: any): Promise<T> {
  const res = await apiClient.get(path, options)
  return res.data
}

export async function apiPost<T = any>(path: string, body: any): Promise<T> {
  const res = await apiClient.post(path, body)
  return res.data
}

export async function apiDelete<T = any>(path: string, options?: any): Promise<T> {
  const res = await apiClient.delete(path, options)
  return res.data
}
