import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Plus,
  RefreshCw,
  WalletCards,
} from "lucide-react";
import { api } from "./api";
import type { BankStatus, Choice } from "./BankingPanel";
import { AsyncForm, LoadState, useLoad } from "./components";
import { cents, day, localDate, money } from "./money";
import type { Envelope } from "./types";

type Draft = {
  name: string;
  code: string;
  amount: string;
  existing_id?: number;
  icon?: string;
  description?: string;
  sort_order?: number;
};
const blank = (): Draft => ({ name: "", code: "", amount: "" });

export default function Onboarding({
  onDone,
  onLogout,
}: {
  onDone: () => void;
  onLogout: () => Promise<void>;
}) {
  const [step, setStep] = useState(1);
  const [revision, setRevision] = useState(0);
  const bank = useLoad<BankStatus>("/banking/status", revision);
  const existing = useLoad<Envelope[]>("/envelopes", 0);
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [choices, setChoices] = useState<Choice[] | null>(null);
  const [choiceId, setChoiceId] = useState("");
  const [manual, setManual] = useState(false);
  const [name, setName] = useState("Compte de réserve");
  const [balance, setBalance] = useState("");
  const [date, setDate] = useState(() => {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    return localDate(yesterday);
  });
  const [closingConfirmed, setClosingConfirmed] = useState(false);
  const [automatic, setAutomatic] = useState(false);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const selected = choices?.find((c) => c.choice_id === choiceId);
  useEffect(() => {
    if (existing.data && drafts === null)
      setDrafts(
        existing.data.length
          ? existing.data
              .filter((e) => !e.is_system)
              .map((e) => ({
                name: e.name,
                code: e.code || "",
                amount: "",
                existing_id: e.id,
                icon: e.icon,
                description: e.description,
                sort_order: e.sort_order,
              }))
          : [
              { name: "Sécurité", code: "RES-SECU", amount: "" },
              { name: "Vacances", code: "RES-VAC", amount: "" },
            ],
      );
  }, [existing.data, drafts]);
  let residual: number | null = null;
  try {
    if (balance.trim())
      residual =
        cents(balance) -
        (drafts || []).reduce((sum, d) => sum + cents(d.amount || "0"), 0);
  } catch {
    /* Validation à la soumission. */
  }
  const update = (index: number, field: keyof Draft, value: string) =>
    setDrafts((items) =>
      items!.map((d, i) => (i === index ? { ...d, [field]: value } : d)),
    );
  async function discover() {
    setPending(true);
    setError("");
    setChoices(null);
    setChoiceId("");
    try {
      setChoices(await api<Choice[]>("/banking/accounts", "POST"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
      setRevision((v) => v + 1);
    }
  }
  return (
    <div className="onboarding tool-onboarding">
      <header>
        <div className="brand">
          <WalletCards size={24} />
          <div>
            LootSplit<small>Configurer votre suivi</small>
          </div>
        </div>
        <button
          className="text-button"
          onClick={() => onLogout().catch((e) => setError(e.message))}
        >
          Se déconnecter
        </button>
      </header>
      <ol className="setup-steps" aria-label="Étapes de configuration">
        {["Connexion", "Compte", "Enveloppes", "Vérification"].map(
          (label, index) => (
            <li
              key={label}
              aria-current={step === index + 1 ? "step" : undefined}
            >
              <span>{index + 1}</span>
              {label}
            </li>
          ),
        )}
      </ol>
      <main>
        {error && (
          <p role="alert" className="notice danger">
            {error}
          </p>
        )}
        {step === 1 && (
          <>
            <h1>Connectez votre banque</h1>
            <p className="lead">
              Vérifiez l’accès bancaire, puis choisissez le compte de vos
              réserves.
            </p>
            <section className="panel">
              <div className="section-heading">
                <h2>Crédit Agricole</h2>
                <span className="subtle-pill">Lecture seule</span>
              </div>
              <LoadState
                loading={bank.loading && !bank.data}
                error={bank.error}
              />
              {bank.data && (
                <>
                  {!bank.data.configured && (
                    <div className="notice warning">
                      <strong>Configuration nécessaire sur le serveur</strong>
                      <p>
                        {!bank.data.credentials_configured
                          ? "Renseignez la caisse régionale, l’identifiant et le mot de passe dans la configuration Docker Compose, puis recréez le conteneur. Les secrets restent sur votre serveur."
                          : "Le module bancaire est absent. Utilisez une image Docker LootSplit incluant le connecteur Crédit Agricole."}
                      </p>
                      <details>
                        <summary>Aide à la configuration Docker</summary>
                        <p>
                          Renseignez LOOTSPLIT_BANK_WEBSITE,
                          LOOTSPLIT_BANK_LOGIN et LOOTSPLIT_BANK_PASSWORD, ou
                          les variantes LOGIN_FILE et PASSWORD_FILE pour les
                          fichiers de secrets. Le guide docs/WOOB.md décrit les
                          valeurs attendues.
                        </p>
                      </details>
                    </div>
                  )}
                  {bank.data.error && !choices && (
                    <p className="notice warning">{bank.data.error}</p>
                  )}
                  {!bank.data.configured ? (
                    <button
                      className="button"
                      disabled={bank.loading}
                      onClick={() => setRevision((v) => v + 1)}
                    >
                      <RefreshCw size={16} />
                      Revérifier la configuration
                    </button>
                  ) : (
                    <button
                      className="button primary"
                      disabled={pending || bank.data.running}
                      onClick={discover}
                    >
                      <RefreshCw size={16} />
                      {pending
                        ? "Connexion à la banque…"
                        : "Tester la connexion"}
                    </button>
                  )}
                </>
              )}
              {choices &&
                (choices.length ? (
                  <div className="notice success" role="status">
                    <p>
                      Connexion vérifiée · {choices.length} compte(s)
                      compatible(s).
                    </p>
                    <button
                      className="button primary"
                      onClick={() => {
                        setManual(false);
                        setStep(2);
                      }}
                    >
                      Choisir le compte <ArrowRight size={16} />
                    </button>
                  </div>
                ) : (
                  <p className="notice warning">
                    Aucun compte de réserve compatible en euros n’a été trouvé.
                    Vous pouvez réessayer ou utiliser des relevés CSV.
                  </p>
                ))}
            </section>
            <button
              className="text-button"
              onClick={() => {
                setManual(true);
                setAutomatic(false);
                setError("");
                setStep(2);
              }}
            >
              Continuer avec des relevés CSV
            </button>
          </>
        )}
        {step === 2 && (
          <>
            <h1>Quel compte voulez-vous suivre ?</h1>
            <p className="lead">
              Un seul compte est suivi dans cette instance.
            </p>
            <AsyncForm
              key="account"
              label="Utiliser ce compte"
              onSubmit={async () => {
                if (!manual && !selected)
                  throw new Error("Choisissez un compte.");
                if (manual && !name.trim())
                  throw new Error("Indiquez un nom de compte.");
                setError("");
                setStep(3);
              }}
            >
              {manual ? (
                <label>
                  Nom du compte
                  <input
                    required
                    maxLength={100}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </label>
              ) : (
                <fieldset className="account-choices">
                  <legend>Compte de réserve à suivre</legend>
                  {choices?.map((c) => (
                    <label className="account-choice" key={c.choice_id}>
                      <input
                        required
                        type="radio"
                        name="choice"
                        value={c.choice_id}
                        checked={choiceId === c.choice_id}
                        onChange={() => {
                          setChoiceId(c.choice_id);
                          setName(c.name);
                          setClosingConfirmed(false);
                        }}
                      />
                      <span>
                        <strong>{c.name}</strong>
                        <small>{c.masked_iban}</small>
                      </span>
                      <strong>{money(c.balance_cents)}</strong>
                    </label>
                  ))}
                  <p className="small muted">
                    Ces soldes sont actuels. Vous confirmerez le solde de
                    clôture à l’étape suivante.
                  </p>
                </fieldset>
              )}
              <button
                type="button"
                className="text-button"
                onClick={() => setStep(1)}
              >
                <ArrowLeft size={15} />
                Retour à la connexion
              </button>
            </AsyncForm>
          </>
        )}
        {step === 3 && (
          <>
            <h1>Répartissez votre solde de départ</h1>
            <p className="lead">
              {name}{" "}
              {manual ? "· Import CSV" : `· ${selected?.masked_iban || ""}`}
            </p>
            <LoadState loading={existing.loading} error={existing.error} />
            <AsyncForm
              key="allocation"
              disabled={drafts === null}
              label="Vérifier la répartition"
              onSubmit={async () => {
                if (cents(balance) < 0 || residual === null)
                  throw new Error(
                    "Indiquez un solde positif ou nul et des montants valides.",
                  );
                if ((drafts || []).some((d) => cents(d.amount || "0") < 0))
                  throw new Error(
                    "Les montants initiaux doivent être positifs ou nuls.",
                  );
                if (residual < 0)
                  throw new Error(
                    `La répartition dépasse le solde de ${money(-residual)}.`,
                  );
                const codes = (drafts || []).map((d) =>
                  d.code.trim().toUpperCase(),
                );
                if (new Set(codes).size !== codes.length)
                  throw new Error(
                    "Chaque enveloppe doit avoir un code différent.",
                  );
                if ((drafts || []).some((d) => !d.name.trim()))
                  throw new Error("Donnez un nom à chaque enveloppe.");
                setStep(4);
              }}
            >
              <section className="panel">
                <h2>Point de départ</h2>
                <div className="form-grid">
                  <label>
                    Date du solde initial (fin de journée)
                    <input
                      type="date"
                      required
                      max={localDate()}
                      value={date}
                      onChange={(e) => {
                        setDate(e.target.value);
                        setClosingConfirmed(false);
                      }}
                    />
                  </label>
                  <label>
                    Solde à la fin de cette journée (€)
                    <input
                      inputMode="decimal"
                      required
                      value={balance}
                      onChange={(e) => {
                        setBalance(e.target.value);
                        setClosingConfirmed(false);
                      }}
                      placeholder="Ex. 12 480,00"
                    />
                  </label>
                </div>
                {!manual && selected && (
                  <p className="small muted">
                    Solde actuel observé : {money(selected.balance_cents)}. Il
                    peut être différent du solde à la date choisie.
                  </p>
                )}
                <p className="notice subtle">
                  Utilisez le solde à la fin de cette journée. Seules les
                  opérations des jours suivants seront importées.
                </p>
                <label className="checkbox-label">
                  <input
                    required
                    type="checkbox"
                    checked={closingConfirmed}
                    onChange={(e) => setClosingConfirmed(e.target.checked)}
                  />
                  Je confirme le solde à la fin de la journée choisie.
                </label>
              </section>
              <section className="panel">
                <div className="section-heading">
                  <h2>Vos premières enveloppes</h2>
                  <button
                    type="button"
                    className="button"
                    disabled={(drafts?.length || 0) >= 100}
                    onClick={() => setDrafts((d) => [...(d || []), blank()])}
                  >
                    <Plus size={15} />
                    Ajouter une enveloppe
                  </button>
                </div>
                {drafts?.map((d, i) => (
                  <div
                    className="draft-envelope"
                    key={d.existing_id || `new-${i}`}
                  >
                    <label>
                      Nom de l’enveloppe {i + 1}
                      <input
                        required
                        maxLength={100}
                        value={d.name}
                        onChange={(e) => update(i, "name", e.target.value)}
                      />
                    </label>
                    <label>
                      Code virement {i + 1}
                      <input
                        required
                        maxLength={20}
                        pattern="[A-Za-z0-9_\-]{1,20}"
                        value={d.code}
                        onChange={(e) => update(i, "code", e.target.value)}
                      />
                    </label>
                    <label>
                      Montant initial pour {d.name || `l’enveloppe ${i + 1}`}
                      <input
                        inputMode="decimal"
                        value={d.amount}
                        onChange={(e) => update(i, "amount", e.target.value)}
                        placeholder="0,00"
                      />
                    </label>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() =>
                        setDrafts((items) =>
                          items!.filter((_, index) => index !== i),
                        )
                      }
                      aria-label={`Retirer ${d.name || `l’enveloppe ${i + 1}`}`}
                    >
                      Retirer
                    </button>
                  </div>
                ))}
                <p className="small muted">
                  Le code permet de reconnaître les virements qui le
                  contiennent. Lettres, chiffres, tirets et underscores.
                </p>
                <div
                  className={`setup-residual ${residual !== null && residual < 0 ? "negative-text" : ""}`}
                  role="status"
                >
                  Restera non affecté{" "}
                  <strong>{residual === null ? "—" : money(residual)}</strong>
                </div>
              </section>
              <button
                type="button"
                className="text-button"
                onClick={() => setStep(2)}
              >
                <ArrowLeft size={15} />
                Modifier le compte
              </button>
            </AsyncForm>
          </>
        )}
        {step === 4 && (
          <>
            <h1>Vérifiez avant de démarrer</h1>
            <p className="lead">
              La répartition initiale sera validée une seule fois.
            </p>
            <AsyncForm
              key="confirm"
              label="Créer le suivi"
              onSubmit={async () => {
                await api("/setup", "POST", {
                  name: name.trim(),
                  activation_date: date,
                  opening_balance_cents: cents(balance),
                  envelopes: (drafts || []).map((d, i) => ({
                    name: d.name.trim(),
                    code: d.code.trim().toUpperCase(),
                    amount_cents: cents(d.amount || "0"),
                    ...(d.existing_id ? { existing_id: d.existing_id } : {}),
                    icon: d.icon || "",
                    description: d.description || "",
                    sort_order: d.sort_order ?? i,
                  })),
                  ...(manual
                    ? {}
                    : {
                        bank_choice_id: choiceId,
                        bank_confirmed: true,
                        auto_sync_enabled: automatic,
                      }),
                });
                onDone();
              }}
            >
              <section className="panel">
                <dl className="setup-summary">
                  <div>
                    <dt>Compte</dt>
                    <dd>
                      {name} {manual ? "· Import CSV" : selected?.masked_iban}
                    </dd>
                  </div>
                  <div>
                    <dt>Solde au {day(date)}, fin de journée</dt>
                    <dd>{money(cents(balance))}</dd>
                  </div>
                  {drafts?.map((d, i) => (
                    <div key={i}>
                      <dt>
                        {d.name} <code>{d.code}</code>
                      </dt>
                      <dd>{money(cents(d.amount || "0"))}</dd>
                    </div>
                  ))}
                  <div>
                    <dt>Non affecté</dt>
                    <dd>{money(residual || 0)}</dd>
                  </div>
                  <div>
                    <dt>Total vérifié</dt>
                    <dd>{money(cents(balance))}</dd>
                  </div>
                </dl>
              </section>
              {!manual && (
                <>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={automatic}
                      onChange={(e) => setAutomatic(e.target.checked)}
                    />
                    Activer l’actualisation automatique toutes les 6 heures
                  </label>
                  <p className="small muted">
                    Une première actualisation sera lancée après la création.
                    Elle vérifiera l’écart avec le solde bancaire.
                  </p>
                </>
              )}
              <label className="checkbox-label">
                <input type="checkbox" required />
                Je confirme le compte, la date et la répartition ci-dessus.
              </label>
              <button
                type="button"
                className="text-button"
                onClick={() => setStep(3)}
              >
                Modifier la répartition
              </button>
              <button
                type="button"
                className="text-button"
                onClick={() => setStep(1)}
              >
                Revenir à la connexion bancaire
              </button>
            </AsyncForm>
          </>
        )}
      </main>
    </div>
  );
}
