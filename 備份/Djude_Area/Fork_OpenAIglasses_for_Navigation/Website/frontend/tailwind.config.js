/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{js,jsx,ts,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Noto Sans TC', 'sans-serif'],
      },
      colors: {
        // 品牌色系：深色科技風格（暗色模式使用）
        brand: {
          50:  '#edfcff',
          100: '#d6f7ff',
          200: '#b5f2ff',
          300: '#83ecff',
          400: '#48ddff',
          500: '#1ec4f7',
          600: '#07a3d7',
          700: '#0882ae',
          800: '#0f698f',
          900: '#135778',
          950: '#0a3750',
        },
        // 暖色品牌色系：亮色模式使用
        warm: {
          50:  '#fef9ee',
          100: '#fef0cd',
          200: '#fde6b6',
          300: '#fbd07b',
          400: '#fbab6a',
          500: '#f59e0b',
          600: '#f97d16',
          700: '#ef8108',
          800: '#d97704',
          900: '#c26604',
          950: '#92400b',
        },
      },
      animation: {
        'float': 'float 6s ease-in-out infinite',
        'pulse-slow': 'pulse 3s ease-in-out infinite',
        'fade-in-up': 'fadeInUp 0.6s ease-out forwards',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-20px)' },
        },
        fadeInUp: {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
