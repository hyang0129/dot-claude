# E2E Automated UI QA: Best Practices

For experienced engineers new to automated browser testing. Assumes you know how to write code and understand testing theory — this doc is about the pitfalls that trip up smart people who haven't done this before.

---

## The core mental shift

Unit tests are deterministic because they run in your process. E2E tests run in a browser against a real (or semi-real) server stack. The browser introduces timing, paint cycles, network, and DOM mutation. Everything that makes unit tests pleasant to write disappears. Respect that.

---

## 1. Preventing flakiness

Flakiness is the #1 reason E2E suites get abandoned. A test that fails 1-in-10 is worse than no test — it trains engineers to ignore red CI.

### Never use time-based waits

```typescript
// WRONG — any of these will bite you in CI
await page.waitForTimeout(2000);
await new Promise(r => setTimeout(r, 1000));
```

Playwright auto-waits on almost every action. If you think you need a sleep, you have a selector problem. Use:

```typescript
await expect(page.getByRole('button', { name: 'Submit' })).toBeEnabled();
await page.getByRole('dialog').waitFor({ state: 'visible' });
```

### Wait for the right thing

Don't wait for a spinner to disappear — wait for the content you need to appear. Spinners can flicker. Content appearing is a positive assertion.

```typescript
// FRAGILE — spinner may briefly appear and disappear between checks
await expect(page.getByTestId('loading-spinner')).not.toBeVisible();

// BETTER — assert what you actually care about
await expect(page.getByRole('table')).toBeVisible();
```

### Selectors that don't break on refactors

Priority order:

1. `getByRole` — matches what the user sees (button, heading, textbox)
2. `getByLabel` — for form inputs
3. `getByText` — for static labels that won't change
4. `getByTestId` — last resort; add `data-testid` attributes when nothing else works
5. CSS class selectors — **never**. Classes are styling hooks, not test hooks
6. XPath — **never**. Breaks on any DOM restructuring

The rule: your selector should survive a designer moving the button to a different div.

### Isolate test state

Each test must set up its own preconditions and clean up after itself. Tests that depend on execution order fail unpredictably when the suite is parallelized or partially run.

```typescript
// WRONG — depends on previous test having created a user
test('edit profile', async ({ page }) => {
  await page.goto('/profile');
  // ...
});

// RIGHT — creates its own state
test('edit profile', async ({ page, testUser }) => {
  // testUser fixture creates + authenticates a fresh user
  await page.goto('/profile');
  // ...
});
```

### Stub non-deterministic data

Dates, IDs, random values, and third-party APIs all produce different output each run. Stub them at the network boundary:

```typescript
await page.route('**/api/feed', route =>
  route.fulfill({ json: STABLE_FEED_FIXTURE })
);
```

This also makes your assertions exact rather than approximate, which catches more bugs.

### Network race conditions

After a user action that triggers a network request, don't immediately assert on the result. Wait for the request to complete:

```typescript
await page.getByRole('button', { name: 'Save' }).click();
await page.waitForResponse(resp => resp.url().includes('/api/items') && resp.status() === 200);
await expect(page.getByText('Saved')).toBeVisible();
```

Or assert on the DOM state that only appears after the response is processed — that implicitly waits for the network.

### Use `--retries` only as a quarantine signal, not a fix

Running with `--retries 2` is fine for CI noise tolerance, but if a test only passes because of retries, it has a real flakiness bug. Track quarantined tests explicitly and fix them — don't let retries hide them.

---

## 2. Preventing tests from running forever

### One scenario = one user flow

A test should represent one coherent user journey with a clear start and end. Not "the user creates an account, then posts content, then moderates it, then checks analytics."

Split that into four tests. Each test should complete in under 30 seconds under normal conditions. Over 2 minutes is a red flag.

**Why this matters beyond runtime:** when a long test fails, you don't know which step failed without reading a trace. When a short test fails, the name tells you exactly what broke.

### Define a scenario budget

Before writing any code, enumerate the scenarios. If you have more than ~10 new tests for a single feature, you are probably:
- Duplicating unit test coverage
- Testing implementation details instead of user flows
- Treating one flow as many micro-steps

Ask: could any of these be a unit test? Unit tests are faster and more stable. E2E exists for things that require a browser — interaction, rendering, navigation, multi-component wiring.

### Keep setup cheap

Expensive setup (seeding a large DB, creating complex object graphs) multiplies across every test that uses it. Use `beforeAll` for shared read-only fixtures; use `beforeEach` only for mutable state. Prefer API calls over UI navigation to set up preconditions — a `POST /api/users` is faster than clicking through a registration flow.

### Parallelize, don't serialize

Playwright runs tests in parallel by default. Anything that forces serial execution (global mutable state, shared login sessions, fixed ports) is a bottleneck that grows linearly with your suite. Design tests to be independently runnable from the start.

### Set explicit timeouts at the right level

```typescript
// playwright.config.ts
export default {
  timeout: 30_000,          // per test
  expect: { timeout: 5_000 }, // per assertion
  globalTimeout: 600_000,   // entire suite (10 min)
};
```

Don't override these in individual tests unless you have a specific reason. If a test regularly needs 60s, it's doing too much.

---

## 3. Ensuring tests cover what they're supposed to cover

### Derive tests from acceptance criteria, not from the diff

The diff shows what was implemented. The spec shows what was asked for. If you only read the diff, your tests will pass even when the implementation has a bug — because you'll test the bug as if it's correct behavior.

Always pair with the original issue or spec. Disagreement between spec and diff is a bug to report, not a test to write.

### Test observables, not internals

A test should assert what a user can observe: visible text, button state, URL, network calls made, data persisted. It should not assert:
- Internal component state
- Redux/Zustand store shape
- Internal function call counts (those belong in unit tests)

```typescript
// WRONG — testing internals
expect(store.getState().user.loggedIn).toBe(true);

// RIGHT — testing the observable
await expect(page.getByRole('link', { name: 'Log out' })).toBeVisible();
```

### Write the failure case

Every positive test should have a corresponding negative: what happens when input is invalid, when the server returns an error, when a permission is denied? These are the cases that are hardest to verify manually and most likely to regress.

```typescript
test('shows error on invalid email', async ({ page }) => {
  await page.getByLabel('Email').fill('not-an-email');
  await page.getByRole('button', { name: 'Subscribe' }).click();
  await expect(page.getByRole('alert')).toContainText('valid email');
});
```

### Verify side effects, not just UI state

If the action should save data, call an API, send an event — assert that. UI can look correct while the backend call silently fails.

```typescript
const [request] = await Promise.all([
  page.waitForRequest(req => req.url().includes('/api/subscribe')),
  page.getByRole('button', { name: 'Subscribe' }).click(),
]);
expect(request.postDataJSON()).toMatchObject({ email: 'user@example.com' });
```

### Use coverage to find gaps, not to chase a number

Playwright can emit coverage reports. Use them to find flows that no test exercises — not to hit an arbitrary percentage. 90% coverage of the wrong things is worthless; 50% coverage of the critical paths is valuable.

---

## 4. Other important considerations

### Page Object Model — apply it selectively

Page Objects encapsulate selectors and common interactions for a page or component. Use them when multiple tests interact with the same surface. Don't create them for pages covered by a single test — premature abstraction creates maintenance overhead without benefit.

```typescript
// pages/LoginPage.ts
export class LoginPage {
  constructor(private page: Page) {}
  
  async login(email: string, password: string) {
    await this.page.getByLabel('Email').fill(email);
    await this.page.getByLabel('Password').fill(password);
    await this.page.getByRole('button', { name: 'Sign in' }).click();
  }
}
```

### Authentication: never test it every time

Logging in through the UI is the slowest part of most test suites. Use `storageState` to save an authenticated session and reuse it:

```typescript
// global-setup.ts — runs once
const page = await browser.newPage();
await page.goto('/login');
// ... complete login ...
await page.context().storageState({ path: 'auth.json' });

// playwright.config.ts
use: { storageState: 'auth.json' }
```

Only the login test itself should exercise the login flow. Everything else should inherit a pre-authenticated session.

### Test at the right layer

| What you're verifying | Layer |
|---|---|
| Pure logic, data transformation | Unit test |
| Component rendering, props → DOM | Component test (Vitest + Testing Library) |
| Integration between components | Component test |
| User flow, browser events, routing | E2E |
| Two systems talking over HTTP | E2E with real backend or contract test |

E2E tests are expensive. Don't use them for things unit tests can verify. The `why-not-a-unit-test` question should have a real answer before you write a scenario.

### CI environment parity

Your local browser and the CI headless browser behave differently. Fonts, viewport sizes, scroll behavior, and timing all differ. Common pitfalls:

- Always set an explicit viewport in config: `viewport: { width: 1280, height: 720 }`
- Fonts in screenshots will differ; use `--update-snapshots` only intentionally
- CI often runs on slower hardware — your local timeouts may be too tight

### Trace and screenshot on failure

Always configure Playwright to save traces on first retry and screenshots on failure. Without these, debugging CI failures is guesswork:

```typescript
// playwright.config.ts
use: {
  trace: 'on-first-retry',
  screenshot: 'only-on-failure',
  video: 'retain-on-failure',
}
```

### Don't use `test.only` in committed code

`test.only` silently skips all other tests. If it lands in main, your entire suite stops running. Make this a lint rule:

```json
// .eslintrc
"no-restricted-properties": [2, { "object": "test", "property": "only" }]
```

### Tag tests by criticality

Use Playwright tags to separate fast smoke tests from slow regression suites:

```typescript
test('checkout flow @critical @smoke', async ({ page }) => { ... });
test('order history pagination @regression', async ({ page }) => { ... });
```

Run `@smoke` on every commit (fast), `@regression` on pre-merge or nightly. This keeps PR feedback loops under 5 minutes.

### Treat flaky tests as production bugs

A quarantined flake is a debt item, not a dismissed failure. Assign it, track it, and fix it within a sprint. Letting flakes accumulate destroys trust in the suite faster than anything else.

---

## Summary checklist

Before merging new E2E tests:

- [ ] No `waitForTimeout` or arbitrary sleeps
- [ ] Selectors use role/label/testId — no CSS classes or XPath
- [ ] Each test sets up its own state and doesn't depend on other tests
- [ ] Non-deterministic data (dates, IDs, 3rd-party APIs) is stubbed
- [ ] Each test covers one user flow and completes in < 30s
- [ ] Scenarios are derived from acceptance criteria, not just the diff
- [ ] Side effects (API calls, persistence) are asserted, not just UI state
- [ ] Negative cases (errors, permission denied) are included
- [ ] Auth is handled via `storageState`, not UI login in every test
- [ ] `trace`, `screenshot`, `video` are configured for failures
- [ ] No `test.only` in committed code
