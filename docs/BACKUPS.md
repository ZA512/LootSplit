# Sauvegardes et restauration

## Fonctionnement automatique

Les sauvegardes automatiques sont activées par défaut. Le service vérifie les échéances toutes les trente secondes : il crée une première copie après le démarrage si aucune sauvegarde automatique n'est connue, puis une copie chaque jour à **03:00, heure de Paris**.

La politique conserve :

- les **7 dernières copies quotidiennes**, une par date locale ;
- les **4 dernières copies hebdomadaires**, la première copie réussie de chaque semaine ISO ;
- toutes les copies manuelles et celles réalisées avant migration, sans rotation automatique.

Un redémarrage relit l'état enregistré. Une interruption de plusieurs jours provoque une copie à la date du redémarrage ; aucun historique de sauvegardes n'est inventé pour les jours où le serveur était arrêté. Les changements d'heure sont pris en compte. Si un horaire personnalisé tombe dans une heure inexistante au printemps, il est reporté après le saut. En automne, une seule copie est créée pour la journée.

L'interface **Paramètres → Sauvegardes** affiche la dernière réussite, la prochaine échéance, une éventuelle erreur et les fichiers disponibles. Le bouton **Sauvegarder maintenant** crée une copie manuelle indépendante. Les copies sont téléchargeables après authentification administrateur.

## Configuration Docker

Valeurs proposées dans `.env` :

```dotenv
LOOTSPLIT_BACKUP_ENABLED=true
LOOTSPLIT_BACKUP_TIME=03:00
LOOTSPLIT_BACKUP_TIMEZONE=Europe/Paris
```

L'horaire doit être au format `HH:MM` sur 24 heures et le fuseau doit être un nom IANA valide. Recréer le service après modification :

```sh
docker compose up -d --force-recreate
```

`LOOTSPLIT_BACKUP_ENABLED=false` désactive la planification et conserve la possibilité de faire une copie manuelle. Les échecs de copie sont signalés sans bloquer l'application ; une nouvelle tentative automatique attend une heure. Une tentative manuelle reste possible immédiatement.

Par défaut, les fichiers sont placés à côté de la base, dans `backups/`. Dans Docker :

```text
/data/app.db
/data/backups/
  daily/                7 copies quotidiennes au maximum
  weekly/               4 copies hebdomadaires au maximum
  manual/               copies demandées dans l'interface
  before-migration/     copies conservées avant une migration
  lootsplit-…Z.db        copies créées par la commande CLI historique
  backup-state.json     dates de réussite et état du planificateur
```

Les données persistent dans `APPDATA_PATH`. Le backend accepte aussi `LOOTSPLIT_BACKUP_PATH` pour un dossier distinct, à monter et configurer explicitement dans une surcharge Compose. Ce dossier doit être accessible en écriture à l'identité du service. Le stockage prévu est local au serveur.

## Contenu et validation

Une copie SQLite contient les enveloppes, transactions, affectations, réaffectations, audit et paramètres bancaires enregistrés dans la base. Elle ne contient pas les identifiants fournis par environnement, `.env`, les sessions web, les autres sauvegardes ni les sources de l'application.

La copie utilise [l'API de sauvegarde SQLite](https://www.sqlite.org/backup.html), afin de tenir compte des données présentes dans WAL pendant que l'application fonctionne. Elle est écrite dans un fichier temporaire, vérifiée par `integrity_check` et `foreign_key_check`, puis publiée par remplacement du fichier final après fermeture des connexions. La copie finale utilise un journal SQLite classique et se suffit à elle-même, sans fichier WAL annexe. La rotation intervient après la création et la validation des nouvelles copies quotidiennes et hebdomadaires.

Seuls les noms générés dans `daily/` et `weekly/` participent à la rotation. Les autres fichiers, les liens symboliques, les copies manuelles et les copies avant migration ne sont pas supprimés. Les fichiers temporaires d'une copie interrompue ne sont pas proposés au téléchargement.

L'état du planificateur est publié séparément dans un petit fichier JSON. Un état illisible ou mal formé ne bloque pas une nouvelle sauvegarde. Les messages d'erreur affichés sont génériques et ne contiennent pas de chemins internes ni de données bancaires.

## Copie manuelle en ligne de commande

Le service peut continuer de fonctionner pendant cette commande :

```sh
docker compose exec -T lootsplit python -m lootsplit.backup
```

Le chemin du nouveau fichier est affiché. Pour choisir un dossier monté distinct :

```sh
docker compose exec -T lootsplit python -m lootsplit.backup --destination /data/backups/manual
```

Ces copies CLI ne sont pas soumises à la rotation automatique. Leur création ne modifie pas les dates du planificateur de l'application ; elles apparaissent dans la liste des fichiers reconnus au prochain rafraîchissement.

## Restauration contrôlée sur Unraid

La restauration remplit un **dossier neuf** et refuse de remplacer une base ou un dossier existant. La commande ne lance pas l'application et n'effectue aucune connexion bancaire. Elle vérifie l'intégrité, les références, les tables attendues et la version du schéma avant de publier `app.db`.

Exemple avec le volume `/mnt/user/appdata/lootsplit` monté en `/data`. Adapter le nom de fichier à une sauvegarde existante :

1. Arrêter le service :

   ```sh
   docker compose stop lootsplit
   ```

2. Restaurer dans un nouveau sous-dossier du volume :

   ```sh
   docker compose run --rm --no-deps --entrypoint python lootsplit -m lootsplit.backup --restore /data/backups/daily/lootsplit-daily-2026-10-20.db --destination /data/restore-2026-10-20
   ```

3. Modifier `.env` pour monter le dossier restauré :

   ```dotenv
   APPDATA_PATH=/mnt/user/appdata/lootsplit/restore-2026-10-20
   ```

4. Recréer le service :

   ```sh
   docker compose up -d --force-recreate
   ```

5. Vérifier les soldes, les mouvements récents et la réconciliation. La base et les sauvegardes précédentes restent dans l'ancien dossier. Les nouvelles sauvegardes seront créées dans le nouveau volume.

Pour examiner la restauration avant toute synchronisation bancaire, laisser les variables bancaires vides pendant cette vérification. Les sessions web précédentes sont invalidées au redémarrage.

En développement local, la même commande est disponible :

```sh
uv run python -m lootsplit.backup --restore sauvegarde.db --destination nouveau-dossier
```

Les anciennes sauvegardes du premier schéma sont acceptées ; les migrations habituelles s'appliquent lors du lancement de l'application sur la copie restaurée. Une version de schéma plus récente que celle de l'application est refusée.

Les sauvegardes contiennent des données bancaires. Le téléchargement permet de conserver une copie sur un autre support : les copies automatiques sur le même disque ne protègent pas contre la perte de ce disque.
