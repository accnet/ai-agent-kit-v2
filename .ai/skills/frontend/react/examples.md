# React Examples

**Custom hook replacing a copy-pasted debounce effect:**
```jsx
function useDebouncedValue(value, delayMs) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

function SearchBox({ onSearch }) {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebouncedValue(query, 300);
  useEffect(() => {
    if (debouncedQuery) onSearch(debouncedQuery);
  }, [debouncedQuery, onSearch]);
  return <input value={query} onChange={(e) => setQuery(e.target.value)} />;
}
```

**Fixing a stale-closure bug** — the interval below always reads the
`count` from the render it was created in:
```jsx
// Before: stale closure — count is always 0 inside the interval
useEffect(() => {
  const id = setInterval(() => setCount(count + 1), 1000);
  return () => clearInterval(id);
}, []); // count omitted from deps on purpose to "avoid re-subscribing"

// After: functional update reads the latest value, no dependency needed
useEffect(() => {
  const id = setInterval(() => setCount((c) => c + 1), 1000);
  return () => clearInterval(id);
}, []);
```

Before adding a component, find one existing component in the project with
a similar responsibility (a form, a list, a modal) and match its state
management choice (local state vs. context vs. the project's store),
styling approach, and test file location rather than introducing a new
pattern for the same problem.
