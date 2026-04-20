import { createClient, type SupabaseClient } from '@supabase/supabase-js'

/**
 * Lazy Supabase client.
 *
 * Why: `createClient(undefined, undefined)` throws synchronously. When it runs
 * at module load (as it did before), every page that transitively imports
 * `auth-context` crashes immediately if env vars aren't set — which is the
 * common "I can't even enter any route" failure mode in fresh dev checkouts.
 *
 * This version defers instantiation until the first call. If the env vars are
 * missing, the stub client rejects auth calls with a clear message but lets
 * the rest of the app render so the developer can see what's wrong.
 */
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

let _client: SupabaseClient | null = null

function missingEnvError(method: string): Error {
  return new Error(
    `[supabase] ${method} called but NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY are not set. ` +
      `Copy frontend/.env.example to frontend/.env.local and fill in your Supabase project URL + anon key.`
  )
}

function makeStub(): SupabaseClient {
  // Minimal shape needed by auth-context + login page. Anything unexpected
  // throws with the same env-missing message so failures surface at call
  // time with context, not at import with an unhelpful stack.
  const err = () => Promise.reject(missingEnvError('auth.*'))
  const fakeSubscription = { unsubscribe: () => {} }
  const stub = {
    auth: {
      getSession: () => Promise.resolve({ data: { session: null }, error: null }),
      onAuthStateChange: (_cb: unknown) => ({ data: { subscription: fakeSubscription } }),
      signOut: err,
      signInWithPassword: err,
      signUp: err,
      signInWithOAuth: err,
    },
  }
  return stub as unknown as SupabaseClient
}

export function getSupabase(): SupabaseClient {
  if (_client) return _client
  if (!supabaseUrl || !supabaseAnonKey) {
    if (typeof window !== 'undefined') {
      // One-time warning in browser console so the cause is obvious.
      console.warn(
        '[supabase] env vars missing — running in stub mode. See frontend/.env.example.'
      )
    }
    _client = makeStub()
    return _client
  }
  _client = createClient(supabaseUrl, supabaseAnonKey)
  return _client
}

// Backward-compatible export: existing callers using `import { supabase }` keep
// working. Proxy so the real client is materialized lazily on first access.
export const supabase = new Proxy({} as SupabaseClient, {
  get(_target, prop) {
    const client = getSupabase() as unknown as Record<string | symbol, unknown>
    return client[prop]
  },
})

export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey)
