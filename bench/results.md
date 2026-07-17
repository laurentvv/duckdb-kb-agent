# Résultats du benchmark

20 questions × 2 modèle(s).

| Q | Thème | Modèle | Latence (s) | Réponse (extrait) |
|---|---|---|---|---|
| 1 | Sauvegarde | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 23.0 | L'adresse web pour accéder à l'outil de restauration Veeam Backup des dossiers et fichiers est : https://192.168.10.35:9443/Restore.aspx#/report/vms |
| 1 | Sauvegarde | lfm2.5:latest | 17.5 | L'adresse web pour accéder à l'outil de restauration Veeam Backup des dossiers et fichiers est : https://192.168.10.35:9443/Restore.aspx#/report/vms |
| 2 | Sauvegarde | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 30.9 | Après avoir sélectionné le serveur, vous devez :  1. **Choisir la date et monter :** Cliquez sur le calendrier pour choisir la date de restauration souhaitée, puis cliquez sur « Mo |
| 2 | Sauvegarde | lfm2.5:latest | 25.6 | Après avoir sélectionné le serveur et monté l’arborescence, procédez ainsi :  1. Dans la liste des dossiers affichée, sélectionnez le dossier (ou plusieurs) à restaurer.   2. Ouvre |
| 3 | Dépannage | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 28.2 | L'erreur « connect ECONNREFUSED 127.0.0.1:4004 » est signalée dans le contexte d'un problème avec l’api VUP, tel qu'une erreur de chargement.  Pour intervenir et résoudre ce problè |
| 3 | Dépannage | lfm2.5:latest | 24.7 | The error “connect ECONNREFUSED 127.0.0.1:4004” means the GraphQL API endpoint is not reachable because the WCF service on that host is not running or not bound to port 4004. To fi |
| 4 | Dépannage | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 26.2 | Le pool d'applications IIS à recycler est **VUP_WCF**.  La raison de cette action est que l’API va mapper les WSDL du WCF au démarrage. |
| 4 | Dépannage | lfm2.5:latest | 23.6 | Le pool d’application **« VUP_WCF »** sur le serveur concerné (10.201.10.19 ou 10.201.10.20) doit être recyclé, car l’erreur de connexion à l’API VUP est liée à un problème de char |
| 5 | Messagerie | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 28.5 | Pour une demande concernant une adresse mail en « up-cse.fr », la procédure est la suivante :  1. **Initialisation :** Aller sur MDaemon pour rediriger vers la boîte Microsoft. 2.  |
| 5 | Messagerie | lfm2.5:latest | 21.5 | Pour créer une boîte aux lettres partagée pour une adresse en « up‑cse.fr », se rendre sur **MDaemon** et, à partir de là, utiliser le lien : https://admin.microsoft.com/Adminporta |
| 6 | Messagerie | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 24.9 | Il faut obligatoirement mettre « Kalidea - » avant le nom de la boîte aux lettres partagée. |
| 6 | Messagerie | lfm2.5:latest | 23.9 | Le contexte fourni n’indique pas de préfixe obligatoire à ajouter devant le nom d’une boîte aux lettres partagée. |
| 7 | Sage | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 29.7 | Si la fenêtre de licence expirée ne s'affiche pas au démarrage, vous devez suivre la deuxième solution :  1. Ouvrez Sage 100. 2. Cliquez sur l’icône "?" puis sur "À propos de Sage  |
| 7 | Sage | lfm2.5:latest | 20.9 | Suivez la deuxième solution : ouvrez Sage 100, cliquez sur l’icône « ? », puis sur « À propos de Sage 100cloud », puis sélectionnez « Code annuel » et saisissez le code dans les ch |
| 8 | Dépannage | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 26.2 | Après un plantage de l'indexation total, il faut toujours relancer la **total**. Il ne faut surtout pas relancer la partial. |
| 8 | Dépannage | lfm2.5:latest | 18.4 | Oui, il faut d’abord relancer l’indexation totale (durable 3 h à 4 h) puis, une fois celle‑ci terminée, réactiver et lancer la tâche d’indexation partielle. |
| 9 | Infrastructure | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 25.6 | Les pré-requis système pour installer le moteur de recherche ENDECA sont :  *   **Système d'exploitation :** Windows 2008 R2 avec tous les correctifs Microsoft installés. *   **Par |
| 9 | Infrastructure | lfm2.5:latest | 17.5 | Les pré-requis système pour installer le moteur de recherche ENDECA sont :   - **Windows 2008 R2** avec toutes les mises à jour Microsoft installées.   - **Trois partitions** :     |
| 10 | Sécurité | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 33.3 | La commande `openssl` permettant de générer un CSR et une clé privée est :  `openssl req -new -newkey rsa:2048 -sha256 -nodes -out [nom_du_domaine].csr -keyout [nom_du_domaine].key |
| 10 | Sécurité | lfm2.5:latest | 21.9 | La commande OpenSSL utilisée est :  ``` openssl req -new -newkey rsa:2048 -sha256 -nodes -out <nom_fichier>.csr -keyout <nom_fichier>.key ```  L’algorithme employé pour le CSR (et  |
| 11 | Sécurité | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 25.2 | Si la clef privée est arrivée à expiration mais que le certificat a été pris sur plusieurs années, vous pouvez utiliser le CSR et la clef des années précédentes. |
| 11 | Sécurité | lfm2.5:latest | 19.1 | Selon le contexte : si la clé privée n’est plus disponible ou est expirée mais que le certificat a été émis sur plusieurs années, on peut utiliser le **CSR et les clés privées des  |
| 12 | Sécurité | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 30.4 | Pour supprimer les anciennes clés GPG associées à CARREFOUR, suivez ces étapes :  1. **Lister les clés existantes** pour identifier l'ID de la clé CARREFOUR en utilisant :    * `gp |
| 12 | Sécurité | lfm2.5:latest | 23.8 | 1. Listez les clés existantes pour identifier l’ID à supprimer :      `gpg --list-keys` (ou `gpg --list-keys --keyid-format LONG`).    2. Notez l’ID de la clé associée à CARREFOUR  |
| 13 | Sécurité | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 27.1 | Le contexte indique que le SSH root est désactivé sur le serveur WEB247 mais ne fournit aucune raison expliquant pourquoi cette désactivation a été effectuée.  Pour se connecter au |
| 13 | Sécurité | lfm2.5:latest | 19.5 | Le SSH root est désactivé sur le serveur WEB247 afin de limiter les privilèges et d’éviter l’exposition de la clé privée. Pour y accéder, il faut se connecter en tant que l’utilisa |
| 14 | SQL | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 27.8 | L'emplacement du serveur SQL de la base de données est indiqué par le champ **`data_source`**.  La requête permettant d'identifier cet emplacement est : ```sql select initial_catal |
| 14 | SQL | lfm2.5:latest | 27.0 | L’emplacement de la base de données d’un client se trouve dans la table `Association_connection` sur le serveur **Assolution** ; on l’identifie en interrogeant le champ `data_sourc |
| 15 | SQL | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 31.6 | Le contexte métier est lié à un problème sur la commande `xxxxxxx` concernant l'ORACLE SQL Attribution, générant une erreur "Attribution Code is CRITICAL". Ce problème nécessite un |
| 15 | SQL | lfm2.5:latest | 27.4 | **Business context** – The “Attribution Code is CRITICAL” error is raised when the test query that validates certificate allocation for an order line is executed. It compares the c |
| 16 | Navigateur | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 31.0 | Pour utiliser UpGestion+ en mode Internet Explorer, plusieurs paramètres doivent être modifiés :  1. **Autoriser le rechargement des sites en mode Internet Explorer** doit être déf |
| 16 | Navigateur | lfm2.5:latest | 21.0 | Le paramètre à modifier est **« Autoriser le rechargement des sites en mode Internet Explorer »**, qu’il faut régler sur **« Autoriser »**. |
| 17 | Mobile | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 28.8 | Pour changer le mot de passe d'une messagerie Exchange existante sur un Xiaomi Rednote 10, suivez ces étapes :  1. Allez sur l’écran d’accueil du téléphone et accédez à **‘Paramètr |
| 17 | Mobile | lfm2.5:latest | 24.5 | Pour changer le mot de passe d’une messagerie Exchange existante sur un smartphone Xiaomi Redmi Note 10 :  1. Ouvrez les Réglages → **Paramètres & Synchronisation**.   2. Sélection |
| 18 | Active Directory | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 24.9 | La commande qui permet de contrôler quel serveur détient les rôles de maître d’opération est **`Netdom query fsmo`**. |
| 18 | Active Directory | lfm2.5:latest | 16.6 | La commande est : **Netdom query fsmo**. |
| 19 | Infrastructure | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 29.1 | Pour créer un compte SFTP sur le serveur 46.20.172.247, vous devez utiliser les commandes suivantes :  1.  **Création de l'utilisateur et attribution au groupe :**     ```bash      |
| 19 | Infrastructure | lfm2.5:latest | 22.8 | On se connecte au serveur (SSH en tant que root, puis `su`) et on exécute :    `adduser -G sftpusers harmoniemutuelle`    L’utilisateur créé appartient alors au groupe **sftpusers* |
| 20 | Réseau | gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL | 27.9 | Pour modifier la configuration VPN FortiClient :  1. Ouvrez l’application FortiClient. 2. Cliquez sur les trois traits à droite de ‘Nom du VPN’, puis sélectionnez ‘Editer la connex |
| 20 | Réseau | lfm2.5:latest | 17.9 | On remplace la valeur de « Passerelle distante » par « vpn.kalidea.com » et ne doit rien d’autre être modifié. |
