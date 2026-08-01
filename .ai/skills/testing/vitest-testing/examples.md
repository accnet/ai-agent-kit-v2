# Vitest Testing Evidence

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchUser } from './api';
import { getUserGreeting } from './greeting';

vi.mock('./api');

describe('getUserGreeting', () => {
  beforeEach(() => vi.clearAllMocks());

  it('greets the user once loaded', async () => {
    vi.mocked(fetchUser).mockResolvedValue({ id: '1', name: 'Ada' });
    await expect(getUserGreeting('1')).resolves.toBe('Hello, Ada');
  });

  it('surfaces a fetch failure instead of swallowing it', async () => {
    vi.mocked(fetchUser).mockRejectedValue(new Error('network'));
    await expect(getUserGreeting('1')).rejects.toThrow('network');
  });
});
```

Evidence for a task: the focused `vitest run <file>` output, the coverage delta if
thresholds are configured, a regression test for the fixed/added behavior, and
confirmation that mocks/timers were reset (no leaked fake timers or unmocked network
calls) between tests.
