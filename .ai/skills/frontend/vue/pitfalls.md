# Vue Pitfalls

Do not mutate props directly — use `emit` to propagate changes to the parent. Do not use `v-if` and `v-for` on the same element; wrap with a `<template>` or use a computed property. Avoid deep watchers on large objects; prefer specific property watchers. Do not use `this.$nextTick` or Options API patterns in Composition API components — use `nextTick` from `vue`. Do not store non-reactive plain objects in Pinia stores and expect reactivity; use `ref()` or `reactive()` inside `defineStore`.
