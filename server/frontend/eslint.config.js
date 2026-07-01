import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'

export default [
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    languageOptions: {
      globals: {
        window: 'readonly',
        document: 'readonly',
        localStorage: 'readonly',
        console: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        Audio: 'readonly',
        atob: 'readonly',
        btoa: 'readonly',
        fetch: 'readonly',
        alert: 'readonly',
        confirm: 'readonly',
        URLSearchParams: 'readonly',
        navigator: 'readonly',
        IntersectionObserver: 'readonly',
        sessionStorage: 'readonly',
        FormData: 'readonly',
      }
    },
    rules: {
      // Disable formatting rules - not ESLint's job
      'vue/multi-word-component-names': 'off',
      'vue/html-self-closing': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/multiline-html-element-content-newline': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/first-attribute-linebreak': 'off',
      'vue/html-closing-bracket-newline': 'off',
      'vue/html-closing-bracket-spacing': 'off',
      'vue/html-indent': 'off',
      'vue/attribute-hyphenation': 'off',
      'vue/v-on-event-hyphenation': 'off',
      'vue/attributes-order': 'off',
      // Allow v-html (used for SVG icons)
      'vue/no-v-html': 'off',
      // Warn on unused vars, ignore _prefixed
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      // Allow empty catch blocks
      'no-empty': ['error', { allowEmptyCatch: true }],
    }
  }
]
