import { useEffect, useState } from "react";
import { Check, RefreshCw } from "lucide-react";
import { api } from "./api";
import { AsyncForm, LoadState, useLoad } from "./components";
import { money } from "./money";

export type BankStatus = {
  configured: boolean;
  credentials_configured: boolean;
  module_installed: boolean;
  connected: boolean;
  masked_iban: string | null;
  running: boolean;
  auto_sync_enabled: boolean;
  interval_hours: number;
  next_sync_at: string | null;
  last_success_at: string | null;
  last_attempt_at: string | null;
  error_code: string | null;
  error: string | null;
  automatic_paused: boolean;
};
type Choice = {
  choice_id: string;
  name: string;
  masked_iban: string;
  balance_cents: number;
};
const datetime = (value: string) =>
  new Date(value).toLocaleString("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
  });

export default function BankingPanel({
  revision,
  onChanged,
}: {
  revision: number;
  onChanged: () => void;
}) {
  const [reload, setReload] = useState(0);
  const {
    data: status,
    error,
    loading,
  } = useLoad<BankStatus>("/banking/status", revision + reload);
  const [choices, setChoices] = useState<Choice[] | null>(null);
  const [pending, setPending] = useState("");
  const [actionError, setActionError] = useState("");
  const [result, setResult] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [hours, setHours] = useState(6);
  useEffect(() => {
    if (status) {
      setEnabled(status.auto_sync_enabled);
      setHours(status.interval_hours);
    }
  }, [status?.auto_sync_enabled, status?.interval_hours]);
  useEffect(() => {
    if (!status?.running) return;
    const timer = setInterval(() => setReload((v) => v + 1), 5000);
    return () => clearInterval(timer);
  }, [status?.running]);
  async function action(label: string, work: () => Promise<void>) {
    setPending(label);
    setActionError("");
    setResult("");
    try {
      await work();
    } catch (error) {
      setActionError((error as Error).message);
    } finally {
      setPending("");
      setReload((v) => v + 1);
      onChanged();
    }
  }
  const busy = !!pending || status?.running;
  return (
    <section className="panel settings-section bank-panel">
      <div className="section-heading">
        <h2>Connexion bancaire</h2>
        <span className="subtle-pill">Crédit Agricole · Lecture seule</span>
      </div>
      <LoadState loading={loading && !status} error={error} />
      {status && (
        <>
          {!status.configured && (
            <div className="notice subtle">
              <strong>Configuration nécessaire sur le serveur</strong>
              <p>
                {!status.credentials_configured
                  ? "Renseignez votre caisse régionale et vos identifiants dans la configuration Docker, puis recréez le conteneur. Les identifiants ne sont jamais saisis dans cette page."
                  : "Le module bancaire doit être installé. Reconstruisez l’image Docker."}
              </p>
              <p>L’import CSV reste disponible pendant cette configuration.</p>
            </div>
          )}
          {status.error && (
            <div className="notice warning" role="status">
              <strong>
                {status.automatic_paused
                  ? "Une action est nécessaire"
                  : "Connexion bancaire à vérifier"}
              </strong>
              <p>{status.error}</p>
              {status.automatic_paused && (
                <p>
                  Les synchronisations automatiques sont suspendues jusqu’à une
                  synchronisation manuelle réussie.
                </p>
              )}
            </div>
          )}
          {status.connected ? (
            <>
              <p className="bank-connected">
                <Check size={16} />
                Compte de réserve associé{" "}
                <span className="muted">{status.masked_iban}</span>
              </p>
              <dl className="bank-dates">
                <div>
                  <dt>Dernière synchronisation bancaire réussie</dt>
                  <dd>
                    {status.last_success_at
                      ? datetime(status.last_success_at)
                      : "Aucune pour le moment"}
                  </dd>
                </div>
                {status.next_sync_at && !status.automatic_paused && (
                  <div>
                    <dt>Prochaine synchronisation prévue</dt>
                    <dd>{datetime(status.next_sync_at)}</dd>
                  </div>
                )}
              </dl>
              <button
                className="button primary"
                disabled={busy || !status.configured}
                onClick={() =>
                  action("Synchronisation en cours…", async () => {
                    const value = await api<{
                      imported: number;
                      duplicates: number;
                    }>("/sync", "POST");
                    setResult(
                      `${value.imported} opération(s) importée(s), ${value.duplicates} déjà connue(s).`,
                    );
                  })
                }
              >
                <RefreshCw size={16} />
                {pending ||
                  (status.running
                    ? "Synchronisation en cours…"
                    : "Synchroniser maintenant")}
              </button>
              <p className="small muted bank-hint">
                La première récupération peut prendre quelques minutes. Les
                opérations en attente ne sont pas importées.
              </p>
              <div className="bank-schedule">
                <h3>Synchronisation automatique</h3>
                <AsyncForm
                  disabled={busy}
                  label="Enregistrer la fréquence"
                  onSubmit={async () => {
                    await api("/banking/schedule", "PATCH", {
                      enabled,
                      interval_hours: hours,
                    });
                    setResult("Fréquence de synchronisation enregistrée.");
                    setReload((v) => v + 1);
                  }}
                >
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={enabled}
                      onChange={(event) => setEnabled(event.target.checked)}
                    />
                    Activer la synchronisation automatique
                  </label>
                  <label>
                    Fréquence
                    <select
                      aria-label="Fréquence"
                      value={hours}
                      onChange={(event) => setHours(Number(event.target.value))}
                    >
                      <option value={1}>Toutes les heures</option>
                      <option value={6}>Toutes les 6 heures</option>
                      <option value={12}>Toutes les 12 heures</option>
                      <option value={24}>Une fois par jour</option>
                      <option value={168}>Une fois par semaine</option>
                    </select>
                  </label>
                </AsyncForm>
              </div>
            </>
          ) : (
            <>
              <p className="muted">
                Sélectionnez le compte de réserve dont vous avez initialisé les
                enveloppes. Les autres comptes ne sont pas suivis.
              </p>
              <button
                className="button primary"
                disabled={busy || !status.configured}
                onClick={() =>
                  action("Connexion à la banque…", async () =>
                    setChoices(
                      await api<Choice[]>("/banking/accounts", "POST"),
                    ),
                  )
                }
              >
                <RefreshCw size={16} />
                {pending || "Charger mes comptes"}
              </button>
              {choices &&
                (choices.length ? (
                  <AsyncForm
                    disabled={busy}
                    label="Associer ce compte"
                    onSubmit={async (values) => {
                      await api("/banking/selection", "POST", {
                        choice_id: String(values.get("choice")),
                        confirmed: values.get("confirm") === "on",
                      });
                      setChoices(null);
                      setReload((v) => v + 1);
                      onChanged();
                    }}
                  >
                    <label>
                      Compte de réserve à suivre
                      <select
                        aria-label="Compte de réserve à suivre"
                        name="choice"
                        required
                        defaultValue=""
                      >
                        <option value="" disabled>
                          Choisir un compte de réserve
                        </option>
                        {choices.map((choice) => (
                          <option
                            key={choice.choice_id}
                            value={choice.choice_id}
                          >
                            {choice.name} · {choice.masked_iban} ·{" "}
                            {money(choice.balance_cents)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="checkbox-label">
                      <input name="confirm" type="checkbox" required />
                      Je confirme qu’il s’agit du compte de réserve déjà suivi
                      ici.
                    </label>
                    <p className="small muted">
                      L’association ne modifie pas le solde initial. La première
                      synchronisation signalera un éventuel écart avec vos
                      réserves.
                    </p>
                  </AsyncForm>
                ) : (
                  <p className="notice warning">
                    Aucun compte de réserve compatible en euros n’a été trouvé
                    dans cet accès bancaire.
                  </p>
                ))}
            </>
          )}
          {actionError && (
            <p className="notice danger" role="alert">
              {actionError}
            </p>
          )}
          {result && (
            <p className="notice success" role="status">
              {result}
            </p>
          )}
        </>
      )}
    </section>
  );
}

export function BankSyncButton({
  revision,
  onChanged,
}: {
  revision: number;
  onChanged: () => void;
}) {
  const status = useLoad<BankStatus>("/banking/status", revision);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  if (!status.data?.connected) return null;
  return (
    <div className="quick-sync">
      <button
        className="button primary"
        disabled={pending || status.data.running || !status.data.configured}
        onClick={async () => {
          setPending(true);
          setError("");
          try {
            await api("/sync", "POST");
          } catch (error) {
            setError((error as Error).message);
          } finally {
            setPending(false);
            onChanged();
          }
        }}
      >
        <RefreshCw size={16} />
        {pending || status.data.running
          ? "Synchronisation…"
          : "Synchroniser maintenant"}
      </button>
      {error && (
        <p className="notice danger" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
