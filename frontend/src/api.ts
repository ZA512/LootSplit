let csrfToken = "";
export function setCsrf(value: string) {
  csrfToken = value;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).catch(() => {
    throw new ApiError("Connexion au serveur impossible. Réessayez.", 0);
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail =
      typeof payload.detail === "string"
        ? payload.detail
        : response.status === 422
          ? "Vérifiez les champs du formulaire."
          : "Une erreur est survenue.";
    if (response.status === 401 && !path.startsWith("/auth/")) {
      window.dispatchEvent(new Event("session-expired"));
    }
    throw new ApiError(detail, response.status);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export async function downloadExport(format: "json" | "csv") {
  const response = await fetch(`/api/export/${format}`, {
    credentials: "same-origin",
  });
  if (!response.ok)
    throw new Error("L’export a échoué. Vérifiez votre connexion.");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `lootsplit.${format}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
