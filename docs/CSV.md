# Import CSV de secours

L'import accepte pour l'instant un format explicite LootSplit. Il ne prétend pas lire tous les formats d'export Crédit Agricole. L'adaptation au relevé réel sera faite lors de l'intégration bancaire.

Fichier UTF-8, avec ou sans BOM, séparateur `;`. Les champs contenant un point-virgule ou un retour à la ligne doivent être entre guillemets CSV.

| Colonne | Obligatoire | Format |
| --- | --- | --- |
| `booking_date` | Oui | `YYYY-MM-DD` |
| `amount` | Oui | Euros signés, `115,01` ou `-800.00`, au plus deux décimales |
| `raw_label` | Oui | Libellé bancaire original |
| `value_date` | Non | `YYYY-MM-DD` |
| `provider_transaction_id` | Non, recommandé | Identifiant stable et unique de l'opération |
| `currency` | Non | `EUR` uniquement, valeur par défaut |

L'exemple [examples/import.csv](../examples/import.csv) montre entrées, sorties et intérêts ; ses dates doivent être passées au moment de l'essai. Les opérations futures sont refusées.

`POST /api/import/csv` prend un objet JSON :

```json
{
  "bank_balance_cents": 111500,
  "content": "booking_date;amount;raw_label;provider_transaction_id\n2026-10-01;115,00;VIR RES-VAC;operation-1\n"
}
```

`bank_balance_cents` est le solde réel du relevé, après les opérations importées, exprimé en **centimes entiers**. Il n'est pas déduit du fichier, afin de détecter un historique incomplet. Un écart ne bloque pas l'import : il est exposé dans la réconciliation.

La réponse indique `imported`, `duplicates`, `before_start` et `reconciliation`. Les lignes déjà incluses dans le solde initial ne sont pas importées et sont comptées dans `before_start`. Une erreur de format ou une ambiguïté annule tout le lot ; aucune ligne n'est importée partiellement.

Limites : 2 Mo de texte UTF-8 et 10 000 opérations par fichier. Les identifiants ne doivent pas être des numéros de ligne susceptibles de changer d'un export à l'autre. Sans identifiant stable, consulter les limites de [déduplication](ARCHITECTURE.md).

L'export des mouvements a un autre rôle : il inclut les écritures internes et des montants en centimes. Ce n'est pas un fichier de transactions bancaires à réimporter. L'export JSON est exhaustif pour ce lot ; la sauvegarde SQLite reste le mécanisme de restauration disponible.
