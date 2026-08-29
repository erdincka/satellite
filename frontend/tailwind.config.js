export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        hq:   { DEFAULT: '#6366f1', dim: '#4338ca' },
        edge: { DEFAULT: '#14b8a6', dim: '#0f766e' },
      },
      keyframes: {
        // Animate `left`, not `translateX`: a percentage translate is relative to the
        // dot's own width, so it crossed about a quarter of the lane. Percentages of
        // `left` are relative to the lane.
        travel: { '0%': { left: '-1.5rem', opacity: '0' },
                  '15%,85%': { opacity: '1' },
                  '100%': { left: '100%', opacity: '0' } },
        arrive: { '0%': { transform: 'scale(.92)', opacity: '0' },
                  '100%': { transform: 'scale(1)', opacity: '1' } },
      },
      animation: { travel: 'travel 2.4s linear infinite', arrive: 'arrive .28s ease-out' },
    },
  },
}
