import { useState } from "react";
import { Download, HardDrive, ShieldCheck } from "lucide-react";
import { api } from "./api";
import { LoadState, useLoad } from "./components";

type BackupFile = {
  name: string;
  kind: "daily" | "weekly" | "manual" | "legacy";
  created_at: string;
  size_bytes: number;
};
type BackupStatus = {
  enabled: boolean;
  time: string;
  timezone: string;
  running: boolean;
  daily_retention: number;
  weekly_retention: number;
  last_success_at: string | null;
  last_automatic_at: string | null;
  next_backup_at: string | null;
  last_error: string | null;
  files: BackupFile[];
};
const labels = {
  daily: "Quotidienne",
  weekly: "Hebdomadaire",
  manual: "Manuelle",
  legacy: "Manuelle (serveur)",
};

export default function BackupsPanel({ revision }: { revision: number }) {
  const [reload, setReload] = useState(0);
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState("");
  const [message, setMessage] = useState("");
  const [expanded, setExpanded] = useState(false);
  const {
    data: status,
    loading,
    error,
  } = useLoad<BackupStatus>("/backups", revision + reload);
  const formatDate = (value: string) =>
    new Date(value).toLocaleString("fr-FR", {
      dateStyle: "short",
      timeStyle: "short",
      timeZone: status?.timezone || "Europe/Paris",
    });
  return (
    <section className="panel settings-section backup-panel">
      <div className="section-heading">
        <h2>Sauvegardes</h2>
        {status && (
          <span className="subtle-pill">
            <ShieldCheck size={12} />
            {status.enabled
              ? "Protection automatique"
              : "Automatisation désactivée"}
          </span>
        )}
      </div>
      <LoadState loading={loading && !status} error={error} />
      {status && (
        <>
          <p className="muted">
            {status.enabled
              ? `Une sauvegarde chaque jour à ${status.time} (${status.timezone}).`
              : "Les sauvegardes automatiques sont désactivées dans la configuration du serveur."}{" "}
            Les copies restent sur votre serveur.
          </p>
          <dl className="bank-dates">
            <div>
              <dt>Dernière sauvegarde réussie</dt>
              <dd>
                {status.last_success_at
                  ? formatDate(status.last_success_at)
                  : "Aucune pour le moment"}
              </dd>
            </div>
            {status.next_backup_at && (
              <div>
                <dt>Prochaine sauvegarde automatique</dt>
                <dd>{formatDate(status.next_backup_at)}</dd>
              </div>
            )}
          </dl>
          <p className="small muted">
            Conservation : {status.daily_retention} quotidiennes et{" "}
            {status.weekly_retention} hebdomadaires. Les copies manuelles sont
            conservées séparément.
          </p>
          {status.last_error && (
            <p className="notice warning" role="status">
              {status.last_error}
            </p>
          )}
          <button
            className="button primary"
            disabled={pending || status.running}
            onClick={async () => {
              setPending(true);
              setActionError("");
              setMessage("");
              try {
                await api("/backups", "POST");
                setMessage("Sauvegarde créée et vérifiée.");
              } catch (error) {
                setActionError((error as Error).message);
              } finally {
                setPending(false);
                setReload((v) => v + 1);
              }
            }}
          >
            <HardDrive size={16} />
            {pending || status.running
              ? "Sauvegarde en cours…"
              : "Sauvegarder maintenant"}
          </button>
          {actionError && (
            <p className="notice danger" role="alert">
              {actionError}
            </p>
          )}
          {message && (
            <p className="notice success" role="status">
              {message}
            </p>
          )}
          {!!status.files.length && (
            <div className="backup-files">
              {(expanded ? status.files : status.files.slice(0, 5)).map(
                (file) => (
                  <article
                    className="backup-file"
                    key={`${file.kind}-${file.name}`}
                  >
                    <span className="envelope-icon">
                      <HardDrive size={17} />
                    </span>
                    <div>
                      <strong>{labels[file.kind]}</strong>
                      <span>
                        {formatDate(file.created_at)} ·{" "}
                        {new Intl.NumberFormat("fr-FR", {
                          maximumFractionDigits: 1,
                        }).format(file.size_bytes / 1024)}{" "}
                        Ko
                      </span>
                    </div>
                    <a
                      className="text-button"
                      aria-label={`Télécharger ${labels[file.kind].toLowerCase()} du ${formatDate(file.created_at)}`}
                      href={`/api/backups/${encodeURIComponent(file.name)}/download`}
                      download
                    >
                      <Download size={15} />
                      <span>Télécharger</span>
                    </a>
                  </article>
                ),
              )}
              {status.files.length > 5 && (
                <button
                  className="text-button"
                  onClick={() => setExpanded((v) => !v)}
                >
                  {expanded
                    ? "Réduire la liste"
                    : `Voir les ${status.files.length} sauvegardes`}
                </button>
              )}
            </div>
          )}
          <p className="small muted backup-footnote">
            Téléchargez régulièrement une copie sur un autre support. La
            restauration se fait dans un dossier neuf sur le serveur.
          </p>
        </>
      )}
    </section>
  );
}
