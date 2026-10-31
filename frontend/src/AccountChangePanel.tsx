import { useState } from "react";
import { ArrowRightLeft, Download } from "lucide-react";
import { api } from "./api";
import { LoadState, Modal } from "./components";
import { day, money } from "./money";

type Preview = {
  revision: string;
  activation_date: string;
  bank_balance_cents: number;
  difference_cents: number;
  masked_iban: string | null;
  transaction_count: number;
  envelopes: {
    id: number;
    name: string;
    code: string | null;
    status: string;
    is_system: boolean;
    balance_cents: number;
  }[];
};

function downloadSummary(preview: Preview) {
  const lines = [
    "LootSplit — Avant changement de compte de réserve",
    `Suivi démarré le ${day(preview.activation_date)}`,
    `Compte associé : ${preview.masked_iban || "Aucun"}`,
    `Solde bancaire : ${money(preview.bank_balance_cents)}`,
    `Écart de réconciliation : ${money(preview.difference_cents)}`,
    "",
    "Enveloppe | Code bancaire | Montant | État",
    ...preview.envelopes.map(
      (envelope) =>
        `${envelope.name} | ${envelope.code || "Sans code"} | ${money(envelope.balance_cents)} | ${envelope.status === "ARCHIVED" ? "Archivée" : "Active"}`,
    ),
    "",
    "Vérifiez ces montants avant de les reprendre sur le nouveau compte.",
    "Les enveloppes et codes seront conservés ; les soldes et l'historique seront remis à zéro.",
    "Aucun virement bancaire n'est effectué par LootSplit.",
    "Si les fonds sont déjà sur le nouveau compte : répartissez-les dans son solde initial.",
    "Si vous les versez ensuite : utilisez les codes et montants ci-dessus pour les virements, puis synchronisez.",
    "Ne comptez pas les mêmes fonds à la fois dans le solde initial et comme nouveaux virements.",
  ];
  const url = URL.createObjectURL(
    new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = "lootsplit-avant-changement-compte.txt";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function AccountChangePanel({
  onChanged,
}: {
  onChanged: (backupName: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [recorded, setRecorded] = useState(false);
  const [confirmation, setConfirmation] = useState("");

  async function loadPreview() {
    setOpen(true);
    setLoading(true);
    setPreview(null);
    setRecorded(false);
    setConfirmation("");
    setError("");
    try {
      setPreview(await api<Preview>("/account/change-preview"));
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel settings-section">
      <h2>Changer de compte de réserve</h2>
      <p className="muted">
        Un mauvais compte sélectionné ou un nouveau compte à utiliser ? Préparez
        une nouvelle initialisation avec une sauvegarde de votre suivi actuel.
      </p>
      <button className="button" onClick={loadPreview}>
        <ArrowRightLeft size={16} />
        Préparer le changement de compte
      </button>
      {open && (
        <Modal
          title="Changer de compte de réserve"
          onClose={() => {
            if (!pending) setOpen(false);
          }}
        >
          <LoadState loading={loading} error={preview ? "" : error} />
          {preview && (
            <>
              <p className="notice warning">
                Recopiez ou téléchargez vos enveloppes, leurs codes et leurs
                montants avant de continuer. Ces informations vous serviront à
                répartir les fonds et à faire les virements avec les bonnes
                sommes.
              </p>
              <p className="muted">
                Ces montants viennent du compte actuellement suivi
                {preview.masked_iban ? ` (${preview.masked_iban})` : ""}.
                Vérifiez-les si vous aviez sélectionné le mauvais compte.
              </p>
              <div className="account-change-list">
                {preview.envelopes.map((envelope) => (
                  <div className="account-change-row" key={envelope.id}>
                    <div>
                      <strong>{envelope.name}</strong>
                      <span className="small muted">
                        {envelope.code || "Sans code"}
                        {envelope.status === "ARCHIVED" ? " · Archivée" : ""}
                      </span>
                    </div>
                    <strong>{money(envelope.balance_cents)}</strong>
                  </div>
                ))}
              </div>
              <p>
                Solde bancaire :{" "}
                <strong>{money(preview.bank_balance_cents)}</strong>.
              </p>
              {preview.difference_cents !== 0 && (
                <p className="notice warning">
                  Un écart de {money(preview.difference_cents)} est présent.
                  Vérifiez les montants avant de les reprendre sur le nouveau
                  compte.
                </p>
              )}
              <button
                className="button"
                disabled={pending}
                onClick={() => downloadSummary(preview)}
              >
                <Download size={16} /> Télécharger le récapitulatif
              </button>
              <h3>Ce qui sera réinitialisé</h3>
              <p>
                Les soldes, les {preview.transaction_count} opération(s), les
                affectations et l’ancien historique seront retirés du suivi
                courant. L’association bancaire et sa planification seront
                supprimées. Les enveloppes et leurs codes seront conservés.
              </p>
              <p>
                Une sauvegarde complète est créée avant la remise à zéro. Si
                elle échoue, le changement est annulé. Aucun virement bancaire
                n’est effectué.
              </p>
              <h3>Après le changement</h3>
              <ol>
                <li>
                  Choisissez le bon compte dans l’assistant, puis confirmez son
                  solde réel à la clôture de la date choisie et sa répartition.
                </li>
                <li>
                  Si les fonds y sont déjà présents, répartissez-les dans les
                  enveloppes au démarrage.
                </li>
                <li>
                  Si vous faites les virements ensuite, utilisez les codes et
                  montants recopiés, puis synchronisez. Ne comptez pas les mêmes
                  sommes dans le solde initial et les nouveaux virements.
                </li>
              </ol>
              <form
                className="form"
                onSubmit={async (event) => {
                  event.preventDefault();
                  if (
                    pending ||
                    !recorded ||
                    confirmation !== "CHANGER DE COMPTE"
                  )
                    return;
                  setPending(true);
                  setError("");
                  try {
                    const result = await api<{ backup: { name: string } }>(
                      "/account/change",
                      "POST",
                      {
                        revision: preview.revision,
                        amounts_recorded: recorded,
                        confirmation,
                      },
                    );
                    onChanged(result.backup.name);
                  } catch (error) {
                    setError((error as Error).message);
                  } finally {
                    setPending(false);
                  }
                }}
              >
                {error && (
                  <p className="notice danger" role="alert">
                    {error}
                  </p>
                )}
                <fieldset disabled={pending}>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={recorded}
                      required
                      onChange={(event) => setRecorded(event.target.checked)}
                    />
                    J’ai recopié les enveloppes, leurs codes et leurs montants.
                  </label>
                  <label>
                    Saisissez CHANGER DE COMPTE pour confirmer
                    <input
                      value={confirmation}
                      required
                      autoComplete="off"
                      onChange={(event) => setConfirmation(event.target.value)}
                    />
                  </label>
                  <button
                    className="button primary"
                    type="submit"
                    disabled={!recorded || confirmation !== "CHANGER DE COMPTE"}
                  >
                    {pending
                      ? "Sauvegarde et remise à zéro…"
                      : "Sauvegarder et réinitialiser le suivi"}
                  </button>
                </fieldset>
              </form>
            </>
          )}
          <div className="button-group">
            <button
              className="button"
              disabled={pending || loading}
              onClick={loadPreview}
            >
              Actualiser le récapitulatif
            </button>
            <button
              className="text-button"
              disabled={pending}
              onClick={() => setOpen(false)}
            >
              Annuler
            </button>
          </div>
        </Modal>
      )}
    </section>
  );
}
