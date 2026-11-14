const VERIFIER_KEY = 'meridian_pkce_code_verifier';

export function generateRandomString(length: number = 64): string {
  const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
  let text = '';
  if (typeof window !== 'undefined' && window.crypto && window.crypto.getRandomValues) {
    const values = new Uint8Array(length);
    window.crypto.getRandomValues(values);
    for (let i = 0; i < length; i++) {
      text += possible[values[i] % possible.length];
    }
    return text;
  }
  for (let i = 0; i < length; i++) {
    text += possible.charAt(Math.floor(Math.random() * possible.length));
  }
  return text;
}

export async function sha256Base64Url(plain: string): Promise<string> {
  if (typeof window !== 'undefined' && window.crypto && window.crypto.subtle) {
    const encoder = new TextEncoder();
    const data = encoder.encode(plain);
    const hash = await window.crypto.subtle.digest('SHA-256', data);
    const bytes = new Uint8Array(hash);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary)
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');
  }
  return plain;
}

export async function createAndStorePkce(): Promise<{ verifier: string; challenge: string }> {
  const verifier = generateRandomString(64);
  const challenge = await sha256Base64Url(verifier);
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.setItem(VERIFIER_KEY, verifier);
    }
  } catch {}
  return { verifier, challenge };
}

export function getStoredPkceVerifier(): string | null {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      return window.localStorage.getItem(VERIFIER_KEY);
    }
  } catch {}
  return null;
}

export function clearStoredPkceVerifier(): void {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.removeItem(VERIFIER_KEY);
    }
  } catch {}
}

