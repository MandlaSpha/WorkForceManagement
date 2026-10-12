import prettier from 'eslint-config-prettier'
import pluginVue from 'eslint-plugin-vue'
import vueA11y from 'eslint-plugin-vuejs-accessibility'
import tseslint from 'typescript-eslint'
import vueParser from 'vue-eslint-parser'

export default tseslint.config(
  { ignores: ['dist', 'coverage', 'src/shared/api/schema.d.ts'] },
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  ...vueA11y.configs['flat/recommended'],
  {
    files: ['**/*.vue'],
    languageOptions: { parser: vueParser, parserOptions: { parser: tseslint.parser } },
  },
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/consistent-type-imports': 'error',
      // Never render API data as raw HTML (coding standards section 3).
      'vue/no-v-html': 'error',
      'vue/multi-word-component-names': 'off',
      // Our fields pair <label :for="id"> with an input that has the same generated id.
      'vuejs-accessibility/label-has-for': ['error', { required: { some: ['nesting', 'id'] } }],
    },
  },
  {
    files: ['src/**/*.test.ts'],
    rules: { '@typescript-eslint/no-non-null-assertion': 'off' },
  },
  // Formatting is Prettier's job: switch off every ESLint rule that would fight it. Keep last.
  prettier,
)
