import { useState } from "react";
import { api } from "./api";
import { LoadState, Modal } from "./components";
import { cents, day, money } from "./money";

type Preview = {
  revision: string;
  activation_date: string;
  opening_balance_cents: number;
  bank_balance_known: boolean;
  difference_cents: number;
  envelopes: {
    id: number;
    name: string;
    status: string;
    is_system: boolean;
    initial_cents: number;
    balance_cents: number;
  }[];
};

export default function OpeningBalancePanel({
  onChanged,
}: {
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [balance, setBalance] = useState("");
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [backup, setBackup] = useState("");

  async function load() {
    setOpen(true);
    setLoading(true);
    setPreview(null);
    setError("");
    setConfirmed(false);
    setReason("");
    try {
      const data = await api<Preview>("/account/opening-balance");
      setBalance((data.opening_balance_cents / 100).toFixed(2));
      setAmounts(
        Object.fromEntries(
          data.envelopes
            .filter((e) => !e.is_system)
            .map((e) => [e.id, (e.initial_cents / 100).toFixed(2)]),
        ),
      );
      setPreview(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  let parsed: { total: number; allocations: Record<number, number> } | null =
    null;
  let validation = "";
  try {
    const total = cents(balance);
    const allocations = Object.fromEntries(
      Object.entries(amounts).map(([id, value]) => [id, cents(value)]),
    );
    if (total < 0 || Object.values(allocations).some((v) => v < 0))
      throw new Error("Les montants doivent être positifs ou nuls.");
    if (Object.values(allocations).reduce((a, b) => a + b, 0) > total)
      throw new Error("La répartition dépasse le solde initial corrigé.");
    parsed = { total, allocations };
  } catch (e) {
    validation = (e as Error).message;
  }

  return (
    <section className="panel settings-section">
      <h2>Solde initial et répartition</h2>
      <p className="muted">
        Corrigez une erreur au démarrage, par exemple un montant compté à la
        fois dans le solde initial et dans un virement importé.
      </p>
      <button className="button" onClick={load}>
        Corriger le solde initial
      </button>
      {backup && (
        <p className="notice success" role="status">
          Correction enregistrée. Les opérations bancaires sont conservées.{" "}
          <a
            href={`/api/backups/${encodeURIComponent(backup)}/download`}
            download
          >
            Télécharger la sauvegarde avant correction
          </a>
        </p>
      )}
      {open && (
        <Modal
          title="Corriger le solde initial"
          onClose={() => !pending && setOpen(false)}
        >
          <LoadState loading={loading} error={preview ? "" : error} />
          {preview && (
            <form
              className="form"
              onSubmit={async (event) => {
                event.preventDefault();
                if (!parsed || !confirmed || pending) return;
                setPending(true);
                setError("");
                try {
                  const saved = await api<{ backup: { name: string } }>(
                    "/account/opening-balance",
                    "PATCH",
                    {
                      revision: preview.revision,
                      opening_balance_cents: parsed.total,
                      allocations: parsed.allocations,
                      reason: reason.trim(),
                      confirmed,
                    },
                  );
                  setBackup(saved.backup.name);
                  setOpen(false);
                  onChanged();
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setPending(false);
                }
              }}
            >
              <p>
                Indiquez les fonds réellement présents à la clôture du{" "}
                <strong>{day(preview.activation_date)}</strong>, avant les
                opérations importées après cette date. La date de démarrage
                reste la même.
              </p>
              <p className="notice warning">
                Si un virement importé apporte déjà cette somme, retirez-la du
                solde initial et de sa répartition. La déplacer vers une autre
                enveloppe ne corrige pas le double comptage.
              </p>
              <fieldset disabled={pending}>
                <label>
                  Solde initial corrigé (€)
                  <input
                    inputMode="decimal"
                    required
                    value={balance}
                    onChange={(e) => {
                      setBalance(e.target.value);
                      setConfirmed(false);
                    }}
                  />
                </label>
                <h3>Répartition initiale corrigée</h3>
                {preview.envelopes
                  .filter((e) => !e.is_system)
                  .map((envelope) => (
                    <label key={envelope.id}>
                      Montant initial pour {envelope.name}
                      {envelope.status === "ARCHIVED"
                        ? " (archivée, conservé)"
                        : ""}
                      <input
                        inputMode="decimal"
                        required
                        readOnly={envelope.status === "ARCHIVED"}
                        value={amounts[envelope.id]}
                        onChange={(e) => {
                          setAmounts({
                            ...amounts,
                            [envelope.id]: e.target.value,
                          });
                          setConfirmed(false);
                        }}
                      />
                      <span className="small muted">
                        Solde de l’enveloppe après correction :{" "}
                        {parsed
                          ? money(
                              envelope.balance_cents +
                                parsed.allocations[envelope.id] -
                                envelope.initial_cents,
                            )
                          : "—"}
                      </span>
                    </label>
                  ))}
                {parsed ? (
                  <div className="notice">
                    <p>
                      Solde initial NON AFFECTÉ :{" "}
                      {money(
                        parsed.total -
                          Object.values(parsed.allocations).reduce(
                            (a, b) => a + b,
                            0,
                          ),
                      )}
                      .
                    </p>
                    <p>
                      Écart total après correction :{" "}
                      {money(
                        preview.bank_balance_known
                          ? preview.difference_cents +
                              preview.opening_balance_cents -
                              parsed.total
                          : 0,
                      )}
                      .
                    </p>
                  </div>
                ) : (
                  <p role="alert" className="notice warning">
                    {validation}
                  </p>
                )}
                <label>
                  Motif de la correction
                  <input
                    required
                    maxLength={1000}
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </label>
                <p className="small muted">
                  Une sauvegarde sera créée avant la correction. Les montants
                  précédents et le motif restent dans l’historique. Les
                  enveloppes archivées conservent leur répartition initiale.
                </p>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />
                  Je confirme le solde initial et sa répartition corrigés.
                </label>
                {error && (
                  <p role="alert" className="notice danger">
                    {error}
                  </p>
                )}
                <div className="button-group">
                  <button
                    type="submit"
                    className="button primary"
                    disabled={
                      !parsed || !confirmed || !reason.trim() || pending
                    }
                  >
                    {pending ? "Enregistrement…" : "Sauvegarder et corriger"}
                  </button>
                  <button type="button" className="button" onClick={load}>
                    Recharger les montants
                  </button>
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => setOpen(false)}
                  >
                    Annuler
                  </button>
                </div>
              </fieldset>
            </form>
          )}
        </Modal>
      )}
    </section>
  );
}
