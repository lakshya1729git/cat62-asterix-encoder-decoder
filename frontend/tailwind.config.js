/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,jsx,ts,tsx}',
  ],
  theme: {
    extend: {
      boxShadow: {
        'glow-blue': '0 0 40px 4px rgba(59, 130, 246, 0.25), 0 0 80px 8px rgba(37, 99, 235, 0.12)',
      },
      backgroundImage: {
        'space-gradient': 'radial-gradient(ellipse at 50% 0%, rgba(15,23,60,0.85) 0%, rgba(0,0,0,0.95) 60%, #000000 100%)',
      },
    },
  },
  plugins: [],
}
