import { useEffect, useState } from "react";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  ArrowRightLeft,
  Check,
  CircleAlert,
  Copy,
  Landmark,
  ListFilter,
  LogOut,
  Settings,
  ShieldCheck,
  Wallet,
  WalletCards,
} from "lucide-react";
import { api, downloadExport, setCsrf } from "./api";
import BankingPanel, { BankSyncButton, type BankStatus } from "./BankingPanel";
import Onboarding from "./Onboarding";
import ReservesPage from "./ReservesPage";
import BackupsPanel from "./BackupsPanel";
import {
  AsyncForm,
  BalanceChart,
  Empty,
  EnvelopeIcon,
  LoadState,
  Modal,
  MovementList,
  Pager,
  useLoad,
} from "./components";
import {
  CorrectionForm,
  EnvelopeForm,
  ImportForm,
  ReallocationForm,
} from "./forms";
import { cents, day, money, signedMoney } from "./money";
import type {
  Account,
  ChartPoint,
  Dashboard,
  Envelope,
  Movement,
  Session,
  Summary,
  Transaction,
} from "./types";

type Page = "envelopes" | "movements" | "review" | "bank" | "settings";
type Dialog =
  | { type: "create" | "import" }
  | { type: "edit" | "archive"; envelope: Envelope }
  | { type: "reallocate"; source?: number }
  | { type: "correct"; transactionId: number };
type MovementPage = { items: Movement[]; total: number };

const navigation = [
  {
    id: "envelopes" as const,
    label: "Enveloppes",
    short: "Enveloppes",
    icon: WalletCards,
  },
  {
    id: "movements" as const,
    label: "Opérations",
    short: "Opérations",
    icon: ArrowRightLeft,
  },
  {
    id: "bank" as const,
    label: "Banque",
    short: "Banque",
    icon: Landmark,
  },
  {
    id: "settings" as const,
    label: "Réglages",
    short: "Réglages",
    icon: Settings,
  },
];

function Brand() {
  return (
    <div className="brand">
      <span>
        <WalletCards size={23} strokeWidth={1.6} />
      </span>
      <div>
        LootSplit<small>RÉSERVES FAMILIALES</small>
      </div>
    </div>
  );
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [restoring, setRestoring] = useState(true);
  useEffect(() => {
    api<Session>("/auth/session")
      .then((value) => {
        setCsrf(value.csrf_token);
        setSession(value);
      })
      .catch(() => {})
      .finally(() => setRestoring(false));
    const expired = () => {
      setCsrf("");
      setSession(null);
    };
    window.addEventListener("session-expired", expired);
    return () => window.removeEventListener("session-expired", expired);
  }, []);
  if (restoring)
    return (
      <div className="splash">
        <Brand />
        <LoadState loading error="" />
      </div>
    );
  if (!session)
    return (
      <div className="login-screen">
        <section className="login-story">
          <Brand />
          <div>
            <p className="eyebrow">UN COMPTE. PLUSIEURS PROJETS.</p>
            <h1>
              Chaque euro
              <br />à sa place.
            </h1>
            <p>
              Vos vacances, les cadeaux, les imprévus.
              <br />
              Retrouvez simplement ce que vous avez mis de côté.
            </p>
          </div>
          <span className="privacy">
            <ShieldCheck size={17} /> Vos réserves restent chez vous.
          </span>
        </section>
        <main className="login-form">
          <div className="login-card">
            <span className="envelope-icon tone-shield">
              <Wallet size={24} />
            </span>
            <h2>Bienvenue chez vous.</h2>
            <p className="muted">
              Connectez-vous pour retrouver vos réserves familiales.
            </p>
            <AsyncForm
              label="Ouvrir mes réserves"
              onSubmit={async (values) => {
                const value = await api<Session>("/auth/login", "POST", {
                  token: String(values.get("token")),
                });
                setCsrf(value.csrf_token);
                setSession(value);
              }}
            >
              <label>
                Clé d’accès
                <input
                  type="password"
                  name="token"
                  required
                  autoComplete="current-password"
                  autoFocus
                  placeholder="Votre clé administrateur"
                />
              </label>
              <small>
                La clé d’accès est celle définie dans la configuration du
                serveur.
              </small>
            </AsyncForm>
            <p className="login-footer">
              <ShieldCheck size={14} /> Connexion locale · Aucune donnée
              bancaire partagée
            </p>
          </div>
        </main>
      </div>
    );
  return (
    <Bootstrap
      onLogout={async () => {
        await api("/auth/logout", "POST");
        setCsrf("");
        setSession(null);
      }}
    />
  );
}

function Bootstrap({ onLogout }: { onLogout: () => Promise<void> }) {
  const [revision, setRevision] = useState(0);
  const accounts = useLoad<Account[]>("/accounts", revision);
  if (!accounts.data)
    return (
      <div className="splash">
        <Brand />
        <LoadState loading={accounts.loading} error={accounts.error} />
        {accounts.error && (
          <button className="button" onClick={() => setRevision((v) => v + 1)}>
            Réessayer
          </button>
        )}
      </div>
    );
  if (!accounts.data.length)
    return (
      <Onboarding
        onDone={() => setRevision((v) => v + 1)}
        onLogout={onLogout}
      />
    );
  return <Workspace onLogout={onLogout} account={accounts.data[0]} />;
}

function Workspace({
  onLogout,
  account,
}: {
  onLogout: () => Promise<void>;
  account: Account;
}) {
  const [page, setPage] = useState<Page>("envelopes");
  const [selected, setSelected] = useState<number | null>(null);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [revision, setRevision] = useState(0);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const dashboard = useLoad<Dashboard>("/dashboard", revision);
  const bank = useLoad<BankStatus>("/banking/status", revision);
  const envelopes = useLoad<Envelope[]>(
    "/envelopes?include_archived=true",
    revision,
  );
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(""), 5000);
    return () => clearTimeout(id);
  }, [toast]);
  const refresh = () => setRevision((value) => value + 1);
  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") setRevision((v) => v + 1);
    }, 60_000);
    return () => clearInterval(timer);
  }, []);
  const saved = (message = "Modification enregistrée.") => {
    setDialog(null);
    setToast(message);
    refresh();
  };
  const open = (id: number) => {
    setSelected(id);
    setPage("envelopes");
  };
  const correct = (id: number) =>
    setDialog({ type: "correct", transactionId: id });
  const go = (value: Page) => {
    setPage(value);
    setSelected(null);
    setError("");
  };
  const active = (envelopes.data || []).filter((e) => e.status === "ACTIVE");
  return (
    <div className="app-layout tool-layout">
      <aside className="sidebar">
        <Brand />
        <p className="sidebar-label">MON ESPACE FAMILLE</p>
        <nav aria-label="Navigation principale">
          {navigation.map((item) => (
            <button
              key={item.id}
              className={
                page === item.id ||
                (page === "review" && item.id === "movements")
                  ? "nav-item active"
                  : "nav-item"
              }
              aria-current={
                page === item.id ||
                (page === "review" && item.id === "movements")
                  ? "page"
                  : undefined
              }
              onClick={() => go(item.id)}
            >
              <item.icon size={20} />
              <span className="desktop-label">{item.label}</span>
              <span className="mobile-label">{item.short}</span>
              {item.id === "movements" && !!dashboard.data?.anomalies.count && (
                <span className="badge">{dashboard.data.anomalies.count}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-label">
            <ShieldCheck size={17} />
            <span>
              Hébergé chez vous<small>Vos données, votre foyer.</small>
            </span>
          </div>
          <button
            className="nav-item"
            onClick={() => onLogout().catch((e) => setError(e.message))}
          >
            <LogOut size={18} />
            Se déconnecter
          </button>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar tool-account-bar">
          <div className="account-context">
            <span className="eyebrow">COMPTE SUIVI</span>
            <strong>
              {account.name}{" "}
              <span className="muted">{bank.data?.masked_iban}</span>
            </strong>
            <small>
              {bank.error
                ? "État bancaire indisponible"
                : !bank.data
                  ? "Vérification de la connexion…"
                  : bank.data.error
                    ? "Actualisation bancaire en échec"
                    : bank.data.connected
                      ? bank.data.last_success_at
                        ? `Dernier import bancaire : ${new Date(bank.data.last_success_at).toLocaleString("fr-FR")}`
                        : "Compte associé · premier import attendu"
                      : "Import CSV · aucune banque associée"}
            </small>
          </div>
          <div className="topbar-actions">
            {bank.data && !bank.data.connected && page !== "bank" && (
              <button className="button" onClick={() => go("bank")}>
                Connecter ma banque
              </button>
            )}
            <BankSyncButton revision={revision} onChanged={refresh} />
            <button
              className="button"
              onClick={() => setDialog({ type: "import" })}
            >
              <ArrowDownToLine size={16} />
              Importer un relevé CSV
            </button>
            <button
              className="icon-button mobile-logout"
              aria-label="Se déconnecter"
              onClick={() => onLogout().catch((e) => setError(e.message))}
            >
              <LogOut size={17} />
            </button>
          </div>
        </header>
        <main className="main-content">
          {toast && (
            <div role="status" className="toast">
              <Check size={17} />
              {toast}
            </div>
          )}
          {error && (
            <p className="notice danger" role="alert">
              {error}
            </p>
          )}
          <LoadState
            loading={dashboard.loading || envelopes.loading}
            error={dashboard.error || envelopes.error}
          />
          {(dashboard.error || envelopes.error) && (
            <button className="button" onClick={refresh}>
              Réessayer
            </button>
          )}
          {dashboard.data && envelopes.data && (
            <>
              {bank.error && (
                <p className="notice warning" role="status">
                  L’état bancaire n’a pas pu être vérifié.{" "}
                  <button className="text-button" onClick={refresh}>
                    Réessayer
                  </button>
                </p>
              )}
              {bank.data?.error && (
                <div className="notice warning" role="status">
                  <strong>La dernière actualisation bancaire a échoué.</strong>
                  <p>{bank.data.error}</p>
                  <button className="button" onClick={() => go("bank")}>
                    Vérifier la connexion
                  </button>
                </div>
              )}
              {page === "envelopes" &&
                (selected ? (
                  <EnvelopeDetail
                    id={selected}
                    revision={revision}
                    back={() => setSelected(null)}
                    correct={correct}
                    onEdit={(envelope) => setDialog({ type: "edit", envelope })}
                    onArchive={(envelope) =>
                      setDialog({ type: "archive", envelope })
                    }
                    onReallocate={() =>
                      setDialog({ type: "reallocate", source: selected })
                    }
                  />
                ) : (
                  <ReservesPage
                    dashboard={dashboard.data}
                    envelopes={envelopes.data}
                    open={open}
                    onCreate={() => setDialog({ type: "create" })}
                    onReview={() => go("review")}
                    onReallocate={(source) =>
                      setDialog({ type: "reallocate", source })
                    }
                  />
                ))}
              {(page === "movements" || page === "review") && (
                <div className="tabs operation-tabs">
                  <button
                    aria-pressed={page === "movements"}
                    className={page === "movements" ? "selected" : ""}
                    onClick={() => go("movements")}
                  >
                    Toutes les écritures
                  </button>
                  <button
                    aria-pressed={page === "review"}
                    className={page === "review" ? "selected" : ""}
                    onClick={() => go("review")}
                  >
                    À traiter ({dashboard.data.anomalies.count})
                  </button>
                </div>
              )}
              {page === "bank" && (
                <>
                  <div className="page-heading">
                    <div>
                      <h1>Banque</h1>
                      <p className="muted">
                        Connexion, compte suivi et actualisation.
                      </p>
                    </div>
                  </div>
                  <BankingPanel revision={revision} onChanged={refresh} />
                </>
              )}
              {page === "movements" && (
                <MovementsPage
                  envelopes={envelopes.data}
                  revision={revision}
                  correct={correct}
                />
              )}
              {page === "review" && (
                <ReviewPage
                  dashboard={dashboard.data}
                  envelopes={envelopes.data}
                  revision={revision}
                  correct={correct}
                  open={open}
                  onImport={() => setDialog({ type: "import" })}
                />
              )}
              {page === "settings" && (
                <SettingsPage
                  revision={revision}
                  envelopes={envelopes.data}
                  account={account}
                  onImport={() => setDialog({ type: "import" })}
                  onExport={(format) =>
                    downloadExport(format).catch((e) => setError(e.message))
                  }
                  notify={setToast}
                />
              )}
            </>
          )}
        </main>
        <footer className="app-footer">
          LootSplit · Réserves familiales
          <span>Accès bancaire en lecture seule</span>
        </footer>
      </div>
      {dialog && (
        <Modal
          title={
            dialog.type === "create"
              ? "Créer une enveloppe"
              : dialog.type === "edit"
                ? "Modifier l’enveloppe"
                : dialog.type === "import"
                  ? "Importer un relevé CSV"
                  : dialog.type === "correct"
                    ? "Affecter une opération"
                    : dialog.type === "archive"
                      ? "Archiver cette enveloppe"
                      : "Déplacer entre enveloppes"
          }
          onClose={() => setDialog(null)}
        >
          {dialog.type === "create" && (
            <EnvelopeForm onSaved={() => saved("Enveloppe créée.")} />
          )}
          {dialog.type === "edit" && (
            <EnvelopeForm envelope={dialog.envelope} onSaved={() => saved()} />
          )}
          {dialog.type === "import" && <ImportForm onSaved={refresh} />}
          {dialog.type === "correct" && (
            <CorrectionForm
              transactionId={dialog.transactionId}
              envelopes={active}
              onSaved={() => saved("Affectation enregistrée.")}
            />
          )}
          {dialog.type === "reallocate" && (
            <ReallocationForm
              envelopes={active}
              initialSource={dialog.source}
              onSaved={() => saved("Réaffectation enregistrée.")}
            />
          )}
          {dialog.type === "archive" &&
            (dialog.envelope.balance_cents !== 0 ? (
              <>
                <p>
                  Le solde de <strong>{dialog.envelope.name}</strong> est de{" "}
                  {money(dialog.envelope.balance_cents)}. Il doit être ramené à
                  zéro avant l’archivage.
                </p>
                <button
                  className="button primary"
                  onClick={() =>
                    setDialog({
                      type: "reallocate",
                      source: dialog.envelope.id,
                    })
                  }
                >
                  Réaffecter le solde
                </button>
              </>
            ) : (
              <AsyncForm
                label="Confirmer l’archivage"
                onSubmit={async () => {
                  await api(`/envelopes/${dialog.envelope.id}/archive`, "POST");
                  saved("Enveloppe archivée.");
                }}
              >
                <p>
                  L’enveloppe <strong>{dialog.envelope.name}</strong> quittera
                  le tableau de bord. Son historique restera disponible dans les
                  archives.
                </p>
              </AsyncForm>
            ))}
        </Modal>
      )}
    </div>
  );
}

function EnvelopeDetail({
  id,
  revision,
  back,
  correct,
  onEdit,
  onArchive,
  onReallocate,
}: {
  id: number;
  revision: number;
  back: () => void;
  correct: (id: number) => void;
  onEdit: (envelope: Envelope) => void;
  onArchive: (envelope: Envelope) => void;
  onReallocate: () => void;
}) {
  const [year, setYear] = useState(new Date().getFullYear());
  const [page, setPage] = useState(0);
  const summary = useLoad<Summary>(
    `/envelopes/${id}/summary?year=${year}`,
    revision,
  );
  const chart = useLoad<ChartPoint[]>(
    `/envelopes/${id}/chart?year=${year}`,
    revision,
  );
  const history = useLoad<MovementPage>(
    `/movements?envelope_id=${id}&since=${year}-01-01&until=${year}-12-31&limit=25&offset=${page * 25}`,
    revision,
  );
  const envelope = summary.data;
  return (
    <>
      <button className="text-button back-button" onClick={back}>
        <ArrowLeft size={16} />
        Toutes les enveloppes
      </button>
      <LoadState loading={summary.loading} error={summary.error} />
      {envelope && (
        <>
          <div className="page-heading">
            <div className="detail-title">
              <EnvelopeIcon envelope={envelope} />
              <div>
                <p className="eyebrow">
                  {envelope.code || "ENVELOPPE SYSTÈME"}
                  {envelope.status === "ARCHIVED" ? " · ARCHIVÉE" : ""}
                </p>
                <h1>{envelope.name}</h1>
              </div>
            </div>
            <div className="button-group">
              {envelope.status === "ACTIVE" && (
                <>
                  <button className="button primary" onClick={onReallocate}>
                    <ArrowRightLeft size={16} />
                    Déplacer entre enveloppes
                  </button>
                  {!envelope.is_system && (
                    <>
                      <button
                        className="button"
                        onClick={() => onEdit(envelope)}
                      >
                        Modifier
                      </button>
                      <button
                        className="button"
                        onClick={() => onArchive(envelope)}
                      >
                        Archiver
                      </button>
                    </>
                  )}
                </>
              )}
            </div>
          </div>
          {envelope.description && (
            <p className="muted">{envelope.description}</p>
          )}
          <div className="summary-grid">
            <section className="panel">
              <span>Solde actuel</span>
              <strong
                className={envelope.balance_cents < 0 ? "negative-text" : ""}
              >
                {money(envelope.balance_cents)}
              </strong>
            </section>
            <section className="panel">
              <span>Entrées en {year}</span>
              <strong>{signedMoney(envelope.in_cents)}</strong>
            </section>
            <section className="panel">
              <span>Sorties en {year}</span>
              <strong>{signedMoney(envelope.out_cents)}</strong>
            </section>
          </div>
          <section className="panel">
            <div className="section-heading">
              <h2>Au fil de l’année</h2>
              <label className="year-select">
                <span className="sr-only">Année</span>
                <select
                  aria-label="Année"
                  value={year}
                  onChange={(event) => {
                    setYear(Number(event.target.value));
                    setPage(0);
                  }}
                >
                  {Array.from(
                    { length: 30 },
                    (_, index) => new Date().getFullYear() - index,
                  ).map((value) => (
                    <option value={value} key={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <LoadState loading={chart.loading} error={chart.error} />
            {chart.data && <BalanceChart points={chart.data} />}
          </section>
          <section className="panel">
            <div className="section-heading">
              <h2>Historique de l’enveloppe</h2>
              <span className="muted">{year}</span>
            </div>
            <LoadState loading={history.loading} error={history.error} />
            {history.data && (
              <>
                <MovementList
                  items={history.data.items}
                  onCorrect={correct}
                  showEnvelope={false}
                />
                <Pager
                  page={page}
                  total={history.data.total}
                  onPage={setPage}
                />
              </>
            )}
          </section>
        </>
      )}
    </>
  );
}

function MovementsPage({
  envelopes,
  revision,
  correct,
}: {
  envelopes: Envelope[];
  revision: number;
  correct: (id: number) => void;
}) {
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [filterError, setFilterError] = useState("");
  const [page, setPage] = useState(0);
  const params = new URLSearchParams({
    ...filters,
    limit: "25",
    offset: String(page * 25),
  });
  const movements = useLoad<MovementPage>(`/movements?${params}`, revision);
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Opérations</h1>
          <p className="muted">
            Opérations bancaires, réaffectations et corrections.
          </p>
        </div>
      </div>
      <section className="panel filters">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            try {
              const values = new FormData(event.currentTarget);
              const next: Record<string, string> = {};
              for (const [key, value] of values)
                if (String(value))
                  next[key] = key.endsWith("_cents")
                    ? String(cents(String(value)))
                    : String(value);
              setFilters(next);
              setPage(0);
              setFilterError("");
            } catch (e) {
              setFilterError((e as Error).message);
            }
          }}
        >
          <div className="filter-grid">
            <label>
              Rechercher
              <input
                name="text"
                maxLength={200}
                placeholder="Un libellé, un motif…"
              />
            </label>
            <label>
              Enveloppe
              <select aria-label="Enveloppe" name="envelope_id">
                <option value="">Toutes les enveloppes</option>
                {envelopes.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                    {e.status === "ARCHIVED" ? " (archive)" : ""}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Type
              <select aria-label="Type" name="kind">
                <option value="">Tous les mouvements</option>
                <option value="BANK">Opération bancaire</option>
                <option value="REALLOCATION">Réaffectation</option>
                <option value="CORRECTION">Correction</option>
                <option value="INITIAL">Solde initial</option>
              </select>
            </label>
          </div>
          <div className="filter-grid secondary-filters">
            <label>
              Du
              <input name="since" type="date" />
            </label>
            <label>
              Au
              <input name="until" type="date" />
            </label>
            <label>
              Montant min. (€)
              <input
                name="min_cents"
                inputMode="decimal"
                placeholder="−800,00"
              />
            </label>
            <label>
              Montant max. (€)
              <input
                name="max_cents"
                inputMode="decimal"
                placeholder="1 000,00"
              />
            </label>
            <button className="button" type="submit">
              <ListFilter size={16} />
              Filtrer
            </button>
          </div>
          <FilterError />
        </form>
      </section>
      <section className="panel">
        <div className="section-heading">
          <h2>Tous les mouvements</h2>
          <span className="muted">
            {movements.data?.total ?? "…"} écriture(s)
          </span>
        </div>
        <LoadState loading={movements.loading} error={movements.error} />
        {movements.data && (
          <>
            <MovementList items={movements.data.items} onCorrect={correct} />
            <Pager page={page} total={movements.data.total} onPage={setPage} />
          </>
        )}
      </section>
    </>
  );
  function FilterError() {
    return filterError ? (
      <p role="alert" className="notice danger">
        {filterError}
      </p>
    ) : null;
  }
}

function ReviewPage({
  dashboard,
  envelopes,
  revision,
  correct,
  open,
  onImport,
}: {
  dashboard: Dashboard;
  envelopes: Envelope[];
  revision: number;
  correct: (id: number) => void;
  open: (id: number) => void;
  onImport: () => void;
}) {
  const unassigned = useLoad<Transaction[]>(
    "/transactions/unassigned",
    revision,
  );
  const { anomalies, reconciliation } = dashboard;
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>
            À vérifier <span className="heading-count">{anomalies.count}</span>
          </h1>
          <p className="muted">
            Opérations à affecter, écarts et autres points à contrôler.
          </p>
        </div>
      </div>
      {!reconciliation.reconciled && (
        <section className="panel anomaly-panel">
          <CircleAlert />
          <div>
            <h2>Un écart de {money(reconciliation.difference_cents)}</h2>
            <p>
              Le solde bancaire est de{" "}
              {money(reconciliation.bank_balance_cents)}, pour{" "}
              {money(reconciliation.envelopes_total_cents)} répartis dans les
              enveloppes. Vérifiez que toutes les opérations du relevé ont été
              importées.
            </p>
            <button className="button" onClick={onImport}>
              Importer un relevé
            </button>
          </div>
        </section>
      )}
      {reconciliation.last_sync_error && (
        <p className="notice danger">{reconciliation.last_sync_error}</p>
      )}
      {anomalies.negative_envelope_ids.map((id) => (
        <section className="panel anomaly-panel" key={id}>
          <CircleAlert />
          <div>
            <h2>{envelopes.find((e) => e.id === id)?.name} est négative</h2>
            <p>
              Vérifiez l’affectation des retraits ou réaffectez un montant
              depuis une autre enveloppe.
            </p>
            <button className="text-button" onClick={() => open(id)}>
              Voir l’enveloppe <ArrowRight size={16} />
            </button>
          </div>
        </section>
      ))}
      {anomalies.suspected_duplicate_fingerprints.length > 0 && (
        <div className="notice warning">
          <strong>
            {anomalies.suspected_duplicate_fingerprints.length} groupe(s)
            d’opérations identiques à examiner
          </strong>
          <p>
            Plusieurs opérations ont les mêmes dates, montant et libellé. Elles
            ont été conservées avec leurs identifiants distincts. Comparez-les
            au relevé bancaire dans les opérations.
          </p>
        </div>
      )}
      <section className="panel">
        <div className="section-heading">
          <h2>Opérations à affecter</h2>
          <span className="subtle-pill">{unassigned.data?.length ?? "…"}</span>
        </div>
        <LoadState loading={unassigned.loading} error={unassigned.error} />
        {unassigned.data &&
          (unassigned.data.length ? (
            unassigned.data.map((transaction) => (
              <article className="qualification-row" key={transaction.id}>
                <div>
                  <strong>{transaction.raw_label}</strong>
                  <span className="muted">{day(transaction.booking_date)}</span>
                </div>
                <strong>{signedMoney(transaction.amount_cents)}</strong>
                <button
                  className="button"
                  onClick={() => correct(transaction.id)}
                >
                  Affecter
                </button>
              </article>
            ))
          ) : (
            <Empty
              title="Tout est à sa place"
              detail="Aucune opération bancaire ne reste à affecter."
            />
          ))}
      </section>
    </>
  );
}

function SettingsPage({
  revision,
  envelopes,
  account,
  onImport,
  onExport,
  notify,
}: {
  revision: number;
  envelopes: Envelope[];
  account: Account;
  onImport: () => void;
  onExport: (format: "json" | "csv") => void;
  notify: (message: string) => void;
}) {
  const [copyError, setCopyError] = useState("");
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Réglages</h1>
          <p className="muted">
            Retrouvez vos codes et gardez une copie de vos données.
          </p>
        </div>
      </div>
      <section className="panel settings-section">
        <div className="section-heading">
          <h2>Votre compte de réserve</h2>
          <span className="subtle-pill">Import manuel</span>
        </div>
        <p>
          Suivi démarré le {day(account.activation_date)}. Les opérations
          suivantes peuvent être intégrées depuis un relevé CSV.
        </p>
        <button className="button primary" onClick={onImport}>
          <ArrowDownToLine size={16} />
          Importer un relevé CSV
        </button>
      </section>
      <BackupsPanel revision={revision} />
      <section className="panel settings-section">
        <h2>Vos codes bancaires</h2>
        <p className="muted">
          Copiez un code dans le libellé du virement correspondant depuis votre
          application bancaire.
        </p>
        {copyError && (
          <p role="alert" className="notice warning">
            {copyError}
          </p>
        )}
        {envelopes
          .filter((e) => !e.is_system && e.status === "ACTIVE")
          .map((envelope) => (
            <div className="code-row" key={envelope.id}>
              <span>{envelope.name}</span>
              <code>{envelope.code}</code>
              <button
                className="text-button"
                aria-label={`Copier le code de ${envelope.name}`}
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(envelope.code!);
                    notify("Code copié.");
                    setCopyError("");
                  } catch {
                    setCopyError(
                      "La copie automatique nécessite une connexion sécurisée. Sélectionnez et copiez le code affiché.",
                    );
                  }
                }}
              >
                <Copy size={15} />
                Copier
              </button>
            </div>
          ))}
      </section>
      <section className="panel settings-section">
        <h2>Exporter vos données</h2>
        <p className="muted">
          Le JSON conserve les données et l’audit. Le CSV permet de consulter
          les mouvements dans un tableur.
        </p>
        <div className="button-group">
          <button className="button" onClick={() => onExport("json")}>
            Exporter en JSON
          </button>
          <button className="button" onClick={() => onExport("csv")}>
            Exporter en CSV
          </button>
        </div>
        <p className="small muted">
          La restauration est actuellement disponible à partir d’une sauvegarde
          SQLite sur le serveur.
        </p>
      </section>
    </>
  );
}
