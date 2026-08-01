# Vue Patterns

<<<<<<< HEAD
Prefer the Composition API (`<script setup>`) for new components in Vue 3 projects. Extract reusable reactive logic into composables under `composables/`. Use Pinia stores for shared application state; keep component-local state in `ref`/`reactive`. Define props with TypeScript types and emit events with `defineEmits` for type safety. Keep components focused — split presentation from data-fetching logic. Use Vue Router navigation guards for authentication; avoid checking auth inside component setup.
=======
- Use composables for reusable side-effect logic.
- Keep components single-responsibility with explicit props/emits.
- Derive UI state from reactive sources instead of manual DOM mutation.
- Co-locate tests with components/composables for changed behavior.
>>>>>>> origin/main
