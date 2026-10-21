import { useEffect, useState } from "react";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  ArrowRightLeft,
  Check,
  CircleAlert,
  Copy,
  LayoutDashboard,
  ListFilter,
  LogOut,
  Plus,
  RefreshCw,
  Settings,
  ShieldCheck,
  Wallet,
  WalletCards,
} from "lucide-react";
import { api, downloadExport, setCsrf } from "./api";
import BankingPanel, { BankSyncButton } from "./BankingPanel";
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
import { cents, day, localDate, money, signedMoney } from "./money";
import type {
  AllocatedTransaction,
  Account,
  ChartPoint,
  Dashboard,
  Envelope,
  Movement,
  Session,
  Summary,
  Transaction,
} from "./types";

type Page = "dashboard" | "envelopes" | "movements" | "review" | "settings";
type Dialog =
  | { type: "create" | "import" }
  | { type: "edit" | "archive"; envelope: Envelope }
  | { type: "reallocate"; source?: number }
  | { type: "correct"; transactionId: number };
type MovementPage = { items: Movement[]; total: number };

const navigation = [
  {
    id: "dashboard" as const,
    label: "Tableau de bord",
    short: "Accueil",
    icon: LayoutDashboard,
  },
  {
    id: "envelopes" as const,
    label: "Enveloppes",
    short: "Enveloppes",
    icon: WalletCards,
  },
  {
    id: "movements" as const,
    label: "Mouvements",
    short: "Mouvements",
    icon: ArrowRightLeft,
  },
  {
    id: "review" as const,
    label: "À vérifier",
    short: "À vérifier",
    icon: CircleAlert,
  },
  {
    id: "settings" as const,
    label: "Paramètres",
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
        réserves<small>PAR LOOTSPLIT</small>
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

function Onboarding({
  onDone,
  onLogout,
}: {
  onDone: () => void;
  onLogout: () => Promise<void>;
}) {
  const [revision, setRevision] = useState(0);
  const envelopes = useLoad<Envelope[]>("/envelopes", revision);
  const [create, setCreate] = useState(false);
  const [balance, setBalance] = useState("");
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [signoutError, setSignoutError] = useState("");
  let residual: number | null = null;
  try {
    residual =
      cents(balance || "0") -
      Object.values(amounts).reduce(
        (sum, value) => sum + cents(value || "0"),
        0,
      );
  } catch {
    /* Le formulaire affichera l'erreur à la validation. */
  }
  return (
    <div className="onboarding">
      <header>
        <Brand />
        <button
          className="text-button"
          onClick={() => onLogout().catch((e) => setSignoutError(e.message))}
        >
          Se déconnecter
        </button>
      </header>
      <main>
        <p className="eyebrow">BIENVENUE DANS VOS RÉSERVES</p>
        <h1>Partons de ce que vous avez.</h1>
        <p className="lead">
          Un solde réel, puis une place pour chaque projet.
        </p>
        {signoutError && (
          <p role="alert" className="notice danger">
            {signoutError}
          </p>
        )}
        <LoadState loading={envelopes.loading} error={envelopes.error} />
        <AsyncForm
          label="Démarrer mes réserves"
          disabled={envelopes.loading || !envelopes.data}
          onSubmit={async (values) => {
            const allocations = Object.fromEntries(
              (envelopes.data || []).map((e) => [
                e.id,
                cents(amounts[e.id] || "0"),
              ]),
            );
            await api("/setup", "POST", {
              name: "Compte de réserve",
              activation_date: values.get("date"),
              opening_balance_cents: cents(balance),
              allocations,
            });
            onDone();
          }}
        >
          <section className="panel setup-section">
            <div className="section-number">01</div>
            <h2>Votre point de départ</h2>
            <div className="form-grid">
              <label>
                Date de démarrage
                <input
                  name="date"
                  type="date"
                  required
                  max={localDate()}
                  defaultValue={localDate()}
                />
              </label>
              <label>
                Solde du compte de réserve à cette date (€)
                <input
                  name="balance"
                  inputMode="decimal"
                  required
                  value={balance}
                  onChange={(event) => setBalance(event.target.value)}
                  placeholder="Ex. 9 365,00"
                />
              </label>
            </div>
            <p className="notice subtle">
              Utilisez le solde à la fin de cette journée. Les opérations des
              jours suivants seront ajoutées après import. Cette répartition
              initiale ne sera validée qu’une fois.
            </p>
          </section>
          <section className="panel setup-section">
            <div className="section-number">02</div>
            <div className="section-heading">
              <h2>Répartissez votre épargne</h2>
              <button
                type="button"
                className="text-button"
                onClick={() => setCreate(true)}
              >
                <Plus size={16} />
                Créer une enveloppe
              </button>
            </div>
            {!envelopes.data?.length && (
              <p className="muted">
                Créez vos premières enveloppes : sécurité, vacances, cadeaux…
                Vous pourrez en ajouter d’autres ensuite.
              </p>
            )}
            {envelopes.data?.map((e) => (
              <div className="allocation-row" key={e.id}>
                <EnvelopeIcon envelope={e} />
                <div>
                  <strong>{e.name}</strong>
                  <code>{e.code}</code>
                </div>
                <label>
                  <span className="sr-only">Montant initial pour {e.name}</span>
                  <input
                    name={`allocation-${e.id}`}
                    aria-label={`Montant initial pour ${e.name}`}
                    inputMode="decimal"
                    value={amounts[e.id] || ""}
                    onChange={(event) =>
                      setAmounts({ ...amounts, [e.id]: event.target.value })
                    }
                    placeholder="0,00"
                  />
                  <span>€</span>
                </label>
              </div>
            ))}
            <div className="setup-residual">
              <span>Reste dans « Non affecté »</span>
              <strong
                className={
                  residual !== null && residual < 0 ? "negative-text" : ""
                }
              >
                {residual === null ? "—" : money(residual)}
              </strong>
            </div>
          </section>
        </AsyncForm>
      </main>
      {create && (
        <Modal title="Créer une enveloppe" onClose={() => setCreate(false)}>
          <EnvelopeForm
            onSaved={() => {
              setCreate(false);
              setRevision((v) => v + 1);
            }}
          />
        </Modal>
      )}
    </div>
  );
}

function Workspace({
  onLogout,
  account,
}: {
  onLogout: () => Promise<void>;
  account: Account;
}) {
  const [page, setPage] = useState<Page>("dashboard");
  const [selected, setSelected] = useState<number | null>(null);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [revision, setRevision] = useState(0);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const dashboard = useLoad<Dashboard>("/dashboard", revision);
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
    <div className="app-layout">
      <aside className="sidebar">
        <Brand />
        <p className="sidebar-label">MON ESPACE FAMILLE</p>
        <nav aria-label="Navigation principale">
          {navigation.map((item) => (
            <button
              key={item.id}
              className={page === item.id ? "nav-item active" : "nav-item"}
              aria-current={page === item.id ? "page" : undefined}
              onClick={() => go(item.id)}
            >
              <item.icon size={20} />
              <span className="desktop-label">{item.label}</span>
              <span className="mobile-label">{item.short}</span>
              {item.id === "review" && !!dashboard.data?.anomalies.count && (
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
        <header className="topbar">
          <div className="breadcrumb">
            Mon foyer <span>/</span>{" "}
            {selected
              ? "Détail de l’enveloppe"
              : navigation.find((n) => n.id === page)?.label}
          </div>
          <div className="topbar-actions">
            <span className="account-pill">
              <span className="status-dot" />
              {account.name}
            </span>
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
              {page === "dashboard" && (
                <DashboardPage
                  dashboard={dashboard.data}
                  revision={revision}
                  open={open}
                  correct={correct}
                  onCreate={() => setDialog({ type: "create" })}
                  onImport={() => setDialog({ type: "import" })}
                  onReview={() => go("review")}
                  onReallocate={() => setDialog({ type: "reallocate" })}
                  onSynced={refresh}
                />
              )}
              {page === "envelopes" &&
                (selected ? (
                  <EnvelopeDetail
                    id={selected}
                    revision={revision}
                    back={() => setSelected(null)}
                    correct={correct}
                    onEdit={(envelope) => setDialog({ type: "edit", envelope })}
                    onReallocate={() =>
                      setDialog({ type: "reallocate", source: selected })
                    }
                  />
                ) : (
                  <EnvelopesPage
                    envelopes={envelopes.data}
                    open={open}
                    onCreate={() => setDialog({ type: "create" })}
                    onEdit={(envelope) => setDialog({ type: "edit", envelope })}
                    onArchive={(envelope) =>
                      setDialog({ type: "archive", envelope })
                    }
                  />
                ))}
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
                  onChanged={refresh}
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
          Une place pour chacun de vos projets.<span>Réserves · LootSplit</span>
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
                      : "Réaffecter un montant"
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

function DashboardPage({
  onSynced,
  dashboard,
  revision,
  open,
  correct,
  onCreate,
  onImport,
  onReview,
  onReallocate,
}: {
  onSynced: () => void;
  dashboard: Dashboard;
  revision: number;
  open: (id: number) => void;
  correct: (id: number) => void;
  onCreate: () => void;
  onImport: () => void;
  onReview: () => void;
  onReallocate: () => void;
}) {
  const recent = useLoad<AllocatedTransaction[]>(
    "/transactions?limit=5",
    revision,
  );
  const reconciliation = dashboard.reconciliation;
  const reserves = dashboard.envelopes.filter((e) => !e.is_system);
  const sync = reconciliation.last_sync_at;
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">L’ESSENTIEL, EN UN COUP D’ŒIL</p>
          <h1>Vos projets prennent forme.</h1>
          <p className="muted">
            Voici ce que vous avez réellement mis de côté.
          </p>
        </div>
        <div className="button-group">
          <BankSyncButton revision={revision} onChanged={onSynced} />
          <button className="button" onClick={onImport}>
            <ArrowDownToLine size={17} />
            Importer un relevé
          </button>
        </div>
      </div>
      <section className="balance-overview">
        <div className="balance-main">
          <div className="balance-top">
            <span>
              <Wallet size={18} /> VOTRE COMPTE DE RÉSERVE
            </span>
            <span
              className={`reconciled ${reconciliation.reconciled ? "" : "warning-status"}`}
            >
              {reconciliation.reconciled ? (
                <Check size={14} />
              ) : (
                <CircleAlert size={14} />
              )}
              {reconciliation.reconciled ? "Réconcilié" : "Écart à vérifier"}
            </span>
          </div>
          <p className="hero-amount">
            {money(reconciliation.bank_balance_cents)}
          </p>
          <p className="balance-caption">Un seul compte, tous vos projets.</p>
          <div className="sync-info">
            <RefreshCw size={13} />
            {sync
              ? `Dernier relevé intégré le ${new Date(sync.endsWith("Z") || /[+-]\d\d:\d\d$/.test(sync) ? sync : `${sync}Z`).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}`
              : "Aucun relevé intégré pour le moment"}
          </div>
        </div>
        <div className="balance-breakdown">
          <div>
            <span>Répartis dans vos enveloppes</span>
            <strong>
              {money(
                reconciliation.envelopes_total_cents -
                  reconciliation.unassigned_cents,
              )}
            </strong>
          </div>
          <div>
            <span>Non affecté</span>
            <strong>{money(reconciliation.unassigned_cents)}</strong>
          </div>
          <div className="total-line">
            <span>Total des enveloppes</span>
            <strong>{money(reconciliation.envelopes_total_cents)}</strong>
          </div>
        </div>
      </section>
      {!reconciliation.reconciled && (
        <button className="notice danger notice-button" onClick={onReview}>
          <CircleAlert size={20} />
          <span>
            <strong>
              Un écart de {money(reconciliation.difference_cents)} est à
              vérifier.
            </strong>
            <small>Comparez le dernier relevé aux opérations importées.</small>
          </span>
          <ArrowRight size={18} />
        </button>
      )}
      {dashboard.anomalies.count > 0 && reconciliation.reconciled && (
        <button className="notice warning notice-button" onClick={onReview}>
          <CircleAlert size={19} />
          <span>
            {dashboard.anomalies.count} élément(s) attendent votre vérification.
          </span>
          <ArrowRight size={17} />
        </button>
      )}
      <div className="section-heading spaced">
        <div>
          <h2>Vos enveloppes</h2>
          <p className="muted">Chaque réserve a sa raison d’être.</p>
        </div>
        <div className="button-group">
          <button
            className="text-button"
            onClick={onReallocate}
            disabled={dashboard.envelopes.length < 2}
          >
            <ArrowRightLeft size={16} />
            Réaffecter
          </button>
          <button className="button" onClick={onCreate}>
            <Plus size={17} />
            Nouvelle enveloppe
          </button>
        </div>
      </div>
      {!reserves.length ? (
        <section className="panel">
          <Empty
            title="Faites une place à vos projets"
            detail="Créez votre première enveloppe et donnez un rôle à votre épargne."
          >
            <button className="button primary" onClick={onCreate}>
              Créer une enveloppe
            </button>
          </Empty>
        </section>
      ) : (
        <div className="envelope-grid">
          {reserves.map((e) => (
            <EnvelopeCard envelope={e} key={e.id} onClick={() => open(e.id)} />
          ))}
        </div>
      )}
      <section className="panel recent-panel">
        <div className="section-heading">
          <h2>Dernières opérations bancaires</h2>
          <span className="subtle-pill">Compte de réserve</span>
        </div>
        <LoadState loading={recent.loading} error={recent.error} />
        {recent.data && (
          <MovementList
            items={recent.data.map((t) => ({
              id: t.id,
              transaction_id: t.id,
              envelope_id: t.allocation.envelope_id,
              envelope_name: t.envelope_name,
              effective_date: t.booking_date,
              amount_cents: t.amount_cents,
              reason: t.raw_label,
              kind: "BANK",
              event_id: "",
            }))}
            onCorrect={correct}
          />
        )}
      </section>
    </>
  );
}

function EnvelopeCard({
  envelope,
  onClick,
}: {
  envelope: Envelope;
  onClick: () => void;
}) {
  return (
    <button className="envelope-card" onClick={onClick}>
      <div className="card-top">
        <EnvelopeIcon envelope={envelope} />
        <ArrowRight size={17} className="card-arrow" />
      </div>
      <h3>{envelope.name}</h3>
      <p
        className={`card-amount ${envelope.balance_cents < 0 ? "negative-text" : ""}`}
      >
        {money(envelope.balance_cents)}
      </p>
      {envelope.balance_cents < 0 && (
        <span className="negative-warning">Cette enveloppe est négative</span>
      )}
      {envelope.chart && <BalanceChart points={envelope.chart} mini />}
      <div className="card-month">
        {envelope.month_movement_count ? (
          <>
            <span>Ce mois-ci</span>
            <strong>{signedMoney(envelope.month_net_cents || 0)}</strong>
          </>
        ) : (
          <span>Aucun mouvement ce mois-ci</span>
        )}
      </div>
      <p className="card-last">
        {envelope.last_movement_date
          ? `Dernier mouvement · ${day(envelope.last_movement_date)}`
          : "Aucun mouvement enregistré"}
      </p>
    </button>
  );
}

function EnvelopesPage({
  envelopes,
  open,
  onCreate,
  onEdit,
  onArchive,
}: {
  envelopes: Envelope[];
  open: (id: number) => void;
  onCreate: () => void;
  onEdit: (envelope: Envelope) => void;
  onArchive: (envelope: Envelope) => void;
}) {
  const [archives, setArchives] = useState(false);
  const visible = envelopes.filter(
    (e) => (e.status === "ARCHIVED") === archives,
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">UNE RÉSERVE POUR CHAQUE ENVIE</p>
          <h1>Vos enveloppes</h1>
          <p className="muted">Organisez votre épargne à votre rythme.</p>
        </div>
        <button className="button primary" onClick={onCreate}>
          <Plus size={17} />
          Nouvelle enveloppe
        </button>
      </div>
      <div className="tabs">
        <button
          className={!archives ? "selected" : ""}
          onClick={() => setArchives(false)}
        >
          Actives
        </button>
        <button
          className={archives ? "selected" : ""}
          onClick={() => setArchives(true)}
        >
          Archives
        </button>
      </div>
      <section className="panel">
        {!visible.length ? (
          <Empty
            title="Aucune enveloppe archivée"
            detail="Les enveloppes archivées conserveront ici tout leur historique."
          />
        ) : (
          visible.map((e) => (
            <div className="envelope-table-row" key={e.id}>
              <EnvelopeIcon envelope={e} />
              <button
                className="envelope-name text-button"
                onClick={() => open(e.id)}
              >
                <strong>{e.name}</strong>
                <code>{e.code || "Enveloppe système"}</code>
              </button>
              <strong className="table-amount">{money(e.balance_cents)}</strong>
              <div className="button-group">
                {!e.is_system && e.status === "ACTIVE" && (
                  <>
                    <button className="text-button" onClick={() => onEdit(e)}>
                      Modifier
                    </button>
                    <button
                      className="text-button muted"
                      onClick={() => onArchive(e)}
                    >
                      Archiver
                    </button>
                  </>
                )}
                <button
                  className="icon-button"
                  aria-label={`Voir ${e.name}`}
                  onClick={() => open(e.id)}
                >
                  <ArrowRight size={18} />
                </button>
              </div>
            </div>
          ))
        )}
      </section>
    </>
  );
}

function EnvelopeDetail({
  id,
  revision,
  back,
  correct,
  onEdit,
  onReallocate,
}: {
  id: number;
  revision: number;
  back: () => void;
  correct: (id: number) => void;
  onEdit: (envelope: Envelope) => void;
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
                    Réaffecter
                  </button>
                  {!envelope.is_system && (
                    <button className="button" onClick={() => onEdit(envelope)}>
                      Modifier
                    </button>
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
          <p className="eyebrow">LE FIL DE VOTRE ÉPARGNE</p>
          <h1>Mouvements</h1>
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
          <p className="eyebrow">POUR GARDER L’ESPRIT TRANQUILLE</p>
          <h1>
            À vérifier <span className="heading-count">{anomalies.count}</span>
          </h1>
          <p className="muted">
            Quelques points à regarder pour des réserves toujours justes.
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
            au relevé bancaire dans Mouvements.
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
  onChanged,
  envelopes,
  account,
  onImport,
  onExport,
  notify,
}: {
  revision: number;
  onChanged: () => void;
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
          <p className="eyebrow">VOTRE ESPACE, À VOTRE FAÇON</p>
          <h1>Paramètres</h1>
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
      <BankingPanel revision={revision} onChanged={onChanged} />
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
