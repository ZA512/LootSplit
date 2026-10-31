# Changer de compte de réserve

Un seul compte de réserve est suivi à la fois. Si vous avez associé le mauvais compte ou souhaitez en utiliser un autre, ouvrez **Réglages → Changer de compte de réserve → Préparer le changement de compte**.

## 1. Conserver les montants avant de changer

**Recopiez les enveloppes, leurs codes et leurs montants, ou cliquez sur Télécharger le récapitulatif.** Ce fichier texte permet de retrouver les bonnes sommes pour répartir les fonds sur le nouveau compte et, si nécessaire, réaliser les virements avec les bons codes.

Le récapitulatif inclut aussi les enveloppes archivées, le montant NON AFFECTÉ et l'éventuel écart entre la banque et le total des enveloppes. Si le compte actuellement associé n'est pas le bon, vérifiez ces montants : ils ne constituent pas automatiquement la répartition à reprendre.

Vous pouvez annuler à ce stade sans modifier le suivi. Si un import, une synchronisation ou une modification intervient après l'ouverture du récapitulatif, la confirmation est refusée. Cliquez sur **Actualiser le récapitulatif** et recopiez les nouveaux montants.

## 2. Confirmer la remise à zéro

1. Cocher **J’ai recopié les enveloppes, leurs codes et leurs montants**.
2. Saisir exactement **CHANGER DE COMPTE**.
3. Cliquer sur **Sauvegarder et réinitialiser le suivi**.

Le serveur crée d'abord une sauvegarde SQLite complète, conservée parmi les sauvegardes manuelles, sans rotation automatique. Si la sauvegarde échoue ou qu'une connexion bancaire est en cours, le changement est refusé. En cas d'échec pendant la remise à zéro, la transaction est annulée.

Les enveloppes, leurs codes, descriptions, icônes et états actif/archivé sont conservés. Les soldes, opérations, identités de déduplication et affectations de l'ancien compte sont retirés du suivi courant, avec son ancien historique et son association bancaire. La planification bancaire revient à l'état désactivé. L'ancien suivi complet reste dans la sauvegarde et une trace du changement est enregistrée dans le nouveau journal d'audit.

## 3. Initialiser le bon compte

L'assistant de démarrage s'affiche à nouveau. Un lien permet de télécharger la sauvegarde de l'ancien compte ; elle reste aussi disponible dans **Réglages → Sauvegardes** après l'initialisation. Une restauration complète reste possible par la [procédure sur le serveur](BACKUPS.md#restauration-contrôlée-sur-unraid), dans un dossier neuf.

Choisir le bon compte dans l'assistant, ou continuer avec des relevés CSV, puis indiquer le **solde réel du nouveau compte à la clôture de la date de démarrage choisie**. Les opérations de cette date et des jours précédents sont déjà comprises dans ce solde et ne seront pas ajoutées par les imports.

- **Les fonds sont déjà sur le nouveau compte :** reprendre leur répartition dans les enveloppes lors de l'initialisation. Aucun aller-retour bancaire n'est nécessaire pour changer le compte suivi.
- **Les fonds seront versés après la date de démarrage :** initialiser uniquement le solde déjà présent. Effectuer ensuite les virements dans votre banque, avec les montants vérifiés et les codes des enveloppes recopiés, puis synchroniser ou importer le relevé. Une opération sans code peut être affectée manuellement dans **Opérations → À traiter**.

**Ne comptabilisez pas les mêmes sommes à la fois dans la répartition initiale et comme nouveaux virements.** LootSplit n'effectue aucun virement. Si une somme reste sans enveloppe au démarrage, elle est placée dans NON AFFECTÉ et peut être réaffectée ensuite.

Vérifier le récapitulatif de l'assistant et créer le suivi. Pour un démarrage en CSV, l'association peut aussi se faire ensuite dans **Banque**, en vérifiant les derniers chiffres affichés. La synchronisation automatique reste désactivée jusqu'à son activation explicite dans l'assistant ou dans Banque. Après la première synchronisation, contrôler le solde et la réconciliation avant de reprendre les imports habituels.
