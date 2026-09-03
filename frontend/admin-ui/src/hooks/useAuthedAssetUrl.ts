import { useEffect, useState } from "react";

import { authAwareFetch } from "../auth/api";

/**
 * Превью медиа нельзя грузить через <img src="/api/assets/preview">:
 * такой запрос не несёт Bearer-токен, а 401 с WWW-Authenticate: Basic
 * открывает нативный браузерный пароль-диалог. Грузим blob авторизованно.
 */
export function useAuthedAssetUrl(
  assetRef: string | null | undefined
): { url: string | null; failed: boolean } {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const key = assetRef?.trim() ?? "";

  useEffect(() => {
    if (!key) {
      setUrl(null);
      setFailed(false);
      return;
    }
    let alive = true;
    let objectUrl: string | null = null;
    setUrl(null);
    setFailed(false);
    (async () => {
      try {
        const res = await authAwareFetch(
          `/api/assets/preview?asset_ref=${encodeURIComponent(key)}`
        );
        if (!res.ok) throw new Error(`preview: ${res.status}`);
        const blob = await res.blob();
        if (!alive) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      } catch {
        if (alive) setFailed(true);
      }
    })();
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [key]);

  return { url, failed };
}