# LootSplit — Réserves

Suivi des réserves familiales présentes sur un compte de réserve unique. Le besoin initial est décrit dans [le PRD](docs/PRD.md).

## État du développement

L'application comprend un moteur métier Python, une API FastAPI, une interface React/TypeScript en français et un déploiement Docker Compose. L'interface permet d'initialiser le compte de réserve, de créer les enveloppes, d'y répartir le solde, d'importer un CSV, de qualifier les transactions, de corriger une affectation, de réaffecter un montant et de consulter les soldes, anomalies, historiques et graphiques annuels. Les exports JSON/CSV et une commande de sauvegarde SQLite sont disponibles.

Le connecteur Woob Crédit Agricole est disponible, avec sélection explicite du compte de réserve, synchronisation manuelle et planification configurable. Il reste à valider avec votre accès bancaire réel et sur Unraid. Le CSV continue de fonctionner indépendamment. Les sauvegardes quotidiennes avec rotation, leur téléchargement et la restauration SQLite vers un dossier neuf sont disponibles. La réimportation JSON n'est pas implémentée.

## Démarrage avec Docker Compose

1. Copier `.env.example` vers `.env`.
2. Générer un jeton avec `python -c "import secrets; print(secrets.token_urlsafe(48))"` et renseigner `LOOTSPLIT_ADMIN_TOKEN` dans `.env`.
3. Créer le dossier `data` et lui donner les droits d'écriture correspondant à `PUID:PGID` sur Linux.
4. Lancer :

```sh
docker compose pull
docker compose up -d
```

Compose utilise l'image `ghcr.io/za512/lootsplit:latest`, construite et testée par GitHub Actions, sans compilation sur le serveur. Attendre la première publication du workflow **Docker** avant le premier lancement. Seuls `compose.yaml` et `.env` sont nécessaires sur le serveur, en plus du dossier de données. Si le package GHCR est privé, s'authentifier comme décrit dans le [guide Unraid](docs/UNRAID.md#accès-à-limage-ghcr).

Ouvrir [l'application](http://localhost:8000/) et saisir la clé configurée dans `LOOTSPLIT_ADMIN_TOKEN`. Au premier démarrage, l'assistant propose de choisir la date et le solde initial, créer les enveloppes et répartir l'épargne. Ensuite, utiliser les pages Tableau de bord, Enveloppes, Mouvements, À vérifier et Paramètres. Les imports CSV et exports sont accessibles depuis Paramètres.

La session dure huit heures et utilise un cookie HttpOnly avec une protection CSRF sur les modifications. La clé administrateur n'est pas conservée dans le stockage du navigateur. Un redémarrage du serveur nécessite de se reconnecter. Pour un accès en HTTPS, définir `LOOTSPLIT_SECURE_COOKIE=true`.

Pour connecter la banque, suivre le [guide Woob/Crédit Agricole](docs/WOOB.md). Les identifiants se configurent uniquement sur le serveur. La planification reste désactivée jusqu'à son activation explicite dans les paramètres.

Les sauvegardes automatiques sont activées : première copie après le démarrage, puis chaque jour à 03:00, heure de Paris. Le service garde 7 copies quotidiennes et 4 hebdomadaires, ainsi que les copies manuelles séparées. **Paramètres → Sauvegardes** permet de consulter leur état, créer une copie et la télécharger. Voir le [guide de sauvegarde et restauration](docs/BACKUPS.md).

La [documentation interactive de l'API](http://localhost:8000/docs) reste disponible : cliquer sur **Authorize** et saisir le jeton administrateur, sans le préfixe `Bearer`. Les routes métier `/api/` sont protégées. `/health` ne révèle aucune donnée métier.

Le conteneur utilise un seul processus applicatif et stocke SQLite dans `/data/app.db`. Les données restent dans le dossier hôte `APPDATA_PATH` lors de la recréation du conteneur. Le lancement écoute par défaut uniquement sur l'hôte local ; le [guide Unraid](docs/UNRAID.md) décrit la configuration réseau et `appdata`.

Le schéma SQLite est désormais versionné. La migration du premier schéma ajoute les paramètres bancaires et réalise d'abord une sauvegarde dans `/data/backups/before-migration/`. Les transactions, affectations et historiques existants sont conservés. Sauvegarder aussi le volume avant toute mise à jour.

Pour mettre à jour, créer une sauvegarde, puis relancer `docker compose pull` et `docker compose up -d`. La variable `LOOTSPLIT_IMAGE` permet de sélectionner une version précise ou un digest au lieu de `latest`.

## Construction et publication de l'image

Le workflow [Docker](.github/workflows/docker.yml) construit l'image Linux `amd64` depuis le Dockerfile (interface, API et module bancaire), puis exécute le test Compose d'authentification, de sauvegarde et de persistance. Il publie ensuite **cette même image testée** dans GitHub Container Registry avec le `GITHUB_TOKEN` du dépôt ; aucun secret de registre supplémentaire n'est nécessaire.

- Chaque push sur `main` publie `ghcr.io/za512/lootsplit:latest` et un tag `sha-<SHA complet du commit>`.
- Chaque tag Git `v*` publie le tag correspondant, par exemple `ghcr.io/za512/lootsplit:v0.1.0`, ainsi que le tag du commit, sans déplacer `latest`.
- Les pull requests vers `main` construisent et testent l'image sans la publier.
- Un lancement manuel depuis l'onglet **Actions → Docker → Run workflow** permet de republier `main` ou un tag `v*`. Les autres branches sont seulement testées.

Le téléchargement ne met pas à jour automatiquement un conteneur déjà démarré : exécuter `docker compose up -d` après `docker compose pull`.

## Essai de l'API dans `/docs` (facultatif)

1. Appeler `POST /api/envelopes` avec `{"name":"Vacances","code":"RES-VAC"}`, puis créer les autres enveloppes souhaitées.
2. Appeler `POST /api/setup` avec le solde bancaire **à la clôture de la date de démarrage**, en centimes, et les identifiants retournés :

```json
{
  "name": "Compte de réserve",
  "activation_date": "2026-09-30",
  "opening_balance_cents": 100000,
  "allocations": {"1": 80000}
}
```

Le reliquat de 20 000 centimes est placé dans `NON AFFECTÉ`. L'initialisation est définitive dans ce premier lot.

3. Appeler `POST /api/import/csv` :

```json
{
  "bank_balance_cents": 111500,
  "content": "booking_date;amount;raw_label;provider_transaction_id\n2026-10-01;115,00;VIR RES-VAC;demo-001\n"
}
```

Le solde communiqué doit correspondre aux opérations comptabilisées du relevé importé. Une différence est signalée, sans création d'opération de compensation.

4. Consulter `GET /api/dashboard`, `/api/reconciliation`, `/api/transactions` et `/api/anomalies`.
5. Utiliser `PATCH /api/transactions/{id}/allocation` pour qualifier ou corriger une transaction, puis `POST /api/reallocations` pour déplacer un montant virtuellement.

Les dates futures sont refusées. Les exemples ci-dessus sont des données fictives ; utiliser un dossier de données de test avant de saisir une répartition réelle.

## Développement local

Python 3.12 à 3.14 et [uv](https://docs.astral.sh/uv/) sont requis ; Docker utilise Python 3.13. Le frontend utilise Node.js 22.12 ou supérieur. Les versions résolues sont conservées dans `uv.lock` et `frontend/package-lock.json`.

```powershell
uv sync --frozen
$env:LOOTSPLIT_ADMIN_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(48))"
uv run uvicorn lootsplit.api:app --reload
```

Dans un second terminal :

```powershell
cd frontend
npm ci
npm run dev
```

Ouvrir l'adresse indiquée par Vite (habituellement `http://127.0.0.1:5173`). Le serveur de développement transmet `/api` au backend sur le port 8000. En production, le Dockerfile construit l'interface et FastAPI la sert sur le même port que l'API. Pour servir aussi l'interface depuis FastAPI en local, lancer `npm run build` dans `frontend` puis redémarrer le backend.

La base locale est créée dans `data/app.db`. Pour vérifier les changements :

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

Dans `frontend` :

```sh
npm run build
npm test
npm run format:check
npx playwright install chromium
npm run test:e2e
```

Les tests navigateur lancent un serveur et une base temporaires sur le port 8765, avec des données fictives. Ils exigent un build frontend préalable et ne touchent pas à `data/app.db`.

Le test de conteneur isolé construit une image locale `lootsplit:smoke`, exerce l'API avec SQLite, recrée le conteneur et vérifie la persistance. Docker doit fonctionner :

```sh
uv run python scripts/smoke_compose.py
```

Pour tester une image déjà construite et présente dans Docker, sans build ni téléchargement (comme dans GitHub Actions) :

```sh
uv run python scripts/smoke_compose.py --image lootsplit:smoke
```

Voir [les décisions d'architecture et la suite](docs/ARCHITECTURE.md) et [le format CSV](docs/CSV.md).
