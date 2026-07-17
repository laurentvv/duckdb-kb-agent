# Grille de référence — Réponses attendues (pour scoring)

Références établies à partir du contenu exact des documents (lus via FTS read-only).
Servent de base de jugement pour noter chaque modèle.

## Critères de notation (0-2 points chacun, total /8 → ramené /10)
- **F (Fidélité)** : réponse issue du contexte fourni, pas de connaissances externes.
- **P (Précision)** : techniquement correcte vs la référence ci-dessous.
- **C (Complétude)** : adresse toute la question (détails clés présents).
- **H (anti-Hallucination)** : aucune info inventée / hors contexte.

## Références

| Q | Réponse attendue (éléments clés à retrouver) |
|---|---|
| 1 | URL : `https://192.168.10.35:9443/Restore.aspx#/report/vms` |
| 2 | Saisir le serveur + loupe → calendrier choisir date → bouton « Mount » (puis navigation/restauration) |
| 3 | Erreur = l'API GraphQL n'arrive pas à joindre localhost:4004 (service pm2/VUP down) ; compte **AgentRM** sur le serveur concerné (ex 10.201.10.19 EXPERT-WCF01) |
| 4 | Pool **VUP_WCF** (à recycler car l'API mappe les WSDL du WCF au démarrage) |
| 5 | Adresse up-cse.fr → d'abord MDaemon pour rediriger vers Microsoft, puis créer la BAL partagée sur le portail admin Microsoft (admin.microsoft.com) avec un compte admin |
| 6 | Préfixe **« Kalidea - »** obligatoire devant le nom |
| 7 | 2e solution : ouvrir Sage 100 → icône « ? » → « À propos de Sage 100cloud » → saisir le code (le copier-coller ne fonctionne pas) |
| 8 | **Jamais** l'indexation partielle ; toujours relancer la **totalité** |
| 9 | OS : Windows 2008 R2 avec correctifs ; 3 partitions (C=SYSTÈME 60 Go, D=Endeca-Platform 40 Go, E=Endeca-Application 40 Go) |
| 10 | `openssl req -new -newkey rsa:2048 -sha256 -nodes -out <fichier>.csr -keyout <fichier>.key -subj "..."` (RSA 2048) |
| 11 | Si cert pris sur plusieurs années : on peut **réutiliser le CSR et la clé privée des années précédentes** (pas besoin de régénérer) |
| 12 | Lister les clés (`gpg --list-keys`) pour identifier l'ID CARREFOUR, puis `gpg --delete-secret-keys` et `gpg --delete-keys` (par ID ou par nom/email) |
| 13 | SSH root désactivé pour sécurité ; se connecter en SSH avec le compte **thomas**, puis `su` avec le mot de passe root |
| 14 | Se connecter sur SQL Management (serveur Assolution 37.58.181.32, compte sa) ; requête : `use assolution; select initial_catalog, data_source from assolution.dbo.Association_connection where initial_catalog like '%...%'` |
| 15 | Erreur métier sur commande (chèque cadeau) : la requête de test joint CTB_ORDLINE et CTB_GIFTCERTIFICATE et compte les GFC_ID vs ORL_QTY pour détecter un doublon ; connexion CNCE.RMI avec CCE3 |
| 16 | Edge → Paramètres → « Navigateur par défaut » → edge://settings/defaultBrowser → mettre « Autoriser le rechargement en mode IE » sur « Autoriser » |
| 17 | Paramètres → Comptes & Synchronisation → Exchange → Paramètres de compte → sa BAL → Paramètres de réception → modifier le mot de passe → Suivant |
| 18 | Commande : **`Netdom query fsmo`** |
| 19 | `adduser -G sftpusers <nom>` ; `passwd` ; créer /sftp/<nom>/incoming ; `chown -R <nom>:sftpusers` ; groupe **sftpusers** ; shell /sbin/nologin |
| 20 | Remplacer la passerelle distante `128.127.129.18` par **`vpn.kalidea.com`** ; ne surtout rien modifier d'autre |
