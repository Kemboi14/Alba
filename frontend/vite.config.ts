import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  
  // Build into Django's static directory
  build: {
    outDir: '../loan_system/static/verification/',  // Output to Django static
    emptyOutDir: true,
    manifest: true,  // Generate manifest.json for Django
    rollupOptions: {
      input: {
        main: './src/main.tsx',  // Entry point
      },
      output: {
        entryFileNames: 'js/[name].js',
        chunkFileNames: 'js/[name].js',
        assetFileNames: (assetInfo) => {
          const info = assetInfo.name.split('.');
          const ext = info[info.length - 1];
          if (/\.(css)$/i.test(ext)) {
            return 'css/[name][extname]';
          }
          return 'assets/[name][extname]';
        },
      },
    },
  },
  
  // Development server (only used during dev, not production)
  server: {
    port: 5173,
    strictPort: true,
  },
  
  // Path aliases
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  
  // Optimize dependencies
  optimizeDeps: {
    exclude: ['tesseract.js', 'face-api.js'],
    include: ['react', 'react-dom', 'zustand', 'lucide-react'],
  },
});
