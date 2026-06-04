import type { Config } from 'tailwindcss';

// Tokens mirror docs/design/COLOR_SYSTEM.md §2-§5.
// Any change here must update the COLOR_SYSTEM.md table in the same PR.
const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
    './.storybook/**/*.{ts,tsx}',
    './components/**/*.stories.{ts,tsx}',
    './app/**/*.stories.{ts,tsx}'
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#147A73',
          primary: '#147A73',
          primaryFg: '#FFFFFF',
          ink: '#0D1B2A',
          copy: '#48606A',
          surface: '#F7FBFA',
          surfaceAlt: '#FFFFFF',
          border: '#D9E3E1',
          cta: '#F26B4F',
          ctaFg: '#1A0F0B',
          professional: '#153B5C',
          professionalFg: '#FFFFFF',
          fg: '#FFFFFF'
        },
        content: {
          DEFAULT: '#0D1B2A',
          muted: '#48606A',
          subtle: '#6F8088',
          link: '#147A73',
          linkHover: '#0F5F59'
        },
        status: {
          success: '#1B7F46',
          successFg: '#FFFFFF',
          successSurface: '#E8F5EE',
          danger: '#C0392B',
          dangerFg: '#FFFFFF',
          dangerSurface: '#FBEAE8',
          warning: '#995D00',
          warningFg: '#FFFFFF',
          warningSurface: '#FFF3E0',
          info: '#1F6F8B',
          infoFg: '#FFFFFF',
          infoSurface: '#E8F1F5'
        },
        notice: {
          legal: '#48606A'
        }
      }
    }
  },
  plugins: []
};

export default config;
