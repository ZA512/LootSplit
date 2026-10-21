import { useState } from "react";
import { api } from "./api";
import { AsyncForm } from "./components";
import { cents, money } from "./money";
import type { Envelope, Reconciliation } from "./types";

export function EnvelopeForm({
  envelope,
  onSaved,
}: {
  envelope?: Envelope;
  onSaved: () => void;
}) {
  return (
    <AsyncForm
      onSubmit={async (values) => {
        const body = {
          name: String(values.get("name")).trim(),
          code: String(values.get("code")).trim().toUpperCase(),
          description: String(values.get("description")),
          icon: String(values.get("icon")),
          sort_order: Number(values.get("sort_order")),
        };
        await api(
          envelope ? `/envelopes/${envelope.id}` : "/envelopes",
          envelope ? "PATCH" : "POST",
          body,
        );
        onSaved();
      }}
      label={envelope ? "Enregistrer les modifications" : "Créer l’enveloppe"}
    >
      <label>
        Nom de l’enveloppe
        <input
          name="name"
          required
          maxLength={100}
          defaultValue={envelope?.name}
          placeholder="Ex. Vacances"
          autoFocus
        />
      </label>
      <label>
        Code bancaire
        <input
          name="code"
          required
          maxLength={20}
          pattern="[A-Za-z0-9_\-]{1,20}"
          defaultValue={envelope?.code || ""}
          placeholder="RES-VAC"
          className="code-input"
        />
        <small>
          À utiliser dans les libellés des virements. Lettres, chiffres, tirets
          et underscores.
        </small>
      </label>
      <label>
        Description <span className="optional">facultatif</span>
        <textarea
          name="description"
          rows={2}
          maxLength={1000}
          defaultValue={envelope?.description}
        />
      </label>
      <div className="form-grid">
        <label>
          Icône
          <select
            aria-label="Icône"
            name="icon"
            defaultValue={envelope?.icon || "sun"}
          >
            <option value="sun">Soleil</option>
            <option value="shield">Bouclier</option>
            <option value="gift">Cadeau</option>
            <option value="school">École</option>
            <option value="plane">Voyage</option>
            <option value="heart">Cœur</option>
          </select>
        </label>
        <label>
          Ordre d’affichage
          <input
            name="sort_order"
            type="number"
            min="0"
            max="100000"
            step="1"
            required
            defaultValue={envelope?.sort_order || 0}
          />
        </label>
      </div>
    </AsyncForm>
  );
}

export function ReallocationForm({
  envelopes,
  initialSource,
  onSaved,
}: {
  envelopes: Envelope[];
  initialSource?: number;
  onSaved: () => void;
}) {
  const available = envelopes.filter((e) => e.status === "ACTIVE");
  const [source, setSource] = useState(
    String(
      initialSource ||
        available.find((e) => e.balance_cents > 0)?.id ||
        available[0]?.id ||
        "",
    ),
  );
  const balance =
    available.find((e) => e.id === Number(source))?.balance_cents || 0;
  const [target, setTarget] = useState("");
  const [amount, setAmount] = useState("");
  let preview: number | null = null;
  try {
    if (amount.trim()) preview = cents(amount);
  } catch {
    /* Le formulaire affichera l'erreur à la validation. */
  }
  const destination = available.find((e) => e.id === Number(target));
  return (
    <AsyncForm
      label="Confirmer le déplacement"
      onSubmit={async (values) => {
        await api("/reallocations", "POST", {
          from_envelope_id: Number(source),
          to_envelope_id: Number(values.get("target")),
          amount_cents: cents(String(values.get("amount"))),
          reason: String(values.get("reason")),
        });
        onSaved();
      }}
    >
      <p className="muted">
        Déplacez un montant entre vos enveloppes. Le solde du compte de réserve
        reste identique.
      </p>
      <label>
        Depuis
        <select
          aria-label="Depuis"
          name="source"
          value={source}
          onChange={(event) => {
            setSource(event.target.value);
            if (target === event.target.value) setTarget("");
          }}
          required
        >
          {available.map((e) => (
            <option key={e.id} value={e.id}>
              {e.name}
            </option>
          ))}
        </select>
        <small>Disponible : {money(balance)}</small>
      </label>
      <label>
        Vers
        <select
          aria-label="Vers"
          name="target"
          required
          value={target}
          onChange={(e) => setTarget(e.target.value)}
        >
          <option value="" disabled>
            Choisir une enveloppe
          </option>
          {available
            .filter((e) => e.id !== Number(source))
            .map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
        </select>
      </label>
      <label>
        Montant (€)
        <input
          name="amount"
          inputMode="decimal"
          required
          placeholder="0,00"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
      </label>
      {destination && preview !== null && preview > 0 && (
        <div
          className={`notice ${preview > balance ? "warning" : "subtle"}`}
          role="status"
        >
          <strong>Après le déplacement</strong>
          <p>
            {available.find((e) => e.id === Number(source))?.name} :{" "}
            {money(balance - preview)}
            <br />
            {destination.name} : {money(destination.balance_cents + preview)}
          </p>
          <p>Solde bancaire inchangé · aucun virement effectué.</p>
        </div>
      )}
      <label>
        Motif <span className="optional">facultatif</span>
        <input
          name="reason"
          maxLength={1000}
          placeholder="Ex. Préparation des vacances"
        />
      </label>
    </AsyncForm>
  );
}

export function CorrectionForm({
  transactionId,
  envelopes,
  onSaved,
}: {
  transactionId: number;
  envelopes: Envelope[];
  onSaved: () => void;
}) {
  return (
    <AsyncForm
      label="Valider l’affectation"
      onSubmit={async (values) => {
        await api(`/transactions/${transactionId}/allocation`, "PATCH", {
          envelope_id: Number(values.get("envelope")),
        });
        onSaved();
      }}
    >
      <p className="muted">
        Choisissez la réserve à laquelle appartient cette opération. La
        correction sera conservée dans l’historique.
      </p>
      <label>
        Affecter à
        <select
          aria-label="Affecter à"
          name="envelope"
          defaultValue=""
          required
          autoFocus
        >
          <option value="" disabled>
            Choisir une enveloppe
          </option>
          {envelopes
            .filter((e) => e.status === "ACTIVE")
            .map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
        </select>
      </label>
    </AsyncForm>
  );
}

export function ImportForm({ onSaved }: { onSaved: () => void }) {
  const [result, setResult] = useState<{
    imported: number;
    duplicates: number;
    before_start: number;
    reconciliation: Reconciliation;
  } | null>(null);
  return (
    <>
      <AsyncForm
        label="Importer le relevé"
        onSubmit={async (values) => {
          const file = values.get("file") as File;
          if (!file?.size)
            throw new Error("Sélectionnez un fichier CSV non vide.");
          if (file.size > 2_000_000)
            throw new Error("Le fichier est limité à 2 Mo.");
          const response = await api<NonNullable<typeof result>>(
            "/import/csv",
            "POST",
            {
              content: await file.text(),
              bank_balance_cents: cents(String(values.get("balance"))),
            },
          );
          setResult(response);
          onSaved();
        }}
      >
        <p className="muted">
          Importez les opérations comptabilisées depuis la date de démarrage,
          puis indiquez le solde correspondant du compte de réserve.
        </p>
        <label>
          Relevé CSV
          <input
            name="file"
            type="file"
            accept=".csv,text/csv"
            required
            onChange={() => setResult(null)}
          />
        </label>
        <details className="format-help">
          <summary>Format du fichier attendu</summary>
          <p>
            UTF-8, séparateur point-virgule. Colonnes obligatoires :{" "}
            <code>booking_date;amount;raw_label</code>.
          </p>
          <p>
            Date au format AAAA-MM-JJ, montant en euros signé. Colonnes
            facultatives : <code>value_date</code>,{" "}
            <code>provider_transaction_id</code> et <code>currency</code> (EUR).
          </p>
        </details>
        <label>
          Solde bancaire après ces opérations (€)
          <input
            name="balance"
            inputMode="decimal"
            required
            placeholder="Ex. 9 365,00"
          />
        </label>
      </AsyncForm>
      {result && (
        <div
          className={`notice ${result.reconciliation.reconciled ? "success" : "warning"}`}
          role="status"
        >
          <strong>Import terminé</strong>
          <p>
            {result.imported} opération(s) importée(s), {result.duplicates} déjà
            connue(s), {result.before_start} incluse(s) dans le solde initial.
          </p>
          <p>
            {result.reconciliation.reconciled
              ? "Le solde est réconcilié."
              : `Écart à vérifier : ${money(result.reconciliation.difference_cents)}.`}
          </p>
        </div>
      )}
    </>
  );
}
