import { create } from 'zustand'

interface AppState {
  initData: string | null;
  setInitData: (data: string | null) => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
}

export const useAppStore = create<AppState>()((set) => ({
  initData: null,
  setInitData: (data) => set({ initData: data }),
  isLoading: false,
  setIsLoading: (loading) => set({ isLoading: loading }),
}))
