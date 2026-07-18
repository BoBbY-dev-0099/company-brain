import axios from "axios"

export const apiClient = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
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
