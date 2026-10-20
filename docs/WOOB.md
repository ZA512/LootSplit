# Connexion au Crédit Agricole avec Woob

Le connecteur est implémenté en lecture seule : découverte des Livrets A en EUR, récupération du solde et des opérations comptabilisées, puis import dans le moteur commun. Le fonctionnement réel doit encore être validé avec votre caisse régionale et votre Livret A. Les tests du projet utilisent des données fictives ; aucune connexion à votre banque n'a été effectuée pendant le développement.

## Préparer la configuration sur Unraid

Le Dockerfile installe Woob et le module officiel `cragr`. Dans le fichier `.env` du projet sur le serveur, renseigner :

```dotenv
LOOTSPLIT_BANK_WEBSITE=www.ca-paris.fr
LOOTSPLIT_BANK_LOGIN=VOTRE_IDENTIFIANT
LOOTSPLIT_BANK_PASSWORD=VOTRE_CODE_PERSONNEL
```

La caisse ci-dessus est un exemple. Utiliser le domaine correspondant à votre caisse régionale, parmi les valeurs acceptées par le [module officiel cragr](https://gitlab.com/woob/woob/-/blob/3bc0f159c65fc2685c8b8787d0e25ff55f896f73/modules/cragr/module.py). Ce module attend un identifiant à 11 chiffres et un code personnel à 6 chiffres. Garder les zéros initiaux : ces valeurs sont des chaînes de caractères.

Conserver `.env` sur votre serveur, avec des droits restreints. Les identifiants ne sont jamais saisis dans la page web et ne doivent pas être partagés dans le chat. Ils ne sont ni enregistrés dans SQLite ni inclus dans les exports ou les sauvegardes de l'application.

Recréer le conteneur pour injecter les variables :

```sh
docker compose up -d --build --force-recreate
```

Laisser ces variables vides conserve le fonctionnement par CSV. Le connecteur n'effectue aucun accès bancaire au démarrage tant qu'aucun Livret A n'est associé et que la planification n'est pas activée.

## Associer le Livret A

1. Initialiser les réserves avec un solde de clôture connu et sa date. Si vous reprenez un historique, utiliser le solde de clôture avant cet historique ; pour un démarrage au jour courant, le suivi commence aux opérations des jours suivants. L'association bancaire ne réécrit pas cette répartition initiale.
2. Ouvrir **Paramètres → Connexion bancaire**.
3. Cliquer sur **Charger mes livrets**. Cette action se connecte à la banque. Seuls les comptes identifiés comme Livret A, de type épargne et en EUR, sont proposés.
4. Sélectionner le livret en vérifiant le solde et les derniers chiffres affichés. Confirmer qu'il s'agit du compte déjà suivi dans LootSplit.
5. Cliquer sur **Associer ce Livret A**, puis **Synchroniser maintenant**.
6. Comparer le solde bancaire et les enveloppes. Traiter les opérations non affectées dans **À vérifier**.

La liste de sélection expire après dix minutes. L'interface reçoit des identifiants de choix opaques, sans numéro de compte complet ni IBAN complet. Si Woob ne fournit pas l'IBAN, les quatre derniers caractères de l'identifiant du compte sont affichés.

Une fois le compte associé, le bouton **Synchroniser maintenant** apparaît aussi sur le tableau de bord. Le compte associé ne peut pas être remplacé silencieusement par un autre compte : une nouvelle base et une nouvelle initialisation sont nécessaires pour changer de Livret A dans cette version.

## Planification

La synchronisation automatique est désactivée lors de l'association. Dans la même section, l'activer et choisir une fréquence, par défaut six heures, puis enregistrer. L'API accepte des intervalles entiers de 1 à 168 heures. Le prochain passage est calculé à l'activation ; le planificateur vérifie les échéances toutes les trente secondes.

La configuration, l'échéance et la date de dernière réussite sont persistantes. Un redémarrage reprend les échéances dues. La prochaine échéance est réservée avant un appel réseau, afin qu'une interruption du processus ne provoque pas de tentatives rapprochées. Une seule opération bancaire s'exécute à la fois. La synchronisation manuelle attend au moins une minute entre deux tentatives. Le navigateur actualise les informations affichées environ toutes les minutes quand la page est visible.

Une erreur d'identifiants, une demande de validation bancaire ou la disparition du compte suspend les tentatives automatiques. Après avoir résolu le problème, lancer une synchronisation manuelle réussie pour reprendre la planification. Une panne temporaire reporte la prochaine tentative à l'intervalle configuré.

## Validation bancaire et erreurs

Lorsque Woob indique qu'une action est nécessaire, l'interface invite à ouvrir le site ou l'application bancaire et à effectuer la validation demandée. Aucun code SMS ni validation de paiement n'est demandé par LootSplit. Le module figé peut ne pas prendre en charge tous les parcours d'authentification de votre caisse ; dans ce cas, conserver le CSV et signaler le problème sans transmettre de secret.

Chaque opération Woob s'exécute dans un processus isolé, avec un délai maximal de trois minutes. Le solde et l'historique sont récupérés lors d'une seule session de lecture avant l'import transactionnel. Une panne, un dépassement de délai ou des données invalides n'importent pas une partie du lot. Les transactions et affectations existantes restent disponibles.

L'API bancaire peut présenter un solde et un historique temporairement décalés ou limiter l'historique disponible. L'application affiche alors l'écart de réconciliation ; elle ne crée aucun mouvement de compensation. Le rapprochement Woob/CSV est exact : des différences de dates ou de libellés entre sources doivent être examinées, sans rapprochement approximatif automatique.

Les messages techniques du fournisseur et ses journaux HTTP ne sont ni affichés ni enregistrés. Les erreurs exposées sont des messages prédéfinis, sans détail susceptible de contenir un identifiant, un cookie ou un secret. Les dates de dernière tentative et de dernière réussite sont distinctes. Un import CSV ne fait pas disparaître une erreur bancaire encore active.

## Fichiers secrets (option)

Le backend accepte aussi `LOOTSPLIT_BANK_LOGIN_FILE` et `LOOTSPLIT_BANK_PASSWORD_FILE`. Le contenu UTF-8 du fichier monté est prioritaire sur la variable correspondante. Pour utiliser Docker secrets, ajouter une surcharge Compose locale, sans la publier :

```yaml
services:
  lootsplit:
    environment:
      LOOTSPLIT_BANK_LOGIN_FILE: /run/secrets/bank_login
      LOOTSPLIT_BANK_PASSWORD_FILE: /run/secrets/bank_password
    secrets:
      - bank_login
      - bank_password
secrets:
  bank_login:
    file: ./secrets/bank_login.txt
  bank_password:
    file: ./secrets/bank_password.txt
```

Les fichiers doivent être lisibles par l'identité `PUID:PGID` du conteneur. Garder le domaine de la caisse dans `LOOTSPLIT_BANK_WEBSITE`. Le Compose principal continue à fonctionner sans cette surcharge.

## Installation locale et maintenance

Après `uv sync --frozen`, installer le module localement :

```sh
uv run python scripts/fetch_woob_modules.py
```

Le répertoire `bank_modules/` est ignoré par Git. L'installateur vérifie l'empreinte SHA-256 d'une archive officielle, puis ne copie que les fichiers du module et ses licences. En Docker, cette étape est effectuée pendant la construction. Aucun module n'est téléchargé ou mis à jour pendant une synchronisation.

Révision retenue : `3bc0f159c65fc2685c8b8787d0e25ff55f896f73`. L'origine et l'empreinte sont conservées dans `bank_modules/SOURCE.txt`. Les sources du module ainsi que `COPYING` et `COPYING.LESSER` sont incluses dans l'image. Toute mise à jour de cette révision doit être accompagnée d'une mise à jour de l'empreinte et de nouveaux tests.

Le chargement utilise [WoobBase](https://woob.dev/api/core/woob/), qui charge les modules locaux sans gérer les dépôts distants. Le contrat métier conserve ses trois méthodes de lecture, indépendantes de Woob : `get_accounts`, `get_balance` et `get_transactions`. L'adaptateur appelle uniquement `iter_accounts` et `iter_history` du [contrat bancaire Woob](https://woob.dev/api/capabilities/bank/base/).
