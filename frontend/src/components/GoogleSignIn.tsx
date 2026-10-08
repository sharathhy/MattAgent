import { useEffect, useRef } from "react";

interface GoogleId {
  initialize(config: { client_id: string; callback: (r: { credential: string }) => void; use_fedcm_for_button?: boolean }): void;
  renderButton(el: HTMLElement, options: Record<string, string | number>): void;
}
declare global {
  interface Window {
    google?: { accounts: { id: GoogleId } };
  }
}

const SCRIPT_SRC = "https://accounts.google.com/gsi/client";

function loadScript(): Promise<void> {
  if (window.google) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${SCRIPT_SRC}"]`);
    const script = existing ?? Object.assign(document.createElement("script"), { src: SCRIPT_SRC, async: true });
    script.addEventListener("load", () => resolve());
    script.addEventListener("error", () => reject(new Error("Could not load Google Sign-In")));
    if (!existing) document.head.appendChild(script);
  });
}

/** Renders Google's own "Sign in with Google" button and hands back the ID token. */
export function GoogleSignIn({ clientId, onCredential, onError }: {
  clientId: string;
  onCredential: (credential: string) => void;
  onError: (err: unknown) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let cancelled = false;
    loadScript()
      .then(() => {
        const el = ref.current;
        if (cancelled || !el || !window.google) return;
        // FedCM lets the browser run the Google popup, so the page's COOP header no longer
        // blocks Google's postMessage (the console warning seen at sign-in).
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: (r) => onCredential(r.credential),
          use_fedcm_for_button: true,
        });
        window.google.accounts.id.renderButton(el, { theme: "filled_black", size: "large", shape: "pill", width: 280 });
      })
      .catch(onError);
    return () => {
      cancelled = true;
    };
  }, [clientId, onCredential, onError]);
  return <div ref={ref} data-testid="google-signin" className="flex min-h-10 justify-center" />;
}
