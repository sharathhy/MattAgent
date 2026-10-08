import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState, type FormEvent, type ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { api } from "../api/client";
import { GoogleSignIn } from "../components/GoogleSignIn";
import { ErrorState, Loading } from "../components/ui";
import { useAuth } from "../lib/auth";

function Shell({ subtitle, children }: { subtitle: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="panel scanline relative w-full max-w-sm space-y-4 overflow-hidden p-8">
        <div className="text-center">
          <div className="font-mono text-3xl font-bold tracking-[0.4em] text-accent">MATT</div>
          <div className="label mt-2">{subtitle}</div>
        </div>
        {children}
      </div>
    </div>
  );
}

export function LoginPage() {
  const { user, login, loginWithGoogle } = useAuth();
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["auth-status"], queryFn: api.authStatus });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [setupCode, setSetupCode] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const onGoogleCredential = useCallback(
    (credential: string) => {
      setError(null);
      loginWithGoogle(credential).catch(setError);
    },
    [loginWithGoogle],
  );

  if (user) return <Navigate to="/command-center" replace />;
  if (status.isPending) return <Loading label="Connecting to MATT" />;
  if (status.isError) return <div className="p-8"><ErrorState error={status.error} /></div>;

  const {
    bootstrap_required: bootstrap,
    setup_code_required: needsCode,
    web_bootstrap_enabled,
    google_client_id: googleClientId,
  } = status.data;
  // On a locked-down install with no owner yet, only the owner's Google account can get in.
  const showPasswordForm = !bootstrap || web_bootstrap_enabled;

  const google = googleClientId && (
    <GoogleSignIn clientId={googleClientId} onCredential={onGoogleCredential} onError={setError} />
  );

  if (!showPasswordForm) {
    return (
      <Shell subtitle="Owner sign-in">
        {google ? (
          <>
            <p className="text-center text-xs text-muted">Sign in with the owner's Google account to set up MATT.</p>
            {google}
          </>
        ) : (
          <p className="text-center text-sm text-muted">
            No owner account exists yet. Create it on the server with{" "}
            <code className="font-mono text-accent">matt create-owner --email you@example.com</code>.
          </p>
        )}
        {error !== null && <ErrorState error={error} />}
      </Shell>
    );
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (bootstrap) {
        await api.bootstrap({ email, password, full_name: fullName, setup_code: needsCode ? setupCode : undefined });
        await qc.invalidateQueries({ queryKey: ["auth-status"] });
      }
      await login(email, password);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell subtitle={bootstrap ? "Initialise owner account" : "Command Center access"}>
      {google && (
        <>
          {google}
          <div className="label text-center">or</div>
        </>
      )}
      <form onSubmit={submit} className="space-y-4">
        {bootstrap && (
          <p className="text-xs text-muted">
            No accounts exist yet. The first account becomes the owner, with final authority over every agent.
          </p>
        )}
        {bootstrap && needsCode && (
          <label className="block space-y-1 text-sm">
            <span className="label">Setup code</span>
            <input className="input" type="password" required autoComplete="off" value={setupCode} onChange={(e) => setSetupCode(e.target.value)} />
          </label>
        )}
        {bootstrap && (
          <label className="block space-y-1 text-sm">
            <span className="label">Name</span>
            <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </label>
        )}
        <label className="block space-y-1 text-sm">
          <span className="label">Email</span>
          <input className="input" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="block space-y-1 text-sm">
          <span className="label">Password</span>
          <input
            className="input"
            type="password"
            required
            minLength={bootstrap ? 12 : undefined}
            autoComplete={bootstrap ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error !== null && <ErrorState error={error} />}
        <button type="submit" className="btn w-full" disabled={busy}>
          {bootstrap ? "Create owner and sign in" : "Sign in"}
        </button>
      </form>
    </Shell>
  );
}
