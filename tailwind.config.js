/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './apps/**/templates/**/*.html',
    './static/js/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        // Alba Capital Brand Colors
        primary: {
          50: '#fff5f2',
          100: '#ffe8e0',
          200: '#ffd4c7',
          300: '#ffb89f',
          400: '#ff9977',
          500: '#ff805d',  // Main brand color
          600: '#ff6943',
          700: '#e8562f',
          800: '#c24420',
          900: '#9e3518',
        },
        secondary: {
          50: '#f0f4f8',
          100: '#d9e2ec',
          200: '#bcccdc',
          300: '#9fb3c8',
          400: '#829ab1',
          500: '#627d98',
          600: '#486581',
          700: '#334e68',
          800: '#22354e',  // Alba Capital navy
          900: '#1a2940',
        },
        alba: {
          orange: '#ff805d',   // Primary brand color
          navy: '#22354e',     // Secondary brand color  
          light: '#fafbfb',    // Background color
        },
        sidebar: {
          bg: '#22354e',       // Alba Capital navy
          hover: '#334e68',
          active: '#ff805d',   // Alba Capital orange
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
}
