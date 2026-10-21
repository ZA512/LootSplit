# Proposition UX — LootSplit comme outil de gestion

Date : 21 octobre 2026. Statut : direction approuvée et intégrée dans l'application ; les essais utilisateurs restent à réaliser.

## Base conservée

Analyse effectuée sur `830b43a`, avec un arbre de travail initialement propre. Les changements réalisés à la maison sont intégrés à cette proposition : images Docker préconstruites (`753f5a4`), compatibilité LEP (`9cfc187`) et vocabulaire « compte de réserve » (`830b43a`). Le produit suit toujours un seul compte par instance ; la compatibilité avec plusieurs types de comptes ne signifie pas un suivi multi-comptes simultané.

La maquette initiale utilise exclusivement des données fictives et ne contacte aucune banque. L'intégration demandée ensuite modifie le parcours de démarrage et l'interface, sans migration de schéma ni modification de Compose. Les images Docker préconstruites et les comptes déjà initialisés sont conservés. L'application n'a pas été déployée sur le serveur Unraid pendant ce développement.

## Diagnostic à partir du code

- `Bootstrap` ouvre `Onboarding` lorsque `/accounts` est vide. Celui-ci demande le solde, la date et les enveloppes ; aucune connexion bancaire n'est proposée dans ce parcours.
- `BankingPanel` est accessible dans les paramètres après l'initialisation. `Banking.select()` appelle `svc.account()` : déplacer simplement ce panneau dans le démarrage ne suffit donc pas.
- L'accueil et la page des enveloppes répartissent consultation des soldes et gestion des enveloppes entre deux entrées. Les grandes introductions et cartes réduisent la quantité d'informations comparables à l'écran.
- « Réconcilié », « Réaffecter », « Non affecté » et « À vérifier » demandent de comprendre le modèle avant de savoir agir. Plusieurs types d'anomalies sont regroupés sous un compteur peu explicite.
- Le point vert de l'en-tête est actuellement décoratif : il ne représente pas l'état bancaire. Il ne doit pas suggérer une connexion réussie.
- Des textes secondaires descendent à 9–11 px dans certains panneaux ; une apparence discrète ne doit pas compromettre la lecture.

Il s'agit d'un examen du parcours et du code, pas d'une étude utilisateurs réalisée sur cette application.

## Références et limites

Sources consultées le 21 octobre 2026 :

1. [Nielsen Norman Group — 10 usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/) : visibilité de l'état, langage familier, prévention des erreurs et reconnaissance des actions. Application : compte, fraîcheur des données, montant disponible et action pertinente restent visibles. Ce sont des heuristiques, pas une certification d'intuitivité.
2. [NN/g — Recognition vs. recall](https://www.nngroup.com/articles/recognition-and-recall/) : des indices visibles réduisent le rappel nécessaire. Application : boutons nommés, contexte conservé pendant une affectation et aide à côté du champ concerné.
3. [GOV.UK — Complete multiple tasks](https://design-system.service.gov.uk/patterns/complete-multiple-tasks/) : rendre compréhensibles les tâches, leur ordre et leur état. Ce pattern complet vise des démarches longues, parfois sur plusieurs sessions ; pour LootSplit, on en retient ces principes dans un assistant court, sans ajouter une page administrative de tâches.
4. [GOV.UK — Check answers](https://design-system.service.gov.uk/patterns/check-answers/) : récapituler et permettre de corriger avant validation. Application : revoir le compte, la date et la répartition avant de créer le suivi.
5. [Linear — Triage](https://linear.app/docs/triage) : une file dédiée présente les éléments entrants avec des actions dans leur contexte. Application proposée : filtre « À affecter » dans les opérations et correction sur la ligne, avec disparition du compteur après traitement.
6. [Actual Budget — Envelope budgeting](https://actualbudget.org/docs/getting-started/envelope-budgeting/) : rendre explicite le rôle de l'argent disponible et son affectation. Application proposée : distinguer solde du compte, enveloppes de projets et argent non affecté. On ne reprend pas sa logique de budget mensuel : LootSplit reste un outil de réserves.
7. [NN/g — The aesthetic-usability effect](https://www.nngroup.com/articles/aesthetic-usability-effect/) : leurs observations de tests montrent que des participants peuvent apprécier l'apparence tout en rencontrant des difficultés pour accomplir leurs tâches. Application : conserver une interface soignée, mais évaluer les réussites et hésitations réelles plutôt que demander seulement si elle est jolie.

Linear et Actual sont des exemples concrets, pas un classement des meilleurs produits. L'ergonomie proposée est une déduction à partir de ces références et de nos tâches ; elle doit être vérifiée avec des utilisateurs.

## Démarrage guidé

### 1. Vérifier la connexion bancaire

La première page montre le connecteur disponible et propose « Tester la connexion ». Le succès ne correspond pas seulement à la présence des variables d'environnement : il nécessite une découverte effective des comptes.

Si les identifiants sont absents, l'écran donne la marche à suivre correspondant au Docker Compose actuel, puis « Revérifier la configuration ». Conserver les secrets côté serveur conformément à l'architecture actuelle ; la maquette ne propose pas un formulaire qui laisserait croire que leur enregistrement web existe déjà. Une erreur bancaire ou une validation requise par la banque doit être explicite et permettre de réessayer.

« Continuer avec des relevés CSV » est une alternative explicite, utilisable immédiatement. Ce choix reste visible ensuite dans l'état du compte.

### 2. Choisir le compte

Présenter les comptes compatibles avec leur libellé réel, identifiant masqué et solde observé, sous forme de choix radio. Aucune sélection automatique, même s'il n'y a qu'un compte. Rappeler qu'un seul compte est suivi dans cette instance.

En mode CSV, demander le nom du compte. En mode bancaire, conserver une sélection provisoire ; ne pas créer encore le compte comptable ni la connexion définitive.

### 3. Définir le point de départ et les enveloppes

Afficher le compte choisi dans le contexte. Le solde découvert est un solde actuel : il ne prouve pas le solde en fin de journée d'une date antérieure. Demander la date de référence, son solde de clôture et une confirmation explicite ; ne pas préremplir ce dernier avec un solde actuel présenté comme acquis.

Créer ou renommer les enveloppes directement dans le tableau, avec des suggestions facultatives. Les codes peuvent être proposés puis modifiés ; expliquer leur utilisation pour reconnaître les virements au moment pertinent. La somme et le reste non affecté se recalculent. Une répartition supérieure au solde bloque l'étape. Le reste peut rester non affecté.

### 4. Vérifier puis créer le suivi

Récapituler compte, mode d'import, date, solde de référence, enveloppes et reste. Chaque groupe dispose d'un retour pour correction. La validation finale crée le suivi en une seule transaction ; elle ne dépend pas d'un appel bancaire pendant la transaction SQL.

La synchronisation automatique reste un choix explicite après création. Présenter ensuite le résultat de la première synchronisation avec le solde bancaire observé et tout écart éventuel. Un écart n'est jamais comblé silencieusement.

## Vue quotidienne proposée

| Zone | Rôle et comportement |
| --- | --- |
| Navigation | Enveloppes (accueil), Opérations, Banque, Réglages. Supprimer le doublon accueil/enveloppes. |
| Bandeau du compte | Nom réel, identifiant masqué, état de connexion, dernier import réussi et bouton Actualiser. Un échec récent reste visible même si une ancienne synchronisation a réussi. |
| Soldes | Solde du compte, somme dans les enveloppes de projets, non affecté. Le contrôle inclut le non affecté dans le total. En cas de données anciennes ou d'écart, indiquer la date et le problème au lieu d'afficher un état rassurant. |
| Travail à faire | Exemple : « 2 opérations à affecter · 500 € », avec accès au bon filtre. Un reliquat initial non affecté n'est pas automatiquement une opération en attente. Les autres anomalies gardent une description et une action propres. |
| Tableau des enveloppes | Noms cliquables, codes identifiés, soldes alignés, action Ouvrir. Le non affecté est une ligne système séparée, non archivable. Pas de graphiques répétés sur chaque ligne. |
| Actions | « Créer une enveloppe » et « Déplacer entre enveloppes ». Dans le formulaire, montrer source, destination, montant et résultat avant validation ; préciser qu'aucun virement bancaire n'est effectué. |
| Détail | Conserver le contexte, montrer les mouvements et proposer le graphique annuel à ce niveau. |
| Opérations | Recherche et filtres, dont À affecter ; action Affecter ou Corriger au niveau de l'opération. Distinguer opération bancaire et déplacement interne. |
| Banque | Connexion, compte suivi, erreurs et planification. L'import CSV reste disponible pour un compte connecté. |
| Réglages | Sauvegardes, exports et administration. Aucun réglage nécessaire au démarrage n'est uniquement caché ici. |

Direction graphique : conserver le vert profond et les tons doux, employer une police de travail sans sérif, des titres courts, des espacements réguliers et des tableaux lisibles. La couleur signale un état et reste accompagnée d'un texte. Les informations secondaires restent lisibles ; boutons et données essentielles ne dépendent ni du survol ni d'une icône seule. Le mobile empile les montants et conserve les actions auprès des éléments concernés.

## Mise en œuvre retenue

1. Ajouter un contrat de préparation du démarrage : découverte, choix temporaire expirant et résolution du compte choisi avant création. La découverte actuelle peut être appelée avant `/setup`, la sélection définitive actuelle ne le peut pas.
2. Étendre `/setup` pour accepter le choix opaque facultatif et créer atomiquement compte, répartition, association bancaire et audit. Prévoir confirmation explicite, jeton expiré, double validation, concurrence et rollback complet. Ne pas transmettre l'identifiant bancaire interne dans le navigateur.
3. Retirer la dépendance à des enveloppes déjà créées pour le nouveau parcours : envoyer les brouillons au setup atomique. Le parcours existant peut rester compatible pendant la transition.
4. Remplacer l'onboarding, puis fusionner accueil et enveloppes. Les comptes déjà initialisés arrivent directement dans leur espace et ne repassent pas par l'assistant ; les comptes sans banque associée reçoivent une invitation contextuelle.
5. Réorganiser opérations/banque/réglages tout en conservant historique, audit, corrections, anomalies, sauvegardes et exports. Conserver les images Docker, volumes et règles monétaires existants.
6. Vérifier par tests métier et parcours navigateur : banque disponible/absente/erreur/validation requise, LEP et autres comptes compatibles, choix expiré, CSV, date et centimes, suraffectation, aller-retour sans perte, clavier, mobile et absence de réinitialisation d'un compte existant.

La maquette explore les interactions principales (affectation, déplacement, création, recherche, démarrage et erreurs de configuration). Elle ne simule pas tous les cas de production : historique complet, graphique annuel, import de fichiers, sauvegardes et authentification restent des fonctions existantes à préserver lors de l'intégration.

## Vérifier l'intuitivité

Faire essayer la proposition à quelques personnes qui ne connaissent pas LootSplit, sans explication préalable. Les objectifs ci-dessous sont des critères proposés, pas des résultats obtenus ni des seuils scientifiques :

- En cinq secondes, retrouver le solde du compte et le montant non affecté.
- Choisir le bon compte avant de créer une enveloppe, sans chercher dans les paramètres.
- Affecter une opération de 200 € sans aide et constater le nouveau solde.
- Déplacer 100 € entre deux enveloppes et expliquer que le solde bancaire reste identique.
- Identifier une synchronisation en erreur sans confondre « montants cohérents » et « données à jour ».

Observer réussite, hésitations, mauvais clics et explication du résultat, puis ajuster. Une visite guidée ne doit pas être nécessaire pour les tâches courantes.

## Vérification de la maquette livrée

Parcours automatisés dans Chromium : affecter une opération et constater le nouveau solde, déplacer 100 € sans modifier le total, créer une enveloppe à zéro, choisir un LEP, bloquer une suraffectation, vérifier le récapitulatif, revenir modifier, démarrer par CSV, afficher une configuration absente et un échec d'actualisation. La touche Entrée valide les formulaires locaux. Aucun débordement horizontal constaté aux largeurs 320, 390, 736 et 1024 px ; captures examinées sur ordinateur et mobile, en thèmes clair et sombre. Aucun échec JavaScript dans ces parcours. Ces vérifications concernent la maquette ; elles ne remplacent ni les tests de l'intégration future ni les essais utilisateurs.

## Intégration réalisée

La version applicative utilise `Onboarding.tsx` pour l'assistant, `ReservesPage.tsx` pour l'accueil en tableau et `tool.css` pour les styles de travail. La navigation est Enveloppes, Opérations, Banque et Réglages ; les anomalies et opérations non affectées sont accessibles dans Opérations → À traiter. L'archivage et la modification sont dans le détail d'une enveloppe ; les archives restent consultables depuis le tableau. Le formulaire de déplacement montre les deux soldes résultants avant confirmation. L'import CSV est disponible dans l'en-tête et les sauvegardes restent dans Réglages.

Le serveur accepte le setup atomique avec le choix bancaire provisoire et les brouillons d'enveloppes. Les anciennes enveloppes créées avant setup sont reprises ; les comptes déjà initialisés ne sont pas réinitialisés. Un choix bancaire expiré conduit à renouveler la connexion sans perdre les montants saisis pendant la session de page. Après un nouveau choix de compte, la confirmation du solde de clôture est à nouveau demandée.

Validation de cette intégration : 118 tests Python, 11 tests frontend, 4 parcours Playwright (dont création/modification/archivage, premier démarrage CSV, démarrage bancaire simulé avec expiration, sauvegarde téléchargée et mobile à 320/390 px), compilation TypeScript/Vite, Ruff et formatage. L'image locale construite depuis le Dockerfile passe le contrôle Compose : interface, authentification, imports, sauvegarde automatique, restauration isolée et persistance après recréation. Aucun appel réel à la banque ni déploiement Unraid n'a été effectué ; la publication de l'image de production reste à réaliser.
