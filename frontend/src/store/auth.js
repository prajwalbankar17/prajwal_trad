import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const useAuthStore = create(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      permissions: [],
      setTokens: (accessToken, refreshToken) => set({ accessToken, refreshToken }),
      setUser: (user) => set({ user }),
      setPermissions: (permissions) => set({ permissions }),
      logout: () =>
        set({ accessToken: null, refreshToken: null, user: null, permissions: [] }),
    }),
    { name: 'prajwal-auth' },
  ),
)

/** Permission check mirroring the backend: superuser passes everything. */
export function useHasPermission(code) {
  const user = useAuthStore((s) => s.user)
  const permissions = useAuthStore((s) => s.permissions)
  if (user?.is_superuser) return true
  return permissions.includes(code)
}
