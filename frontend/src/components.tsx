import {
  lazy,
  Suspense,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Gift,
  Heart,
  Plane,
  School,
  ShieldCheck,
  Sun,
  Wallet,
  X,
} from "lucide-react";
import { api } from "./api";
import { day, signedMoney } from "./money";
import type { ChartPoint, Envelope, Movement } from "./types";

export function useLoad<T>(path: string, revision = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const previousPath = useRef(path);
  useEffect(() => {
    let current = true;
    setLoading(true);
    setError("");
    if (previousPath.current !== path) setData(null);
    previousPath.current = path;
    api<T>(path)
      .then((value) => {
        if (current) setData(value);
      })
      .catch((e) => {
        if (current) setError(e.message || "Le serveur est inaccessible.");
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [path, revision]);
  return { data, error, loading };
}

export function LoadState({
  loading,
  error,
}: {
  loading: boolean;
  error: string;
}) {
  if (error)
    return (
      <div role="alert" className="notice danger">
        {error}
      </div>
    );
  if (loading)
    return (
      <div role="status" className="loading">
        <span className="spinner" /> Chargement…
      </div>
    );
  return null;
}

export function AsyncForm({
  children,
  onSubmit,
  label = "Enregistrer",
  className = "",
  disabled = false,
}: {
  children: ReactNode;
  onSubmit: (data: FormData) => Promise<void>;
  label?: string;
  className?: string;
  disabled?: boolean;
}) {
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  return (
    <form
      className={`form ${className}`}
      onSubmit={async (event) => {
        event.preventDefault();
        if (pending || disabled) return;
        const values = new FormData(event.currentTarget);
        setPending(true);
        setError("");
        try {
          await onSubmit(values);
        } catch (e) {
          setError(e instanceof Error ? e.message : "Une erreur est survenue.");
        } finally {
          setPending(false);
        }
      }}
    >
      <fieldset disabled={pending || disabled}>
        {children}
        {error && (
          <p className="notice danger" role="alert">
            {error}
          </p>
        )}
        <button className="button primary" type="submit" disabled={pending}>
          {pending ? "Enregistrement…" : label}
        </button>
      </fieldset>
    </form>
  );
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    return () => element.close();
  }, []);
  return (
    <dialog ref={dialog} aria-labelledby={titleId} onCancel={onClose}>
      <header className="modal-header">
        <h2 id={titleId}>{title}</h2>
        <button className="icon-button" aria-label="Fermer" onClick={onClose}>
          <X size={20} />
        </button>
      </header>
      {children}
    </dialog>
  );
}

export const icons = {
  shield: ShieldCheck,
  sun: Sun,
  gift: Gift,
  school: School,
  plane: Plane,
  heart: Heart,
};
export function EnvelopeIcon({
  envelope,
}: {
  envelope: Pick<Envelope, "icon" | "is_system">;
}) {
  const Icon = envelope.is_system
    ? Wallet
    : icons[envelope.icon as keyof typeof icons] || Wallet;
  return (
    <span className={`envelope-icon tone-${envelope.icon || "wallet"}`}>
      <Icon size={22} strokeWidth={1.7} />
    </span>
  );
}

const Chart = lazy(() => import("./Chart"));
export function BalanceChart(props: { points: ChartPoint[]; mini?: boolean }) {
  return (
    <Suspense
      fallback={<div className={props.mini ? "mini-chart" : "balance-chart"} />}
    >
      <Chart {...props} />
    </Suspense>
  );
}

export const movementLabels: Record<Movement["kind"], string> = {
  INITIAL: "Solde initial",
  BANK: "Opération bancaire",
  REALLOCATION: "Réaffectation",
  CORRECTION: "Correction",
};

export function MovementList({
  items,
  onCorrect,
  showEnvelope = true,
}: {
  items: Movement[];
  onCorrect?: (transactionId: number) => void;
  showEnvelope?: boolean;
}) {
  if (!items.length)
    return (
      <Empty
        title="Aucun mouvement"
        detail="Les prochaines opérations apparaîtront ici."
      />
    );
  return (
    <div className="movement-list">
      {items.map((item) => (
        <article className="movement-row" key={item.id}>
          <span
            className={`movement-icon ${item.amount_cents >= 0 ? "positive" : "negative"}`}
          >
            {item.amount_cents >= 0 ? (
              <ArrowDownLeft size={18} />
            ) : (
              <ArrowUpRight size={18} />
            )}
          </span>
          <div className="movement-info">
            <strong>{item.reason || movementLabels[item.kind]}</strong>
            <span>
              {day(item.effective_date)}
              <i>·</i>
              {showEnvelope && (
                <>
                  {item.envelope_name}
                  <i>·</i>
                </>
              )}
              {movementLabels[item.kind]}
            </span>
          </div>
          <div className="movement-value">
            <strong className={item.amount_cents < 0 ? "negative-text" : ""}>
              {signedMoney(item.amount_cents)}
            </strong>
            {item.kind === "BANK" && item.transaction_id && onCorrect && (
              <button
                className="text-button"
                onClick={() => onCorrect(item.transaction_id!)}
              >
                Affecter
              </button>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

export function Empty({
  title,
  detail,
  children,
}: {
  title: string;
  detail: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <Wallet size={30} strokeWidth={1.3} />
      <h3>{title}</h3>
      <p>{detail}</p>
      {children}
    </div>
  );
}

export function Pager({
  page,
  total,
  onPage,
}: {
  page: number;
  total: number;
  onPage: (page: number) => void;
}) {
  if (total <= 25) return null;
  return (
    <div className="pager">
      <button
        className="button"
        disabled={page === 0}
        onClick={() => onPage(page - 1)}
      >
        Précédent
      </button>
      <span>
        {page * 25 + 1}–{Math.min((page + 1) * 25, total)} sur {total}
      </span>
      <button
        className="button"
        disabled={(page + 1) * 25 >= total}
        onClick={() => onPage(page + 1)}
      >
        Suivant
      </button>
    </div>
  );
}
