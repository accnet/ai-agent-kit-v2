---
name: accessibility
description: Build and review accessible interfaces with semantic structure, keyboard operation, and assistive technology support.
version: 2.1.0
tier: core
stack: [any]
owner: frontend
gates: [G2, G3]
related: [e2e-testing, documentation-maintenance]
---

# Skill: accessibility

## Purpose
Ship UI changes that work for keyboard users, screen-reader users, and users with motor,
visual, or cognitive differences — so accessibility is verified evidence in the PR, not
an afterthought reported by users after release. WCAG 2.1 AA is the minimum bar for
public-facing interfaces; the techniques here address the most common failure classes.

## When to use
Any change to a UI component, form, navigation structure, modal/dialog, notification, data
table, or interactive widget. Also required when: adding a new page or route, changing
focus management (e.g., opening/closing a modal), adding dynamic content that updates
without a page reload, or introducing a custom component that replaces a native HTML element.

## Procedure

1. **Identify the changed elements and their required accessibility outcomes.** List every
   interactive element and dynamic region in the changed UI: buttons, links, form inputs,
   select menus, toggles, modals, tabs, accordions, live-updating regions. For each, state
   the expected accessible name, role, state, and keyboard behavior — not in terms of
   implementation, but in terms of what an assistive technology user would experience.
2. **Use semantic HTML as the foundation.** Choose the native element that matches the
   behavior before reaching for ARIA. `<button>` for actions, `<a>` for navigation,
   `<input type="checkbox">` for toggles, `<select>` for dropdowns, `<table>` for tabular
   data. Native elements come with the correct role, focusability, and keyboard handling
   for free. Add ARIA only when no native element provides the required semantics (e.g.,
   a tab panel, a combobox with custom filtering, a tree view).
3. **Assign accessible names to all interactive elements.** Every button, link, input,
   and custom control must have an accessible name that describes its purpose in context:
   - Buttons and links: use descriptive text content; avoid "Click here" or "Learn more."
   - Icon-only buttons: add `aria-label="Close dialog"` or a visually-hidden `<span>`.
   - Form inputs: pair with a `<label for="...">` or use `aria-labelledby`; the
     visible in-field hint text attribute is not a programmatic label.
   - Images: `alt="descriptive text"` for informative images; `alt=""` for decorative ones.
   Test the accessible name by inspecting the accessibility tree in DevTools or running
   `axe` on the rendered component.
4. **Manage focus correctly for dynamic UI.** When UI appears, disappears, or updates:
   - Opening a modal/dialog: move focus to the first focusable element inside it or to
     the dialog container itself (`tabIndex="-1"` + `focus()`). Trap focus within the
     dialog while it is open (Tab/Shift+Tab cycle inside; Escape closes and returns focus).
   - Closing a modal/dialog: return focus to the element that triggered it.
   - Inline validation or status messages that appear after an action: use a live region
     (`role="status"` for non-urgent, `role="alert"` for urgent) so screen readers
     announce the update without losing focus.
   - Route/page transitions in SPAs: move focus to the new page's `<h1>` or a skip-link
     target so screen readers know the page has changed.
5. **Verify keyboard-only navigation end-to-end.** Unplug the mouse and complete every
   changed user journey using Tab, Shift+Tab, Enter, Space, Arrow keys, and Escape only.
   The journey must be completable without the mouse. Specifically check:
   - Focus is always visible (a visible focus ring; `outline: none` without a replacement
     fails WCAG 2.4.7).
   - Interactive elements are reachable in a logical order (matches the visual/reading
     order; elements hidden from view are not in the tab sequence).
   - Custom widgets implement the correct keyboard pattern from the
     [ARIA Authoring Practices Guide](https://www.w3.org/WAI/ARIA/apg/).
6. **Run a screen reader smoke pass on changed paths.** Test the changed flows with at
   least one screen reader: NVDA + Chrome on Windows, VoiceOver + Safari on macOS/iOS,
   or TalkBack on Android. Verify: headings announce the page/section structure, interactive
   elements announce their name and role when focused, dynamic changes are announced, and
   error messages are readable. A visual pass is not a substitute for assistive-technology
   verification — they test different things.
7. **Check color and non-color affordances.** Verify: text/background contrast meets WCAG
   AA (4.5:1 for normal text, 3:1 for large text), and that no information is conveyed by
   color alone (error states use an icon or text label in addition to a red color).

## Checklist
- [ ] All interactive elements have accessible names tested via DevTools or axe
- [ ] Semantic HTML used for all standard controls; ARIA added only where native elements
      are insufficient
- [ ] Form inputs paired with `<label>` elements; visible in-field hint text not used as the sole label
- [ ] Focus management correct: modal opens focus into dialog, closes focus to trigger,
      traps Tab within dialog, Escape closes
- [ ] Live regions used for dynamic content that updates without focus movement
- [ ] Keyboard-only journey completed without pointer interaction on all changed paths
- [ ] Focus ring is visible on all focusable elements (no `outline: none` without replacement)
- [ ] Screen reader smoke pass performed on changed flows; announcements are correct
- [ ] Color contrast meets WCAG AA; no information conveyed by color alone

## Anti-patterns
- Adding `role="button"` to a `<div>` and only handling `onclick` — keyboard users need
  `keydown` Enter/Space handling, and a `<button>` would have provided this natively.
- Using `aria-label` to describe visual appearance ("blue arrow button") instead of
  purpose ("go to next page") — assistive technology users don't see the visual appearance.
- Hiding the focus ring globally with `* { outline: none; }` for visual design reasons
  without providing a replacement — this makes keyboard navigation invisible.
- Testing accessibility only with an automated scanner (`axe`, `Lighthouse`) and treating
  a zero-violation report as an accessibility pass — automated tools catch about 30–40% of
  WCAG issues; keyboard and screen-reader testing catch the rest.
- Deferring accessibility fixes to "after launch" — the cost of retrofitting interactive
  components is 5–10× the cost of building them accessibly initially.

## Output
Changed UI with verified accessible names, keyboard journeys, and focus management;
DevTools accessibility tree inspection or `axe` report as evidence; screen reader smoke
pass notes (what was tested, what was verified) recorded in the task note or PR description.
