# PRD — Gestion des réserves familiales adossées à un compte de réserve

**Version :** 1.0  
**Statut :** MVP à développer  
**Nom de travail :** Réserves  
**Type :** application web auto-hébergée  
**Langue UI :** français  
**Devise :** EUR

---

# 1. Contexte

Le foyer utilise un compte de réserve unique pour stocker plusieurs réserves financières destinées à des usages différents :

- réserve de sécurité ;
- vacances ;
- Noël et anniversaires ;
- rentrée scolaire ;
- voyages scolaires ;
- dépenses enfants ;
- éventuellement d'autres réserves créées ultérieurement.

Le problème est qu'un compte de réserve ne présente qu'un solde global.

Exemple :

Compte de réserve : **9 365 €**

Mais ce montant peut réellement correspondre à :

- Sécurité : 6 000 €
- Vacances : 1 720 €
- Noël : 465 €
- Rentrée : 580 €
- Voyages scolaires : 350 €
- Enfants : 250 €

L'application doit permettre de retrouver cette décomposition tout en restant strictement raccordée aux mouvements bancaires réels.

Elle ne doit pas devenir une application de budget général.

---

# 2. Principe fondamental

La banque reste la source de vérité concernant l'existence de l'argent.

L'application apporte une couche de ventilation logique.

À tout moment :

**Solde réel du compte de réserve = somme des enveloppes + montant non affecté**

L'application ne doit jamais inventer un mouvement financier.

Un mouvement entrant ou sortant d'une enveloppe doit provenir :

1. d'une transaction bancaire réelle ;
2. d'une affectation manuelle d'une transaction bancaire ;
3. d'une réaffectation interne entre deux enveloppes.

Les réaffectations internes ne modifient évidemment pas le solde bancaire.

---

# 3. Objectifs

Le MVP doit permettre :

1. de connecter le compte de réserve et récupérer son solde et ses transactions ;
2. de créer librement des enveloppes ;
3. d'attribuer à chaque enveloppe un code utilisé dans les libellés bancaires ;
4. de détecter automatiquement les mouvements associés à une enveloppe ;
5. de qualifier manuellement les transactions non reconnues ;
6. de connaître à tout moment le montant réellement disponible dans chaque enveloppe ;
7. de contrôler que la somme des enveloppes correspond au solde bancaire ;
8. de consulter l'historique complet de chaque enveloppe ;
9. d'afficher un petit graphique annuel montrant l'évolution de son solde ;
10. de créer, renommer et arrêter des enveloppes sans perdre leur historique ;
11. de disposer d'un import CSV de secours en cas d'indisponibilité du connecteur bancaire ;
12. de conserver une trace des corrections et réaffectations manuelles.

---

# 4. Hors périmètre

Le MVP ne doit PAS devenir une application de gestion financière générale.

Ne pas développer :

- catégorisation Carrefour/Amazon/restaurant/etc. ;
- analyse des dépenses du compte courant ;
- création automatique de virements ;
- initiation de paiement bancaire ;
- optimisation financière ;
- prévisions IA ;
- connexion à plusieurs banques ;
- agrégation du patrimoine ;
- suivi de crédits ;
- catégorisation automatique par commerçant ;
- budget mensuel du foyer ;
- système complexe de notifications ;
- gestion d'objectifs d'épargne automatiques.

L'application répond essentiellement à cette question :

**« Sur les X euros présents réellement sur le compte de réserve, combien appartiennent à chaque réserve ? »**

---

# 5. Architecture bancaire prévue

Les virements vers le compte de réserve sont principalement des virements automatiques programmés depuis le compte CHARGES.

Ils sont volontairement réalisés séparément.

Exemple :

```text
Compte CHARGES
    |
    +--- 115 € ---> compte de réserve
    |               libellé : RES-NOEL
    |
    +--- 200 € ---> compte de réserve
    |               libellé : RES-VAC
    |
    +--- 100 € ---> compte de réserve
                    libellé : RES-RENTR
```

L'application ne programme pas ces virements.

Elle les constate après leur apparition à la banque.

Les retraits du compte de réserve vers le compte CHARGES ou le compte DÉPENSES sont réalisés manuellement dans l'application bancaire Crédit Agricole.

Exemple :

```text
Compte de réserve
   |
   +--- 800 € ---> Compte DÉPENSES
                  libellé : RES-VAC
```

L'application constate ensuite :

```text
VACANCES -800 €
```

---

# 6. Absence volontaire de budget mensuel attendu

Une enveloppe peut recevoir un virement automatique chaque mois, mais son montant peut évoluer librement.

L'application ne doit donc PAS contenir de notion obligatoire du type :

```text
Versement attendu : 115 €/mois
```

Elle ne doit pas générer d'alerte du type :

```text
Le versement de 115 € n'a pas été reçu.
```

En revanche, elle peut présenter une information descriptive :

```text
NOËL
Solde : 465 €

Ce mois-ci :
+115 €

Dernier versement :
05/10/2026
```

Ou :

```text
VACANCES
Solde : 1 720 €

Ce mois-ci :
Aucun versement
```

Cela reste une information, pas une anomalie.

---

# 7. Gestion des enveloppes

## 7.1 Création

L'utilisateur peut créer une enveloppe avec :

- nom ;
- code bancaire ;
- description facultative ;
- icône facultative ;
- ordre d'affichage facultatif.

Exemple :

```text
Nom : Noël & anniversaires
Code : RES-NOEL
```

Autres exemples :

```text
RES-VAC
RES-SECU
RES-RENTR
RES-VOY
RES-ENF
```

Le code doit être unique.

Convention recommandée :

```text
RES-[CODE]
```

Caractères autorisés :

```text
A-Z
0-9
-
_
```

Pas d'accent.

Longueur maximale recommandée : 20 caractères.

La comparaison doit être insensible à la casse.

---

# 8. Cycle de vie d'une enveloppe

Une enveloppe possède au minimum les états :

```text
ACTIVE
ARCHIVED
```

Une enveloppe active peut recevoir de nouvelles transactions.

Une enveloppe archivée conserve :

- son historique ;
- ses transactions ;
- son graphique ;
- ses réaffectations.

Une enveloppe archivée n'apparaît plus par défaut sur le dashboard.

Pour archiver une enveloppe, son solde doit être égal à zéro.

Si son solde n'est pas nul, proposer auparavant une réaffectation vers une autre enveloppe.

Exemple :

```text
Enfants : 120 €

Archiver cette enveloppe ?

Le solde doit d'abord être transféré.

[Transférer vers...]
```

---

# 9. Connexion bancaire

Créer une abstraction :

```text
BankConnector
```

Interface minimale :

```text
get_accounts()
get_balance(account_id)
get_transactions(account_id, since)
```

Implémentations prévues :

```text
WoobConnector
CsvConnector
```

Future possibilité :

```text
OpenBankingConnector
```

L'application métier ne doit jamais dépendre directement de Woob.

Woob est un adaptateur.

---

# 10. Woob

Pour le MVP, utiliser Woob pour récupérer :

- les comptes ;
- le compte de réserve ;
- son solde ;
- les transactions comptabilisées.

L'application doit utiliser Woob uniquement en lecture.

Même si Woob permet éventuellement des opérations bancaires, aucune fonctionnalité de virement ne doit être exposée par l'application.

Principe :

```text
Application -> banque : lecture uniquement
Utilisateur -> banque : virements
```

---

# 11. Import CSV de secours

Prévoir un import manuel CSV.

Objectifs :

- continuer à utiliser l'application si Woob est temporairement cassé ;
- permettre une restauration ;
- éventuellement reprendre un historique bancaire.

L'import doit passer par le même pipeline que Woob :

```text
Connector
   ↓
BankTransaction
   ↓
Matching
   ↓
Allocation
```

Le moteur métier ne doit pas savoir si une transaction vient de Woob ou d'un CSV.

---

# 12. Transaction bancaire

Une transaction bancaire importée doit être considérée comme immuable.

Stocker au minimum :

```text
id
provider_transaction_id
bank_account_id
booking_date
value_date
amount
currency
raw_label
normalized_label
source
imported_at
```

`amount` est signé du point de vue du compte de réserve.

Exemples :

```text
+115 € = argent entrant sur le compte de réserve
-800 € = argent quittant le compte de réserve
```

Une fois enregistrée, la transaction bancaire ne doit pas être modifiée par l'utilisateur.

L'utilisateur modifie son affectation, jamais la transaction elle-même.

---

# 13. Déduplication

Une synchronisation répétée ne doit jamais créer deux fois la même opération.

Utiliser en priorité :

```text
provider_transaction_id
```

Si celui-ci n'est pas disponible ou stable, construire une empreinte basée sur :

```text
account
booking_date
value_date
amount
raw_label
```

La stratégie exacte peut être adaptée au comportement réel de Woob/Crédit Agricole.

---

# 14. Normalisation des libellés

Pour le matching :

1. passer en majuscules ;
2. supprimer espaces multiples ;
3. normaliser les accents si nécessaire ;
4. conserver le libellé original séparément ;
5. rechercher le code d'enveloppe comme token complet.

Exemple bancaire réel possible :

```text
VIR SEPA M GIRARD RES-NOEL
```

L'application doit détecter :

```text
RES-NOEL
```

et affecter automatiquement l'opération à :

```text
Noël & anniversaires
```

---

# 15. Matching automatique

Pour chaque nouvelle transaction :

```text
normaliser le libellé
        |
        v
chercher un code RES-xxx connu
        |
   +----+----+
   |         |
 trouvé    absent
   |         |
   v         v
affecter   NON AFFECTÉ
```

Lorsqu'un code correspond à une enveloppe :

```text
+115 € RES-NOEL
```

donne :

```text
Noël += 115 €
```

et :

```text
-150 € RES-NOEL
```

donne :

```text
Noël -= 150 €
```

---

# 16. Montant non affecté

Créer une enveloppe système spéciale :

```text
NON AFFECTÉ
```

Elle ne peut être :

- supprimée ;
- archivée ;
- renommée en V1.

Toute transaction bancaire qui ne correspond à aucun code connu est automatiquement placée dans cette enveloppe.

Exemple :

```text
INTÉRÊTS COMPTE DE RESERVE
+147,36 €
```

devient :

```text
NON AFFECTÉ +147,36 €
```

L'utilisateur peut ensuite l'affecter manuellement.

Cela garantit que le système reste comptablement cohérent même lorsqu'une transaction est inconnue.

---

# 17. Qualification manuelle

Créer un écran :

```text
Transactions à qualifier
```

Il présente les opérations actuellement dans NON AFFECTÉ.

Exemple :

```text
03/01/2027
+147,36 €
INTERETS COMPTE DE RESERVE

Affecter à :
[ Sécurité ▼ ]

[Valider]
```

Après validation :

```text
NON AFFECTÉ -147,36 €
SÉCURITÉ     +147,36 €
```

Le mouvement bancaire original reste inchangé.

---

# 18. Correction d'une mauvaise affectation automatique

Exemple :

```text
RES-VAC
+150 €
```

mais l'utilisateur voulait réellement alimenter Noël.

Il doit pouvoir modifier l'affectation :

```text
VACANCES -> NOËL
150 €
```

Ne pas modifier la transaction bancaire.

Créer une trace d'audit indiquant :

```text
Transaction XXX

Affectation initiale :
VACANCES

Nouvelle affectation :
NOËL

Date :
...

Source :
correction manuelle
```

---

# 19. Réaffectation interne

L'utilisateur doit pouvoir déplacer virtuellement de l'argent entre deux enveloppes.

Exemple :

```text
VACANCES -200 €
ENFANTS  +200 €
```

Aucun mouvement bancaire n'est effectué.

Le solde global du compte de réserve reste inchangé.

UI :

```text
Réaffecter

Depuis : Vacances
Vers : Enfants
Montant : 200 €
Motif : facultatif
```

Chaque réaffectation doit produire une entrée d'historique.

---

# 20. Solde d'une enveloppe

Le solde d'une enveloppe est calculé, jamais saisi arbitrairement.

Formule :

```text
solde initial
+
transactions bancaires affectées
+
réaffectations entrantes
-
réaffectations sortantes
=
solde actuel
```

Les montants doivent être stockés en centimes entiers.

Ne jamais utiliser `float` pour les valeurs monétaires.

---

# 21. Initialisation de l'application

Lors du premier démarrage :

1. connecter Woob ou importer le compte ;
2. sélectionner le compte de réserve ;
3. récupérer son solde réel ;
4. choisir une date de démarrage ;
5. créer les enveloppes initiales ;
6. répartir le solde existant.

Exemple :

```text
Solde réel compte de réserve :
9 365 €
```

L'utilisateur saisit :

```text
Sécurité       6 000 €
Vacances       1 720 €
Noël             465 €
Rentrée           580 €
Voyages           350 €
Enfants           250 €
```

Total :

```text
9 365 €
```

L'initialisation ne peut être validée que lorsque :

```text
Somme enveloppes = solde compte de réserve
```

Sinon le reliquat est proposé dans :

```text
NON AFFECTÉ
```

---

# 22. Réconciliation

Le dashboard doit toujours comparer :

```text
solde bancaire réel
```

avec :

```text
somme des enveloppes
```

Afficher clairement :

```text
Compte de réserve
9 365,00 €

Enveloppes
9 365,00 €

✓ Réconcilié
```

En cas d'écart :

```text
Compte de réserve
9 465,00 €

Enveloppes
9 365,00 €

⚠ Écart : 100,00 €
```

L'écart doit être visible immédiatement.

Ne jamais masquer une divergence.

---

# 23. Causes possibles d'une divergence

Prévoir au minimum les cas :

- transaction manquante ;
- import partiel ;
- transaction supprimée/modifiée par le fournisseur ;
- synchronisation interrompue ;
- erreur d'initialisation ;
- doublon ;
- changement de solde non encore accompagné des opérations correspondantes.

Afficher la date de dernière synchronisation pour aider au diagnostic.

---

# 24. Dashboard

Le dashboard doit rester extrêmement simple.

En haut :

```text
COMPTE DE RESERVE

Solde bancaire :       9 365 €
Total enveloppes :     9 365 €
Non affecté :              0 €

✓ Réconcilié

Dernière synchronisation :
20/10/2026 11:42
```

Puis les enveloppes.

Exemple :

```text
Sécurité
6 000 €

Ce mois :
+0 €

────────────────

Vacances
1 720 €

Ce mois :
+250 €

────────────────

Noël & anniversaires
465 €

Ce mois :
+115 €
```

Une enveloppe ayant reçu aucun mouvement peut simplement afficher :

```text
Aucun mouvement ce mois-ci
```

Ce n'est pas une alerte.

---

# 25. Carte enveloppe

Chaque carte affiche au minimum :

```text
Nom
Solde actuel
Mouvements du mois
Dernier mouvement
mini graphique annuel
```

Exemple :

```text
VACANCES

1 720 €

Octobre
+250 €

Dernier mouvement :
05/10/2026

[mini graphique]
```

---

# 26. Page détail d'une enveloppe

Cliquer sur une enveloppe ouvre :

```text
VACANCES

Solde actuel :
1 720 €

Entrées année :
+2 750 €

Sorties année :
-1 030 €
```

Puis :

- graphique annuel ;
- historique des mouvements ;
- réaffectations ;
- bouton de réaffectation ;
- paramètres de l'enveloppe.

---

# 27. Graphique annuel

Afficher un graphique simple représentant l'évolution du solde de l'enveloppe sur l'année sélectionnée.

Type :

```text
courbe
```

Abscisse :

```text
janvier -> décembre
```

Ordonnée :

```text
solde en euros
```

Pour chaque mois, afficher idéalement le solde de fin de mois.

Pour l'année courante, la courbe s'arrête au jour actuel.

Permettre de changer d'année.

Ne pas ajouter de graphiques complexes en V1.

Un mini graphique peut également apparaître sur la carte de l'enveloppe.

---

# 28. Historique d'une enveloppe

Afficher chronologiquement :

```text
05/10/2026
+115 €
Virement bancaire
RES-NOEL

17/10/2026
-150 €
Virement bancaire
RES-NOEL

20/10/2026
+100 €
Réaffectation depuis VACANCES
```

Différencier visuellement :

```text
transaction bancaire
réaffectation interne
correction manuelle
```

---

# 29. Historique global

Prévoir également un écran :

```text
Mouvements
```

avec filtres :

- enveloppe ;
- période ;
- type ;
- montant ;
- texte du libellé.

---

# 30. Synchronisation

Prévoir :

```text
[ Synchroniser maintenant ]
```

Afficher :

```text
Dernière synchronisation réussie :
20/10/2026 11:42
```

En cas d'erreur :

```text
⚠ Synchronisation bancaire impossible

Dernière synchronisation réussie :
19/10/2026 18:20
```

L'application doit continuer de fonctionner avec les données existantes.

Une erreur Woob ne doit jamais détruire ni modifier les affectations existantes.

---

# 31. Synchronisation automatique

Prévoir une synchronisation planifiée configurable.

Exemple par défaut :

```text
toutes les 6 heures
```

Elle peut être désactivée.

Ne pas synchroniser excessivement pour éviter les limitations ou blocages bancaires.

Une synchronisation manuelle reste toujours disponible.

---

# 32. Gestion des enveloppes

Écran :

```text
Paramètres > Enveloppes
```

Actions :

```text
Créer
Modifier
Réordonner
Archiver
Consulter les archives
```

Modifier permet :

```text
nom
description
code
icône
ordre
```

Un changement de code concerne les futurs mouvements.

Les transactions déjà affectées restent attachées à l'enveloppe.

---

# 33. Codes bancaires

Écran permettant de voir immédiatement :

```text
Sécurité            RES-SECU
Vacances            RES-VAC
Noël                 RES-NOEL
Rentrée              RES-RENTR
Voyages scolaires   RES-VOY
Enfants              RES-ENF
```

Ajouter un bouton :

```text
[ Copier le code ]
```

Cela permet de configurer facilement les virements automatiques dans l'application bancaire.

---

# 34. Intérêts du compte de réserve

Les intérêts annuels apparaîtront comme une vraie transaction bancaire.

Exemple :

```text
02/01/2027
+147,36 €
INTERETS
```

Sans code connu, elle arrive automatiquement dans :

```text
NON AFFECTÉ
```

L'utilisateur décidera ensuite de son affectation.

Ne prévoir aucune règle spéciale obligatoire pour les intérêts.

---

# 35. Transactions sortantes

Un retrait d'une réserve est effectué depuis l'application bancaire.

Exemple :

```text
Compte de réserve -> Compte DÉPENSES
800 €
RES-VAC
```

Après synchronisation :

```text
VACANCES
-800 €
```

Si aucun code n'est trouvé :

```text
NON AFFECTÉ
-800 €
```

L'utilisateur peut ensuite indiquer :

```text
Cette transaction appartient à VACANCES
```

---

# 36. Solde négatif d'une enveloppe

Une enveloppe peut techniquement devenir négative à cause :

- d'une erreur de code ;
- d'une affectation erronée ;
- d'un retrait supérieur à son solde.

Ne pas bloquer l'import de la transaction.

Afficher une alerte :

```text
⚠ VACANCES

Solde : -120 €

Cette enveloppe est négative.
```

La banque reste la source de vérité : l'application ne doit jamais rejeter une transaction réelle simplement parce qu'elle produit un résultat incohérent.

---

# 37. Écran des anomalies

Créer un écran :

```text
À vérifier
```

Il rassemble :

- transactions dans NON AFFECTÉ ;
- enveloppes négatives ;
- écart de réconciliation ;
- échec de synchronisation ;
- éventuels doublons suspects.

Afficher le nombre d'éléments dans le menu.

Exemple :

```text
À vérifier (2)
```

---

# 38. Audit

Toute action manuelle modifiant une affectation doit être historisée.

Stocker :

```text
date
type d'action
transaction concernée
ancienne valeur
nouvelle valeur
utilisateur
```

L'objectif n'est pas une conformité bancaire mais simplement de pouvoir comprendre plusieurs mois plus tard pourquoi un montant a changé.

---

# 39. Export

Prévoir :

```text
Export JSON
Export CSV
```

JSON doit permettre une sauvegarde complète :

- enveloppes ;
- allocations ;
- réaffectations ;
- transactions ;
- paramètres.

CSV doit permettre principalement l'analyse des mouvements.

---

# 40. Sauvegarde

La base doit pouvoir être sauvegardée facilement.

Prévoir une architecture adaptée à un déploiement Docker.

Les données persistantes doivent être placées dans un volume dédié.

Exemple :

```text
/data/app.db
/data/backups/
```

Prévoir une sauvegarde automatique quotidienne de SQLite avec rotation simple.

Exemple :

```text
7 sauvegardes quotidiennes
4 hebdomadaires
```

---

# 41. Sécurité

Les informations bancaires sont sensibles.

Exigences :

- aucune donnée bancaire envoyée vers un service tiers autre que ce qui est indispensable au connecteur ;
- aucune télémétrie externe ;
- aucun analytics cloud ;
- aucune clé bancaire dans le frontend ;
- aucun mot de passe bancaire stocké en clair dans SQLite ;
- secrets injectés via variables d'environnement ou stockage sécurisé ;
- cookies sécurisés si authentification web ;
- protection CSRF si nécessaire ;
- journalisation sans secrets ;
- masquage des IBAN dans l'interface ;
- aucune capacité de virement bancaire depuis l'application.

---

# 42. Authentification

Pour V1, une authentification locale simple suffit.

Prévoir au minimum :

```text
ADMIN
```

L'architecture ne doit toutefois pas empêcher ultérieurement l'ajout d'un rôle :

```text
VIEWER
```

qui permettrait à un second membre du foyer de consulter les réserves sans modifier les affectations.

Ne pas complexifier le MVP avec une gestion complète des identités.

---

# 43. Architecture technique proposée

Backend :

```text
Python
FastAPI
SQLAlchemy
SQLite
```

Frontend :

```text
React
TypeScript
Vite
```

Graphiques :

```text
Recharts
```

Déploiement :

```text
Docker
Docker Compose
```

Architecture :

```text
               Crédit Agricole
                      |
                    Woob
                      |
                WoobConnector
                      |
                BankConnector
                      |
               Import / Sync
                      |
             BankTransaction
                      |
             Matching Engine
                      |
          +-----------+-----------+
          |                       |
     Allocations             NON AFFECTÉ
          |
    Envelope Ledger
          |
     +----+----+
     |         |
 Dashboard  History
```

---

# 44. Modèle de données minimal

## BankAccount

```text
id
provider
provider_account_id
name
type
masked_iban
activation_date
opening_balance_cents
current_balance_cents
last_sync_at
```

## BankTransaction

```text
id
bank_account_id
provider_transaction_id
booking_date
value_date
amount_cents
currency
raw_label
normalized_label
source
imported_at
fingerprint
```

## Envelope

```text
id
name
code
description
icon
status
sort_order
created_at
archived_at
```

## InitialAllocation

```text
id
envelope_id
amount_cents
created_at
```

## TransactionAllocation

```text
id
transaction_id
envelope_id
allocation_type
created_at
```

Valeurs possibles :

```text
AUTO
MANUAL
SYSTEM
```

## Reallocation

```text
id
from_envelope_id
to_envelope_id
amount_cents
reason
created_at
```

## AuditLog

```text
id
event_type
entity_type
entity_id
old_value
new_value
created_at
```

---

# 45. Règle V1 : une transaction = une enveloppe

Pour conserver le système simple :

**une transaction bancaire ne peut être affectée qu'à une seule enveloppe.**

Ne pas développer de ventilation d'une transaction entre plusieurs enveloppes en V1.

Si l'utilisateur souhaite retirer :

```text
300 € VACANCES
200 € NOEL
```

il doit effectuer deux virements bancaires distincts.

Cela correspond au fonctionnement souhaité.

---

# 46. API backend minimale

Exemples :

```text
GET    /api/dashboard

GET    /api/accounts
POST   /api/sync

GET    /api/transactions
GET    /api/transactions/unassigned
PATCH  /api/transactions/{id}/allocation

GET    /api/envelopes
POST   /api/envelopes
PATCH  /api/envelopes/{id}
POST   /api/envelopes/{id}/archive

GET    /api/envelopes/{id}/history
GET    /api/envelopes/{id}/chart

POST   /api/reallocations

GET    /api/reconciliation

POST   /api/import/csv

GET    /api/export/json
GET    /api/export/csv
```

Les routes peuvent évoluer pendant l'implémentation mais les responsabilités doivent rester séparées.

---

# 47. Pages UI

Navigation principale :

```text
Dashboard
Enveloppes
Mouvements
À vérifier
Paramètres
```

Pas davantage pour le MVP.

---

# 48. Design

L'interface doit privilégier :

- lisibilité ;
- grands montants ;
- peu d'informations simultanément ;
- absence de jargon bancaire ;
- fonctionnement correct desktop et mobile ;
- responsive design ;
- thème clair/sombre si simple à implémenter.

Éviter les dashboards surchargés.

L'information la plus importante est toujours :

```text
combien possède réellement chaque enveloppe ?
```

---

# 49. Critères d'acceptation principaux

## AC01 — Création d'enveloppe

Étant donné une nouvelle enveloppe :

```text
Noël
RES-NOEL
```

une transaction bancaire contenant `RES-NOEL` doit être automatiquement affectée à cette enveloppe.

---

## AC02 — Entrée bancaire

Transaction :

```text
+115 €
VIR RES-NOEL
```

Résultat :

```text
NOEL +115 €
```

---

## AC03 — Sortie bancaire

Transaction :

```text
-150 €
VIR RES-NOEL
```

Résultat :

```text
NOEL -150 €
```

---

## AC04 — Transaction inconnue

Transaction :

```text
+147,36 €
INTERETS COMPTE DE RESERVE
```

Résultat :

```text
NON AFFECTÉ +147,36 €
```

et apparition dans :

```text
À vérifier
```

---

## AC05 — Qualification

L'utilisateur affecte les 147,36 € à SÉCURITÉ.

Résultat :

```text
NON AFFECTÉ -147,36 €
SÉCURITÉ +147,36 €
```

sans modifier la transaction bancaire originale.

---

## AC06 — Réaffectation

Action :

```text
VACANCES -> NOEL
200 €
```

Résultat :

```text
VACANCES -200 €
NOEL +200 €
```

Le solde compte de réserve reste inchangé.

---

## AC07 — Réconciliation

Si :

```text
Compte de réserve = 9 365 €
```

et :

```text
Σ enveloppes = 9 365 €
```

afficher :

```text
✓ Réconcilié
```

---

## AC08 — Divergence

Si les montants divergent de 100 € :

```text
⚠ Écart : 100 €
```

doit être visible sur le dashboard.

---

## AC09 — Synchronisation répétée

Synchroniser dix fois la même période ne doit générer aucune transaction en double.

---

## AC10 — Historique

Chaque enveloppe doit permettre de reconstruire son solde uniquement à partir :

```text
solde initial
transactions
réaffectations
```

---

## AC11 — Graphique annuel

Pour une enveloppe sélectionnée, l'utilisateur peut visualiser l'évolution de son solde sur janvier-décembre pour l'année choisie.

---

## AC12 — Enveloppe sans mouvement

Si aucune transaction n'affecte une enveloppe pendant le mois :

```text
Aucun mouvement ce mois-ci
```

est affiché.

Cela ne doit générer aucune alerte.

---

## AC13 — Archivage

Une enveloppe à solde zéro peut être archivée sans perdre son historique.

Une enveloppe avec un solde différent de zéro ne peut pas être archivée directement.

---

## AC14 — Woob indisponible

Si Woob échoue :

- les données existantes restent disponibles ;
- aucune donnée n'est supprimée ;
- un message indique la date de dernière synchronisation réussie ;
- l'import CSV reste disponible.

---

# 50. Tests particulièrement importants

Tester explicitement :

- transaction entrante ;
- transaction sortante ;
- intérêts annuels ;
- code inconnu ;
- code mal orthographié ;
- modification du code d'une enveloppe ;
- transaction sur enveloppe archivée ;
- doublon Woob ;
- synchronisation interrompue ;
- import CSV doublonnant une opération déjà reçue via Woob ;
- montant négatif d'une enveloppe ;
- réaffectation supérieure au solde disponible ;
- changement d'année ;
- passage décembre → janvier ;
- centimes ;
- caractères spéciaux dans les libellés CA ;
- transactions arrivant dans un ordre différent de leur date réelle.

---

# 51. Priorités de développement

## Phase 1 — moteur métier

Développer avant l'interface complète :

```text
BankTransaction
Envelope
Allocation
Reallocation
matching des codes
calcul des soldes
réconciliation
tests unitaires
```

Le moteur doit fonctionner indépendamment de Woob et de React.

---

## Phase 2 — interface minimale

Développer :

```text
Dashboard
Enveloppes
Historique
Transactions à qualifier
Réaffectation
```

avec transactions de démonstration.

---

## Phase 3 — connecteur Woob

Brancher :

```text
BankConnector
    ↓
WoobConnector
```

Tester sur le compte de réserve réel.

Adapter le mécanisme de déduplication aux données réellement fournies par le module Crédit Agricole.

---

## Phase 4 — import CSV

Ajouter le connecteur de secours.

---

## Phase 5 — graphiques et finitions

Ajouter :

```text
graphique annuel
mini graphiques
exports
sauvegardes
responsive mobile
```

---

# 52. Principe de développement pour Codex

Ne pas chercher à ajouter des fonctions « intelligentes ».

Privilégier :

```text
simplicité
traçabilité
déterminisme
testabilité
```

La logique financière doit être pure et largement couverte par des tests unitaires.

Le connecteur bancaire doit être considéré comme une source externe potentiellement instable.

Le cœur de l'application doit continuer à fonctionner sans lui.

Ne jamais modifier silencieusement une affectation existante après une synchronisation.

Ne jamais supprimer silencieusement une transaction.

Ne jamais corriger automatiquement une divergence financière sans intervention explicite de l'utilisateur.

---

# 53. Invariants métier

Ces règles doivent être traitées comme des invariants du système.

### Invariant 1

Une transaction bancaire importée est immuable.

### Invariant 2

Une transaction bancaire possède exactement une affectation en V1.

### Invariant 3

Toute transaction inconnue appartient à NON AFFECTÉ.

### Invariant 4

Une réaffectation interne conserve le total global des enveloppes.

### Invariant 5

Le solde d'une enveloppe est calculé depuis son historique et jamais saisi directement après l'initialisation.

### Invariant 6

Le montant global des enveloppes doit pouvoir être comparé à tout moment au solde bancaire.

### Invariant 7

Une erreur du connecteur bancaire ne doit jamais entraîner la perte ou la modification d'une donnée métier existante.

### Invariant 8

L'application ne possède aucune fonction permettant d'initier un virement bancaire.

---

# 54. Définition du MVP terminé

Le MVP est considéré comme fonctionnel lorsque l'utilisateur peut :

1. démarrer l'application avec Docker ;
2. connecter ou importer son compte de réserve ;
3. déclarer la répartition initiale du solde ;
4. créer plusieurs enveloppes avec leurs codes ;
5. synchroniser les transactions ;
6. voir les virements correctement affectés automatiquement ;
7. qualifier un mouvement inconnu ;
8. effectuer une réaffectation interne ;
9. consulter le solde et l'historique d'une enveloppe ;
10. visualiser son évolution annuelle ;
11. constater immédiatement que le total des enveloppes correspond au solde réel du compte de réserve ;
12. continuer à utiliser l'application si Woob est temporairement indisponible.

Le produit doit rester volontairement petit.

Sa valeur ne vient pas du nombre de fonctionnalités mais de la confiance que l'utilisateur peut avoir dans cette affirmation :

**« Chaque euro affiché dans mes réserves correspond à un euro réellement présent sur mon compte de réserve, et je sais exactement à quoi il est destiné. »**
