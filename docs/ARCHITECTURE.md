# Architecture et décisions

Le [PRD v1](PRD.md) reste la référence fonctionnelle. Le nom du dépôt est LootSplit ; « Réserves » reste le nom de travail du produit.

## Organisation

```text
src/lootsplit/
  domain.py       règles pures, centimes, normalisation, matching, courbes
  models.py       persistance SQLAlchemy
  database.py     SQLite, contraintes, transactions et journaux immuables
  service.py      cas d'usage transactionnels
  connectors.py   protocole BankConnector et adaptateur CSV
  sync.py         orchestration d'un connecteur, gestion des échecs
  api.py          validation des entrées, authentification et routes HTTP
  backup.py       copie SQLite cohérente à chaud
```

Le moteur ne dépend ni de Woob ni de React. `BankConnector` expose uniquement des lectures. L'orchestrateur récupère les données hors verrou SQLite, puis importe tout le lot dans une transaction. Une exception annule toutes les modifications du lot. L'échec est enregistré séparément avec un message générique, sans conserver le texte potentiellement sensible du fournisseur.

`woob_connector.py` adapte le module Crédit Agricole `cragr`. `woob_worker.py` exécute les lectures dans un sous-processus limité à trois minutes, sans journaux HTTP ni configuration persistante de Woob. Le module est installé depuis une révision officielle figée et une archive vérifiée pendant la construction Docker. Les secrets proviennent des variables d'environnement ou de fichiers montés ; ils ne figurent jamais dans les arguments de commande, l'API de statut, SQLite ou les exports. Voir [le guide bancaire](WOOB.md) pour la configuration et les limites de validation réelle.

`banking.py` sérialise les lectures bancaires, conserve en mémoire les choix de compte opaques pendant dix minutes et persiste uniquement l'association au compte, la fréquence et les dates/erreurs de synchronisation. La planification est désactivée par défaut. Un thread vérifie les échéances toutes les trente secondes ; les actions bancaires requises suspendent les nouvelles tentatives automatiques. Le solde et les affectations ne sont pas modifiés lors de la sélection du compte.

L'interface réside dans `frontend/` : React, TypeScript, Vite, Recharts et des icônes Lucide. Elle ne charge ni police distante ni télémétrie. Les graphiques sont chargés séparément de l'écran de connexion. Le Dockerfile construit les assets avec Node.js, puis les copie dans l'image Python ; un seul service et un seul port servent l'ensemble. En développement, le proxy Vite transmet les appels API au backend.

`auth.py` gère une session administrateur locale, avec un cookie opaque HttpOnly, SameSite strict et une expiration absolue de huit heures. Seule l'empreinte du cookie et son jeton CSRF sont gardés en mémoire côté serveur. Les modifications authentifiées par cookie exigent l'en-tête CSRF correspondant ; les appels scripts peuvent toujours utiliser le jeton Bearer. La clé administrateur n'est pas stockée dans localStorage ni sessionStorage. Les connexions sont limitées en fréquence. Le paramètre `LOOTSPLIT_SECURE_COOKIE=true` active Secure pour un accès HTTPS. Les sessions sont invalidées au redémarrage ; le déploiement reste mono-processus.

## Comptabilité

- Tous les montants sont des entiers en centimes, y compris à la frontière HTTP. Les flottants, booléens et chaînes ne sont pas convertis implicitement en centimes.
- Un journal `ledger` contient les écritures initiales, bancaires, de correction et de réaffectation. Les soldes sont des sommes de ce journal.
- Une table `allocations` conserve l'affectation courante unique d'une transaction. Corriger cette affectation produit deux écritures opposées et une entrée d'audit avec l'acteur `ADMIN`.
- Une correction prend effet le jour de l'action. La courbe et l'historique conservent donc la chronologie des décisions. Les opérations bancaires importées tardivement gardent leur date de comptabilisation.
- Les transactions, le journal et l'audit sont protégés contre UPDATE et DELETE par des triggers SQLite. Les affectations courantes peuvent évoluer, accompagnées de leur journal.
- Une transaction réelle est acceptée même si l'enveloppe devient négative. Une réaffectation manuelle au-delà du disponible est refusée. La correction d'une affectation reste autorisée, y compris si elle révèle un solde négatif.
- Le total inclut l'enveloppe système `NON AFFECTÉ`. Aucun ajustement automatique ne masque une divergence bancaire.

SQLite active les clés étrangères, WAL et un délai d'attente sur les verrous. `BEGIN IMMEDIATE` sérialise les opérations qui lisent puis modifient les soldes pour éviter deux réaffectations concurrentes du même disponible. Le déploiement prévu utilise une seule instance sur un stockage local persistant.

## Date de démarrage

Le solde initial représente la **clôture de la date sélectionnée**. Les opérations dont la date de comptabilisation est antérieure ou égale ne sont pas comptabilisées une seconde fois. Un import CSV indique leur nombre dans `before_start`. Il faut donc fournir un solde de clôture historique cohérent avec cette date, puis importer toutes les opérations suivantes. Un solde actuel en cours de journée ne prouve pas le solde de clôture : l’assistant exige de confirmer la date et le solde de fin de journée, sans préremplissage trompeur depuis la découverte bancaire.

La répartition initiale doit être positive ou nulle, sans dépasser le solde bancaire. Le reliquat est placé dans `NON AFFECTÉ`. Le compte est unique en V1. Un changement de code ne modifie jamais une affectation déjà enregistrée. Les codes des archives restent réservés et ne participent plus au matching.

## Matching et déduplication

La normalisation retire les accents, passe en majuscules et réduit les espaces. Le code doit être un token complet ; `RES-NOEL2` ne correspond pas à `RES-NOEL`. Un libellé contenant plusieurs codes distincts arrive dans `NON AFFECTÉ`.

L'identifiant fournisseur est indexé par compte et source dans `external_identities`. Une opération reçue via plusieurs sources peut ainsi conserver plusieurs identifiants sans modifier sa transaction d'origine. Un identifiant déjà connu dont le contenu change bloque le lot pour vérification.

L'empreinte inclut le compte, les dates, le montant signé, la devise et le libellé original. Un rapprochement exact et unique entre sources conserve l'affectation existante. Plusieurs candidats identiques rendent le rapprochement ambigu et bloquent le lot. Deux identifiants distincts d'une même source sont conservés comme deux transactions et signalés comme doublon potentiel.

Sans identifiant, deux lignes identiques dans un même fichier sont refusées. Une empreinte unique déjà connue est considérée comme une réimportation. Il est impossible de distinguer parfaitement deux opérations légitimes strictement identiques sans identifiant stable : celui-ci est donc fortement recommandé. Les empreintes différentes entre exports CSV et Woob ne sont pas rapprochées approximativement ; l'éventuel doublon et l'écart devront être examinés. La stratégie sera ajustée après observation des données réelles Crédit Agricole.

## État et suite

Le socle couvre le moteur métier, son API, l'interface française responsive, les graphiques annuels dans le détail des enveloppes, le CSV de secours, les exports, une sauvegarde manuelle et Docker Compose. L'interface propose l'initialisation, les enveloppes actives/archivées, leur modification et leur ordre d'affichage, la réaffectation, la qualification, les anomalies, les codes à copier et les mouvements filtrés/paginés. `/api/movements` expose le journal global filtrable ; le résumé annuel d'une enveloppe est calculé indépendamment de la pagination.

`backup.py` réalise des copies SQLite cohérentes via l'API de sauvegarde, vérifie leur intégrité et leurs références puis publie le fichier final. La restauration CLI vérifie aussi les tables et le schéma de l'application, et refuse tout dossier de destination existant. `backups.py` gère la planification en fuseau IANA, la conservation de 7 copies quotidiennes / 4 hebdomadaires et le statut dans un JSON séparé. Les copies manuelles et avant migration échappent à la rotation. Aucun changement du schéma métier n'est nécessaire. Les routes `/api/backups` sont protégées par les mêmes contrôles de session/Bearer et CSRF que les autres actions ; les téléchargements ne permettent pas de chemin libre. Voir [le guide](BACKUPS.md).

Étapes restantes pour le MVP :

1. Vérifier le connecteur et la déduplication avec les données réelles du compte de réserve et la caisse régionale utilisée. Les demandes de validation non prises en charge par le module sont signalées ; le CSV reste disponible.
2. Effectuer la validation de bout en bout sur Unraid, incluant une restauration d'essai et la copie d'une sauvegarde sur un autre support. La réimportation de l'export JSON reste une évolution distincte ; la restauration disponible utilise SQLite.

Les tests actuels comprennent le moteur et l'API, les sessions/CSRF, la conversion monétaire du frontend, l'adaptation d'objets Woob fictifs, les erreurs, la planification, une migration de base antérieure, les sauvegardes/restaurations et un test Docker de persistance. Les sauvegardes sont testées sur plusieurs semaines, au changement d'année et aux changements d'heure. Les parcours navigateur utilisent des données fictives, vérifient aussi l'absence de débordement sur mobile, le téléchargement d'une sauvegarde SQLite et simulent les réponses bancaires pour le parcours de connexion. Le chargement du module réel est vérifié sans appel bancaire dans Docker. Le test Compose attend une véritable échéance du planificateur et restaure une copie dans un dossier isolé.

Le schéma utilise désormais `PRAGMA user_version`. La version 1 correspond au socle initial, y compris les bases antérieures sans numéro ; la version 2 ajoute `bank_connection`. Une base existante est sauvegardée dans `backups/before-migration/` avant la migration. Les versions futures inconnues sont refusées. Les prochaines modifications doivent ajouter une migration explicite, sans modifier rétrospectivement les étapes existantes. L'export JSON porte `schema_version: 2` et contient les données métier, l'audit et la configuration bancaire sans secrets. Sa réimportation n'est pas encore implémentée ; pour restaurer ce lot, utiliser une sauvegarde SQLite.

## Références techniques

- [SQLAlchemy — transactions SQLite et clés étrangères](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html)
- [FastAPI — tests avec lifespan](https://fastapi.tiangolo.com/advanced/testing-events/)
- [FastAPI — déploiement en conteneur](https://fastapi.tiangolo.com/deployment/docker/)
- [FastAPI — cookies de réponse](https://fastapi.tiangolo.com/advanced/response-cookies/)
- [Vite — compilation de production](https://vite.dev/guide/build)
- [Recharts — taille et conteneur responsive](https://recharts.github.io/en-US/guide/sizes/)

## Assistant et interface de travail

L’assistant suit l’ordre connexion → choix du compte → solde de clôture et enveloppes → récapitulatif. Les brouillons restent en mémoire du navigateur jusqu’à la confirmation, sans stockage de secrets. Un rechargement abandonne les brouillons nouveaux, sans écrire de données comptables. Les enveloppes créées par l’ancienne version avant initialisation sont reprises avec leur identifiant ; leur modification et leur répartition restent dans la transaction de setup.

`POST /api/setup` conserve le contrat historique `allocations`. Le nouveau contrat `envelopes` accepte des brouillons (champs d’EnvelopeCreate, `amount_cents`, `existing_id` facultatif), exclusifs d’une répartition `allocations` non vide. `bank_choice_id` désigne un choix opaque issu de la découverte, avec `bank_confirmed=true` ; `auto_sync_enabled` exige ce choix. `Banking.initialize` garde le verrou de découverte/synchronisation jusqu’au commit SQL : vérification du jeton de dix minutes, création/édition des enveloppes, initialisation, association bancaire et audit sont atomiques. Le jeton n’est consommé qu’après réussite. Une double initialisation est refusée et les anciens appels restent compatibles. Aucun appel réseau n’a lieu dans cette transaction. Aucun changement de schéma ou de volume Docker n’est requis.

L’accueil est le tableau **Enveloppes**, avec solde bancaire, total des projets, non affecté, écart et accès aux tâches. Les détails conservent modification, archivage, mouvements et graphique annuel. **Opérations** regroupe le journal filtré et les contrôles **À traiter**. **Banque** expose connexion et planification ; **Réglages** conserve sauvegardes, exports et codes. L’en-tête affiche l’état et la date du dernier import bancaire, sans point vert décoratif. Une erreur reste distincte du contrôle comptable des montants.
