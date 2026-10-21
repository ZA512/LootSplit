import { useState } from "react";
import {
  ArrowRight,
  ArrowRightLeft,
  Check,
  CircleAlert,
  Plus,
} from "lucide-react";
import { EnvelopeIcon } from "./components";
import { money } from "./money";
import type { Dashboard, Envelope } from "./types";

export default function ReservesPage({
  dashboard,
  envelopes,
  open,
  onCreate,
  onReview,
  onReallocate,
}: {
  dashboard: Dashboard;
  envelopes: Envelope[];
  open: (id: number) => void;
  onCreate: () => void;
  onReview: () => void;
  onReallocate: (source?: number) => void;
}) {
  const [archives, setArchives] = useState(false);
  const r = dashboard.reconciliation;
  const projects = envelopes.filter(
    (e) => !e.is_system && (e.status === "ARCHIVED") === archives,
  );
  const system = envelopes.find((e) => e.is_system);
  const count = dashboard.anomalies.unassigned_transaction_ids.length;
  const other =
    dashboard.anomalies.negative_envelope_ids.length +
    dashboard.anomalies.suspected_duplicate_fingerprints.length;
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Enveloppes</h1>
          <p className="muted">Votre argent, réparti par projet.</p>
        </div>
        <button className="button primary" onClick={onCreate}>
          <Plus size={17} />
          Créer une enveloppe
        </button>
      </div>
      <section className="tool-balances" aria-label="Soldes des réserves">
        <div>
          <span>Solde du compte</span>
          <strong>{money(r.bank_balance_cents)}</strong>
          <small>
            {r.last_sync_at
              ? "Au dernier import"
              : "Solde initial · aucun relevé intégré"}
          </small>
        </div>
        <div>
          <span>Dans vos projets</span>
          <strong>{money(r.envelopes_total_cents - r.unassigned_cents)}</strong>
          <small>Hors non affecté, archives incluses</small>
        </div>
        <div>
          <span>Non affecté</span>
          <strong>{money(r.unassigned_cents)}</strong>
          <small>Réserve à répartir</small>
        </div>
      </section>
      <div
        className={`tool-reconciliation ${r.reconciled ? "" : "negative-text"}`}
      >
        <span>
          {r.reconciled ? <Check size={15} /> : <CircleAlert size={15} />}{" "}
          {r.reconciled
            ? "Total des enveloppes, non affecté inclus = solde du compte"
            : "Le total des enveloppes diffère du solde du compte"}
        </span>
        <strong>Écart : {money(r.difference_cents)}</strong>
      </div>
      {!r.reconciled && (
        <button className="notice danger notice-button" onClick={onReview}>
          <CircleAlert size={19} />
          <span>Vérifier l’écart de {money(r.difference_cents)}</span>
          <ArrowRight size={17} />
        </button>
      )}
      {count > 0 && (
        <div className="tool-task">
          <div>
            <strong>{count} opération(s) à affecter</strong>
            <small>Choisissez à quelle enveloppe les rattacher.</small>
          </div>
          <button className="button primary" onClick={onReview}>
            Affecter les opérations <ArrowRight size={16} />
          </button>
        </div>
      )}
      {other > 0 && (
        <button className="notice warning notice-button" onClick={onReview}>
          <CircleAlert size={18} />
          <span>
            {dashboard.anomalies.negative_envelope_ids.length} enveloppe(s)
            négative(s) ·{" "}
            {dashboard.anomalies.suspected_duplicate_fingerprints.length}{" "}
            groupe(s) de doublons possibles
          </span>
          <ArrowRight size={16} />
        </button>
      )}
      {r.last_sync_error && (
        <p className="notice danger" role="status">
          Dernier import en échec : {r.last_sync_error}
        </p>
      )}
      <div className="section-heading">
        <div className="tabs">
          <button
            aria-pressed={!archives}
            className={!archives ? "selected" : ""}
            onClick={() => setArchives(false)}
          >
            Actives
          </button>
          <button
            aria-pressed={archives}
            className={archives ? "selected" : ""}
            onClick={() => setArchives(true)}
          >
            Archives
          </button>
        </div>
        <button
          className="button"
          disabled={envelopes.filter((e) => e.status === "ACTIVE").length < 2}
          onClick={() => onReallocate()}
        >
          <ArrowRightLeft size={16} />
          Déplacer entre enveloppes
        </button>
      </div>
      <div className="tool-table">
        <table>
          <caption className="sr-only">
            {archives ? "Enveloppes archivées" : "Répartition actuelle"}
          </caption>
          <thead>
            <tr>
              <th>Enveloppe</th>
              <th className="code-column">Code virement</th>
              <th className="amount-column">Solde disponible</th>
              <th>
                <span className="sr-only">Action</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {projects.map((e) => (
              <tr key={e.id}>
                <td>
                  <button
                    className="text-button table-name"
                    onClick={() => open(e.id)}
                  >
                    <EnvelopeIcon envelope={e} />
                    <span>
                      {e.name}
                      {e.balance_cents < 0 && (
                        <small className="negative-text">Solde négatif</small>
                      )}
                    </span>
                  </button>
                </td>
                <td className="code-column">
                  <code>{e.code}</code>
                </td>
                <td
                  className={`amount-column ${e.balance_cents < 0 ? "negative-text" : ""}`}
                >
                  {money(e.balance_cents)}
                </td>
                <td>
                  <button
                    className="button"
                    onClick={() => open(e.id)}
                    aria-label={`Ouvrir ${e.name}`}
                  >
                    Ouvrir
                  </button>
                </td>
              </tr>
            ))}
            {!projects.length && (
              <tr>
                <td colSpan={4}>
                  {archives
                    ? "Aucune enveloppe archivée."
                    : "Créez une enveloppe pour commencer à répartir votre réserve."}
                </td>
              </tr>
            )}
          </tbody>
          {!archives && system && (
            <tfoot>
              <tr>
                <th>
                  <button
                    className="text-button"
                    onClick={() => open(system.id)}
                  >
                    Non affecté
                  </button>
                </th>
                <td className="code-column muted">Réserve à répartir</td>
                <td className="amount-column">{money(r.unassigned_cents)}</td>
                <td>
                  <button
                    className="button"
                    onClick={() => onReallocate(system.id)}
                    disabled={
                      r.unassigned_cents <= 0 ||
                      envelopes.filter((e) => e.status === "ACTIVE").length < 2
                    }
                  >
                    Répartir
                  </button>
                </td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
      <p className="small muted tool-footnote">
        Les déplacements entre enveloppes changent la répartition. Ils ne
        déclenchent aucun virement bancaire.
      </p>
    </>
  );
}
