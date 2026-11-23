import axios from 'axios'
import { useAuthStore } from '../store/auth'

export const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// A single in-flight refresh, shared by every 401 that arrives while it runs -
// otherwise ten parallel queries each rotate the refresh token and all but one
// get logged out.
let refreshPromise = null

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const { response, config } = error
    if (response?.status === 401 && !config?._retried) {
      const { refreshToken, setTokens, logout } = useAuthStore.getState()
      if (!refreshToken) {
        logout()
        return Promise.reject(error)
      }
      config._retried = true
      try {
        refreshPromise =
          refreshPromise ||
          axios.post('/api/v1/auth/refresh', { refresh_token: refreshToken })
        const { data } = await refreshPromise
        refreshPromise = null
        setTokens(data.access_token, data.refresh_token)
        config.headers.Authorization = `Bearer ${data.access_token}`
        return api(config)
      } catch (refreshError) {
        refreshPromise = null
        logout()
        return Promise.reject(refreshError)
      }
    }
    return Promise.reject(error)
  },
)

/** The backend always returns {code, message, details}; surface `message`. */
export function errorMessage(error, fallback = 'Something went wrong.') {
  return error?.response?.data?.message || error?.message || fallback
}

export function errorDetails(error) {
  return error?.response?.data?.details || null
}
