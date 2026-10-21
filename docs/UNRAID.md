# Déploiement Docker Compose sur Unraid

Le projet fournit un `compose.yaml` qui utilise l'image Linux `amd64` `ghcr.io/za512/lootsplit:latest`, construite et testée par GitHub Actions, puis publiée dans GitHub Container Registry (GHCR). Un seul conteneur est nécessaire : interface React, API Python, connecteur Woob et SQLite persistant. La connexion Crédit Agricole est facultative ; le CSV reste disponible sans identifiants bancaires. La validation sur votre accès bancaire réel reste à effectuer.

## Préparation

Le serveur doit disposer de Docker Compose, via l'installation ou le gestionnaire Compose de votre choix. Vérifier sa présence avec `docker compose version`. La [documentation Unraid](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/overview/) présente la gestion Docker ; Compose doit être disponible séparément.

Copier `compose.yaml` et `.env.example` sur le serveur, par exemple dans `/mnt/user/appdata/lootsplit-project`. Les sources et les outils de compilation ne sont pas nécessaires sur Unraid. Attendre la réussite du premier workflow **Docker** sur `main` dans GitHub Actions avant de télécharger l'image.

Créer un dossier réservé aux données de l'application :

```sh
mkdir -p /mnt/user/appdata/lootsplit
chown 99:100 /mnt/user/appdata/lootsplit
chmod 750 /mnt/user/appdata/lootsplit
```

Ces commandes ciblent uniquement le nouveau dossier LootSplit. Adapter `99:100` à votre configuration. Les chemins `appdata` et la convention d'identités sont décrits dans la [documentation Unraid sur les conteneurs](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/managing-and-customizing-containers/).

## Configuration

Copier `.env.example` vers `.env` dans le répertoire du projet :

```dotenv
LOOTSPLIT_ADMIN_TOKEN=REMPLACER_PAR_UN_JETON_ALEATOIRE_D_AU_MOINS_32_CARACTERES
LOOTSPLIT_IMAGE=ghcr.io/za512/lootsplit:latest
APPDATA_PATH=/mnt/user/appdata/lootsplit
PUID=99
PGID=100
PORT=8000
BIND_ADDRESS=0.0.0.0
LOOTSPLIT_SECURE_COOKIE=false
```

Générer le jeton sur un poste disposant de Python avec `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Protéger `.env`, par exemple avec `chmod 600 .env`. Le jeton permet de modifier les réserves ; il ne s'agit pas d'un identifiant bancaire. Les identifiants bancaires facultatifs se configurent séparément, comme décrit dans le guide Woob.

`PUID` et `PGID` configurent ici directement `user:` dans Compose. Le conteneur n'effectue aucun changement de propriétaire automatique. Le dossier monté doit donc être accessible en écriture à cette identité.

`BIND_ADDRESS=0.0.0.0` publie le port sur les interfaces du serveur, pour l'accès depuis le réseau local. Pour un accès uniquement par un reverse proxy installé sur l'hôte, conserver `127.0.0.1`. Utiliser HTTPS pour tout accès distant et transporter le jeton sur une connexion protégée. Configurer le reverse proxy et ses règles selon votre installation.

Les valeurs `.env` sont injectées par [l'interpolation Docker Compose](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/). Le démarrage refuse un jeton absent ou trop court.

## Accès à l'image GHCR

Lors de sa première publication, un package GHCR est privé par défaut. Pour un téléchargement sans authentification, passer sa visibilité à **Public** dans les paramètres du package GitHub si cette visibilité convient au projet. Voir la [documentation du registre GitHub](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

Si l'image reste privée, créer un jeton personnel GitHub **classic** avec le droit `read:packages` et un compte ayant accès au package. Connecter Docker au registre sur le serveur :

```sh
docker login ghcr.io -u VOTRE_IDENTIFIANT_GITHUB
```

Saisir le jeton à l'invite de mot de passe. Ce jeton sert au téléchargement par Docker ; il ne doit pas être placé dans `.env`. Le workflow utilise automatiquement son propre `GITHUB_TOKEN` pour publier.

## Lancement et vérification

Depuis le dossier du projet :

```sh
docker compose pull
docker compose up -d
docker compose ps
docker compose logs --tail=100 lootsplit
```

Ouvrir `http://IP_DU_SERVEUR:8000/` et saisir la clé d'accès définie dans `.env`. L'assistant de premier démarrage initialise les réserves. La documentation de l'API reste disponible sur `/docs`, et la santé du service sur `/health`. Le port peut être modifié par `PORT`.

Pour accéder à l'application via un reverse proxy HTTPS, définir `LOOTSPLIT_SECURE_COOKIE=true`. Garder `false` uniquement pour un accès HTTP local : un cookie Secure ne sera pas envoyé par le navigateur sur une adresse HTTP. Les sessions expirent après huit heures et sont invalidées lors du redémarrage du service.

Le conteneur fonctionne sans privilèges root, avec un système de fichiers en lecture seule et un volume `/data` inscriptible. `/data/app.db`, ses fichiers WAL éventuels et `/data/backups/` résident dans le dossier `APPDATA_PATH`. La suppression ou recréation du conteneur conserve ce dossier.

La connexion bancaire est décrite dans [le guide Woob/Crédit Agricole](WOOB.md). Configurer ses variables uniquement sur le serveur, recréer le service, puis sélectionner le compte de réserve dans les paramètres de l'application. Aucun secret bancaire n'est demandé dans la page web. Le CSV reste disponible si la banque exige une validation ou si le connecteur échoue.

## Sauvegarde et restauration

Créer une sauvegarde cohérente pendant le fonctionnement :

```sh
docker compose exec -T lootsplit python -m lootsplit.backup
```

Le fichier est créé sous `/data/backups/` avec un nom horodaté UTC et un contrôle d'intégrité SQLite. La commande utilise l'API SQLite de sauvegarde, qui prend en compte WAL. Les copies automatiques sont également activées : une première copie au démarrage, puis chaque jour à 03:00, heure de Paris, avec 7 copies quotidiennes et 4 hebdomadaires conservées. Les copies manuelles et avant migration ne sont pas supprimées par cette rotation.

Dans `.env`, les options sont `LOOTSPLIT_BACKUP_ENABLED=true`, `LOOTSPLIT_BACKUP_TIME=03:00` et `LOOTSPLIT_BACKUP_TIMEZONE=Europe/Paris`. Leur état, les erreurs, la création manuelle et les téléchargements sont accessibles dans **Réglages → Sauvegardes**. Copier régulièrement une sauvegarde vers un autre support.

Le [guide sauvegarde et restauration](BACKUPS.md) détaille la politique et la commande de restauration contrôlée vers un dossier neuf.

Pour restaurer :

1. Arrêter le service avec `docker compose stop lootsplit`.
2. Conserver une copie du dossier de données actuel, avec `app.db` et ses éventuels fichiers `app.db-wal` / `app.db-shm`.
3. Utiliser la commande `python -m lootsplit.backup --restore … --destination …` via `docker compose run --rm --no-deps --entrypoint python lootsplit`, comme décrit dans le guide. Elle crée un **nouveau dossier de données**, vérifie la sauvegarde et y publie `app.db`. La destination ne doit pas exister et son parent doit être accessible au `PUID:PGID` configuré. Aucun ancien WAL ne doit accompagner cette copie.
4. Pointer `APPDATA_PATH` vers ce nouveau dossier et relancer `docker compose up -d --force-recreate lootsplit`.
5. Vérifier les enveloppes, l'historique et la réconciliation avant de reprendre les imports.

## Mises à jour

Faire une sauvegarde avant une mise à jour, puis télécharger l'image publiée par GitHub Actions et recréer le service :

```sh
docker compose pull
docker compose up -d
```

`latest` suit les builds réussis de `main`. Pour fixer une version, définir par exemple `LOOTSPLIT_IMAGE=ghcr.io/za512/lootsplit:v0.1.0` après publication de ce tag Git. Un tag `sha-<SHA complet du commit>` est aussi publié. Pour figer exactement une image, utiliser `LOOTSPLIT_IMAGE=ghcr.io/za512/lootsplit@sha256:…` avec son digest GHCR. Relancer les mêmes commandes après modification de `.env`. Les changements éventuels de `compose.yaml` et `.env.example` restent à reporter sur le serveur.

Les versions Python sont verrouillées par `uv.lock`. Le schéma SQLite est versionné ; la migration du premier schéma ajoute l'association bancaire après une sauvegarde dans `backups/before-migration/`, en conservant l'historique existant. La validation sur votre serveur Unraid reste à effectuer.
