import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
    fileParallelism: false,
    restoreMocks: true,
    // A cold dependency cache can make the navigation suites exceed Vitest's
    // five-second default even though their assertions remain deterministic.
    testTimeout: 15_000,
  },
})
