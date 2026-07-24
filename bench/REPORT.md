# 📊 Benchmark RAG : Gemma-4-E4B vs LFM2.5

Comparaison de deux modèles LLM sur 20 questions factuelles posées à la base documentaire (pipeline RAG identique : FTS top-3 → contexte commun → réponse).

**Date** : 2026-07-16  |  **Corpus** : knowledge.duckdb (237 docs)  |  **Température** : 0.1

**Modèles** :
- `hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL` (Gemma-4-E4B, 7.5B)
- `lfm2.5:latest` (LFM2.5, 8.5B MoE)

## 🏆 Score final

| Modèle | Score /10 | Fidélité | Précision | Complétude | Anti-halluc. | Latence moy. (s) |
|---|---:|---:|---:|---:|---:|---:|
| **Gemma-4-E4B** | **9.9** | 40/40 | 40/40 | 39/40 | 40/40 | 28.0 |
| **LFM2.5** | **8.7** | 39/40 | 33/40 | 31/40 | 36/40 | 21.8 |

## 📝 Détail par question

Critères notés sur 2 chacun (total /8 par réponse) : **F**=Fidélité au contexte, **P**=Précision, **C**=Complétude, **H**=anti-Hallucination.

### Q1 — Quelle est l'adresse web pour accéder à l'outil de restauration Veeam Backup des dossiers et fichiers ?
*Thème : Sauvegarde  ·  Doc attendu : `Veeam Backup UP de dossiers`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 23.0s

> L'adresse web pour accéder à l'outil de restauration Veeam Backup des dossiers et fichiers est :
https://192.168.10.35:9443/Restore.aspx#/report/vms

**LFM2.5** — 8/8 (F=2 P=2 C=2 H=2) · 17.5s

> L'adresse web pour accéder à l'outil de restauration Veeam Backup des dossiers et fichiers est : https://192.168.10.35:9443/Restore.aspx#/report/vms

*Note du juge : URL exacte pour les deux.*

---

### Q2 — Comment restaure-t-on un dossier via Veeam Backup une fois le serveur sélectionné ?
*Thème : Sauvegarde  ·  Doc attendu : `Veeam Backup UP de dossiers`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 30.9s

> Après avoir sélectionné le serveur, vous devez :

1. **Choisir la date et monter :** Cliquez sur le calendrier pour choisir la date de restauration souhaitée, puis cliquez sur « Mount ». Une fois monté, l'arborescence du serveur sera visible.
2. **Restauration d’un seul fichier ou dossier :** Sélectionnez l'élément dans ‘Other Action’, choisissez ‘Restore’, et sélectionnez ensuite si vous souhaitez ‘Overwrite’ (écraser), ‘Keep’ (garder) ou ‘Download’ (télécharger).
3. **Restauration de plusieurs fichiers ou dossiers :** Sélectionnez les éléments un à un en utilisant ‘Other Actions’ puis ‘Add t…

**LFM2.5** — 7/8 (F=2 P=2 C=1 H=2) · 25.6s

> Après avoir sélectionné le serveur et monté l’arborescence, procédez ainsi :

1. Dans la liste des dossiers affichée, sélectionnez le dossier (ou plusieurs) à restaurer.  
2. Ouvrez la fenêtre « Pending restore (Nombres items) ».  
3. Cliquez sur **Restore**.  
4. Choisissez l’action : **Overwrite** (écraser le fichier existant), **Keep** (garder le fichier actuel) ou **Download** (télécharger les fichiers).  
5. Confirmez en répondant « YES » si vous êtes sûr d’écraser le fichier.

*Note du juge : Gemma complet (Mount, calendrier, Restore, Overwrite/Keep/Download). LFM omet l'étape Mount/calendrier.*

---

### Q3 — Que signifie l'erreur « connect ECONNREFUSED 127.0.0.1:4004 » sur l'API GraphQL VUP et quel compte utiliser pour intervenir ?
*Thème : Dépannage  ·  Doc attendu : `GRAPHQL - Erreur_pm2`*

**Gemma-4-E4B** — 7/8 (F=2 P=2 C=1 H=2) · 28.2s

> L'erreur « connect ECONNREFUSED 127.0.0.1:4004 » est signalée dans le contexte d'un problème avec l’api VUP, tel qu'une erreur de chargement.

Pour intervenir et résoudre ce problème, il faut se connecter sur le bon serveur en fonction de l’alerte en utilisant le compte **AgentRM**.

**LFM2.5** — 6/8 (F=1 P=2 C=2 H=1) · 24.7s

> The error “connect ECONNREFUSED 127.0.0.1:4004” means the GraphQL API endpoint is not reachable because the WCF service on that host is not running or not bound to port 4004. To fix it, connect to the correct server (the one listed for each alert – 10.201.10.19, 10.201.10.20, or 10.201.10.20) and restart the VUP_WCF pool using the pm2 commands with the **AgentRM** account.

*Note du juge : Gemma: AgentRM OK mais n'explique pas vraiment ECONNREFUSED. LFM: explique bien MAIS répond en anglais (contexte FR) + IPs approximatives.*

---

### Q4 — Quel pool d'applications IIS doit-on recycler lors d'un problème avec l'API VUP, et pourquoi ?
*Thème : Dépannage  ·  Doc attendu : `GRAPHQL - Erreur_pm2`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 26.2s

> Le pool d'applications IIS à recycler est **VUP_WCF**.

La raison de cette action est que l’API va mapper les WSDL du WCF au démarrage.

**LFM2.5** — 7/8 (F=2 P=2 C=2 H=1) · 23.6s

> Le pool d’application **« VUP_WCF »** sur le serveur concerné (10.201.10.19 ou 10.201.10.20) doit être recyclé, car l’erreur de connexion à l’API VUP est liée à un problème de chargement de cette API et au mappage des WSDL qui se produit au démarrage ; le redémarrage du pool permet de résoudre ces difficultés.

*Note du juge : VUP_WCF + raison (WSDL au démarrage) pour les deux. LFM ajoute des IPs non vérifiables.*

---

### Q5 — Quelle est la procédure pour créer une boîte aux lettres partagée pour une adresse en up-cse.fr ?
*Thème : Messagerie  ·  Doc attendu : `création-boite-aux-lettres-partagée`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 28.5s

> Pour une demande concernant une adresse mail en « up-cse.fr », la procédure est la suivante :

1. **Initialisation :** Aller sur MDaemon pour rediriger vers la boîte Microsoft.
2. **Connexion à Microsoft :** Utiliser un compte « admin » et se connecter au site suivant : `https://admin.microsoft.com/Adminportal/Home?#/SharedMailbox/:/addsharedmailbox`.
3. **Nomenclature :** Toujours mettre « Kalidea - » avant le nom de la boîte (Exemple : Kalidea - Assistance SPE).

**LFM2.5** — 7/8 (F=2 P=2 C=1 H=2) · 21.5s

> Pour créer une boîte aux lettres partagée pour une adresse en « up‑cse.fr », se rendre sur **MDaemon** et, à partir de là, utiliser le lien : https://admin.microsoft.com/Adminportal/Home?#/SharedMailbox/:/addsharedmailbox en tant que compte **admin**.

*Note du juge : Gemma: MDaemon + Microsoft + nomenclature. LFM omet la nomenclature Kalidea-.*

---

### Q6 — Quel préfixe faut-il obligatoirement ajouter devant le nom d'une boîte aux lettres partagée ?
*Thème : Messagerie  ·  Doc attendu : `création-boite-aux-lettres-partagée`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 24.9s

> Il faut obligatoirement mettre « Kalidea - » avant le nom de la boîte aux lettres partagée.

**LFM2.5** — 4/8 (F=2 P=0 C=0 H=2) · 23.9s

> Le contexte fourni n’indique pas de préfixe obligatoire à ajouter devant le nom d’une boîte aux lettres partagée.

*Note du juge : Gemma: 'Kalidea -' correct. LFM: ECHEC - affirme que le contexte n'indique aucun préfixe alors qu'il y est.*

---

### Q7 — Comment ajouter un code d'activation sur Sage 100 si la fenêtre de licence expirée ne s'affiche pas au démarrage ?
*Thème : Sage  ·  Doc attendu : `Procédure code d'activation Sage`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 29.7s

> Si la fenêtre de licence expirée ne s'affiche pas au démarrage, vous devez suivre la deuxième solution :

1. Ouvrez Sage 100.
2. Cliquez sur l’icône "?" puis sur "À propos de Sage 100cloud".
3. Dans la nouvelle fenêtre, cliquez sur "Code annuel".
4. Saisissez le code dans les champs correspondants (le copier-coller ne fonctionne pas).

**LFM2.5** — 8/8 (F=2 P=2 C=2 H=2) · 20.9s

> Suivez la deuxième solution : ouvrez Sage 100, cliquez sur l’icône « ? », puis sur « À propos de Sage 100cloud », puis sélectionnez « Code annuel » et saisissez le code dans les champs correspondants (le copier‑coller ne fonctionne pas).

*Note du juge : Procédure exacte (? > À propos > Code annuel) pour les deux.*

---

### Q8 — Faut-il relancer une indexation partielle ou totale après un plantage de l'indexation ENDECA ?
*Thème : Dépannage  ·  Doc attendu : `ENDECA - Erreur JAVA_Indexation`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 26.2s

> Après un plantage de l'indexation total, il faut toujours relancer la **total**. Il ne faut surtout pas relancer la partial.

**LFM2.5** — 6/8 (F=2 P=1 C=1 H=2) · 18.4s

> Oui, il faut d’abord relancer l’indexation totale (durable 3 h à 4 h) puis, une fois celle‑ci terminée, réactiver et lancer la tâche d’indexation partielle.

*Note du juge : Gemma: clair 'toujours total, jamais partial'. LFM dilue (relance total PUIS relance partial), message ambigu.*

---

### Q9 — Quels sont les pré-requis système (OS et partitions) pour installer le moteur de recherche ENDECA ?
*Thème : Infrastructure  ·  Doc attendu : `ENDECA - Installation`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 25.6s

> Les pré-requis système pour installer le moteur de recherche ENDECA sont :

*   **Système d'exploitation :** Windows 2008 R2 avec tous les correctifs Microsoft installés.
*   **Partitions :** Trois partitions doivent être présentes :
    *   C = SYSTEM (60 Go)
    *   D = Endeca-Platform (40 Go)
    *   E = Endeca-Application (40 Go)

**LFM2.5** — 8/8 (F=2 P=2 C=2 H=2) · 17.5s

> Les pré-requis système pour installer le moteur de recherche ENDECA sont :  
- **Windows 2008 R2** avec toutes les mises à jour Microsoft installées.  
- **Trois partitions** :  
  - C = SYSTEM (60 Go)  
  - D = Endeca-Platform (40 Go)  
  - E = Endeca-Application (40 Go).

*Note du juge : Win 2008 R2 + 3 partitions (60/40/40) pour les deux.*

---

### Q10 — Quelle commande openssl permet de générer un CSR et une clé privée pour un certificat SSL, et avec quel algorithme ?
*Thème : Sécurité  ·  Doc attendu : `SSL - Changement de certificat`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 33.3s

> La commande `openssl` permettant de générer un CSR et une clé privée est :

`openssl req -new -newkey rsa:2048 -sha256 -nodes -out [nom_du_domaine].csr -keyout [nom_du_domaine].key -subj "/C=FR/ST=[État]/L=[Ville]/OU=[Unité d'organisation]/O=[Organisation]/CN=[Nom du domaine]"`

Les algorithmes utilisés sont **rsa:2048** et **sha256**.

**LFM2.5** — 6/8 (F=2 P=1 C=1 H=2) · 21.9s

> La commande OpenSSL utilisée est :

```
openssl req -new -newkey rsa:2048 -sha256 -nodes -out <nom_fichier>.csr -keyout <nom_fichier>.key
```

L’algorithme employé pour le CSR (et la clé privée générée) est **SHA‑256**.

*Note du juge : Gemma: commande complète avec -subj, RSA 2048. LFM: omet -subj et confond sha256 (digest) avec l'algo de clé.*

---

### Q11 — Que peut-on faire si la clé privée d'un certificat SSL est arrivée à expiration mais que le certificat a été pris sur plusieurs années ?
*Thème : Sécurité  ·  Doc attendu : `SSL - Changement de certificat`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 25.2s

> Si la clef privée est arrivée à expiration mais que le certificat a été pris sur plusieurs années, vous pouvez utiliser le CSR et la clef des années précédentes.

**LFM2.5** — 8/8 (F=2 P=2 C=2 H=2) · 19.1s

> Selon le contexte : si la clé privée n’est plus disponible ou est expirée mais que le certificat a été émis sur plusieurs années, on peut utiliser le **CSR et les clés privées des années antérieures** pour renouveler le certificat.

*Note du juge : Réutiliser CSR/clé des années précédentes pour les deux.*

---

### Q12 — Comment supprimer les anciennes clés GPG associées à CARREFOUR avant d'en créer une nouvelle ?
*Thème : Sécurité  ·  Doc attendu : `GPG - Carrefour`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 30.4s

> Pour supprimer les anciennes clés GPG associées à CARREFOUR, suivez ces étapes :

1. **Lister les clés existantes** pour identifier l'ID de la clé CARREFOUR en utilisant :
   * `gpg --list-keys`
   * Ou `gpg --list-keys --keyid-format LONG`

2. **Noter l'ID** de la clé à supprimer (par exemple : `0402358D`).

3. **Supprimer les clés** en utilisant leur ID ou le nom/email associé :
   * **Par ID :**
     * Supprimer la clé privée : `gpg --delete-secret-keys [ID]`
     * Supprimer la clé publique : `gpg --delete-keys [ID]`
   * **Par nom/email :**
     * Supprimer la clé privée : `gpg --delete-s…

**LFM2.5** — 7/8 (F=2 P=1 C=2 H=2) · 23.8s

> 1. Listez les clés existantes pour identifier l’ID à supprimer :  
   `gpg --list-keys` (ou `gpg --list-keys --keyid-format LONG`).  

2. Notez l’ID de la clé associée à CARREFOUR (exemple : `0402358D`).  

3. Supprimez la clé privée :  
   `gpg --delete-secret-keys 0402358D`.  

4. Supprimez la clé publique :  
   - avec l’ID : `gpg --delete-keys 0402358D`  
   - ou par nom/email : `gpg --delete-secret-keys "CARREFOUR - KALIDEA"`.  

5. Répétez les étapes 3‑4 pour chaque ancienne clé associée à CARREFOUR avant de générer une nouvelle clé.

*Note du juge : Gemma complet. LFM: erreur étape 4 (delete-secret-keys au lieu de delete-keys pour la clé publique).*

---

### Q13 — Pourquoi le SSH root est-il désactivé sur le serveur WEB247 et comment s'y connecte-t-on ?
*Thème : Sécurité  ·  Doc attendu : `GPG - Carrefour`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 27.1s

> Le contexte indique que le SSH root est désactivé sur le serveur WEB247 mais ne fournit aucune raison expliquant pourquoi cette désactivation a été effectuée.

Pour se connecter au serveur, il faut utiliser le compte `thomas` via SSH à l'adresse 46.20.172.247 (WEB247 - TUX22).

**LFM2.5** — 7/8 (F=2 P=2 C=2 H=1) · 19.5s

> Le SSH root est désactivé sur le serveur WEB247 afin de limiter les privilèges et d’éviter l’exposition de la clé privée. Pour y accéder, il faut se connecter en tant que l’utilisateur **thomas** (via `ssh thomas@46.20.172.247`) puis utiliser la commande `su` pour devenir root.

*Note du juge : Gemma honnête (dit que le contexte ne donne pas la raison). LFM INVENTE une raison ('limiter privilèges') = hallucination.*

---

### Q14 — Comment trouve-t-on l'emplacement (serveur SQL) de la base de données d'un client et quelle requête permet de l'identifier ?
*Thème : SQL  ·  Doc attendu : `Client résilié V2 - Suppression`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 27.8s

> L'emplacement du serveur SQL de la base de données est indiqué par le champ **`data_source`**.

La requête permettant d'identifier cet emplacement est :
```sql
select initial_catalog, data_source 
from assolution.dbo.Association_connection 
where initial_catalog like '%CEV2_PENPDCPIC%'
```

**LFM2.5** — 8/8 (F=2 P=2 C=2 H=2) · 27.0s

> L’emplacement de la base de données d’un client se trouve dans la table `Association_connection` sur le serveur **Assolution** ; on l’identifie en interrogeant le champ `data_source` avec une condition sur le catalogue initial (ex. :  

```sql
SELECT initial_catalog, data_source 
FROM assolution.dbo.Association_connection 
WHERE initial_catalog LIKE '%CEV2_PENPDCPIC%';
```  

Le résultat fournit le chemin du serveur SQL associé à ce client.

*Note du juge : data_source + requête Association_connection exacte pour les deux.*

---

### Q15 — Quel est le contexte métier et la requête SQL de test associés à l'erreur ORACLE « Attribution Code is CRITICAL » ?
*Thème : SQL  ·  Doc attendu : `ORACLE - SQL Attribution de codes`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 31.6s

> Le contexte métier est lié à un problème sur la commande `xxxxxxx` concernant l'ORACLE SQL Attribution, générant une erreur "Attribution Code is CRITICAL". Ce problème nécessite une communication de haute importance avec le logiciel DSI.

La requête SQL de test associée est :
```sql
SELECT OL.ORD_ID 
FROM CTB_ORDLINE OL
INNER JOIN CTB_GIFTCERTIFICATE G ON G.ORD_ID = OL.ORD_ID AND G.ORL_ID = OL.ORL_ID AND G.PPE_ID = OL.PPE_ID
WHERE 1 = 1
  AND (SELECT COUNT(GFC_ID)
         FROM CTB_GIFTCERTIFICATE
        WHERE ORD_ID = OL.ORD_ID
          AND ORL_ID = OL.ORL_ID
          AND PPE_ID = OL.PPE_I…

**LFM2.5** — 6/8 (F=2 P=1 C=2 H=1) · 27.4s

> **Business context** – The “Attribution Code is CRITICAL” error is raised when the test query that validates certificate allocation for an order line is executed. It compares the count of GFCERTIFICATE records associated with a given order (and PPE) against the order quantity; if the certificate count exceeds the quantity, the system aborts the operation. This check is part of the pre‑launch validation for the critical command xxxxxxx.

**Test SQL (as provided)**  

```sql
SELECT OL.ORD_ID
FROM CTB_ORDLINE OL
INNER JOIN CTB_GIFTCERTIFICATE G
  ON G.ORD_ID = OL.ORD_ID
 AND G.ORL_ID   = OL.ORL_I…

*Note du juge : Gemma: contexte + requête fidèles. LFM: répond en ANGLAIS (contexte/question FR) + 'GFCERTIFICATE' au lieu de CTB_GIFTCERTIFICATE.*

---

### Q16 — Quel paramètre doit-on modifier dans Microsoft Edge pour utiliser UpGestion+ en mode Internet Explorer ?
*Thème : Navigateur  ·  Doc attendu : `Continuite_Edge`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 31.0s

> Pour utiliser UpGestion+ en mode Internet Explorer, plusieurs paramètres doivent être modifiés :

1. **Autoriser le rechargement des sites en mode Internet Explorer** doit être défini sur « Autoriser ».
2. La valeur de **Permettre à Internet Explorer d’ouvrir des sites dans Microsoft Edge** doit être définie sur « Jamais ».
3. Dans les paramètres Edge, sous le menu « Apparence », il faut activer le bouton du **mode Internet Explorer**.
4. Il est nécessaire d'ajouter l’URL `https://www.123cegestionplus.com` dans la liste des pages en mode Internet Explorer.

**LFM2.5** — 7/8 (F=2 P=2 C=1 H=2) · 21.0s

> Le paramètre à modifier est **« Autoriser le rechargement des sites en mode Internet Explorer »**, qu’il faut régler sur **« Autoriser »**.

*Note du juge : Gemma: complet (plusieurs étapes du doc). LFM: juste le paramètre principal, minimaliste.*

---

### Q17 — Comment changer le mot de passe d'une messagerie Exchange existante sur un smartphone Xiaomi Redmi Note 10 ?
*Thème : Mobile  ·  Doc attendu : `Xiaomi Rednote 10 5G`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 28.8s

> Pour changer le mot de passe d'une messagerie Exchange existante sur un Xiaomi Rednote 10, suivez ces étapes :

1. Allez sur l’écran d’accueil du téléphone et accédez à **‘Paramètres’**.
2. Allez dans **‘Comptes & Synchronisation’**.
3. Sélectionnez **‘Exchange’**.
4. Accédez à **‘Paramètres de compte’**.
5. Choisissez votre boîte mail (par exemple, ‘prenom.nom@up.coop’).
6. Sélectionnez **‘Paramètres de réception’**.
7. Modifiez votre mot de passe et sélectionnez **‘Suivant’**.

Une fois le changement effectué, les mails devraient être accessibles avec l'arrivée des nouveaux messages.

**LFM2.5** — 7/8 (F=2 P=1 C=2 H=2) · 24.5s

> Pour changer le mot de passe d’une messagerie Exchange existante sur un smartphone Xiaomi Redmi Note 10 :

1. Ouvrez les Réglages → **Paramètres & Synchronisation**.  
2. Sélectionnez **Échange** puis **Paramètres de compte**.  
3. Choisissez votre boîte mail (ex. : prenom.nom@up.coop) et allez dans **Paramètres de réception**.  
4. Modifiez le mot de passe et confirmez en appuyant sur **Suivant**.  

Les nouveaux messages seront alors accessibles.

*Note du juge : Gemma: libellés exacts. LFM: 'Paramètres & Synchronisation' au lieu de 'Comptes &' et 'Échange' au lieu de 'Exchange'.*

---

### Q18 — Quelle commande permet de vérifier quel serveur détient les rôles FSMO dans Active Directory ?
*Thème : Active Directory  ·  Doc attendu : `Transfert des rôles FSMO`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 24.9s

> La commande qui permet de contrôler quel serveur détient les rôles de maître d’opération est **`Netdom query fsmo`**.

**LFM2.5** — 8/8 (F=2 P=2 C=2 H=2) · 16.6s

> La commande est : **Netdom query fsmo**.

*Note du juge : Netdom query fsmo pour les deux.*

---

### Q19 — Comment crée-t-on un compte SFTP sur le serveur 46.20.172.247 et à quel groupe doit-il appartenir ?
*Thème : Infrastructure  ·  Doc attendu : `Creation_SFTP`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 29.1s

> Pour créer un compte SFTP sur le serveur 46.20.172.247, vous devez utiliser les commandes suivantes :

1.  **Création de l'utilisateur et attribution au groupe :**
    ```bash
    adduser -G sftpusers [nom_utilisateur]
    passwd [nom_utilisateur]
    ```
2.  **Configuration des répertoires et permissions :**
    ```bash
    mkdir -p /sftp/[nom_utilisateur]/incoming
    chown -R [nom_utilisateur]:sftpusers /sftp/[nom_utilisateur]/incoming
    ```
3.  **Modification du fichier `/etc/passwd` :**
    Vous devez modifier le fichier `/etc/passwd` pour ajouter la ligne de l'utilisateur avec `/sbin/n…

**LFM2.5** — 7/8 (F=2 P=2 C=1 H=2) · 22.8s

> On se connecte au serveur (SSH en tant que root, puis `su`) et on exécute :  

`adduser -G sftpusers harmoniemutuelle`  

L’utilisateur créé appartient alors au groupe **sftpusers**.

*Note du juge : Gemma: complet (adduser, passwd, mkdir, chown, nologin). LFM: minimaliste, omet passwd/mkdir/chown/nologin.*

---

### Q20 — Comment modifie-t-on la configuration VPN FortiClient (quelle passerelle distante) et que ne faut-il surtout pas changer ?
*Thème : Réseau  ·  Doc attendu : `Paramétrage VPN FortiClient`*

**Gemma-4-E4B** — 8/8 (F=2 P=2 C=2 H=2) · 27.9s

> Pour modifier la configuration VPN FortiClient :

1. Ouvrez l’application FortiClient.
2. Cliquez sur les trois traits à droite de ‘Nom du VPN’, puis sélectionnez ‘Editer la connexion sélectionnée’.
3. Dans le champ ‘Passerelle distante’, remplacez ‘128.127.129.18’ par ‘vpn.kalidea.com’ et cliquez sur ‘Sauvegarder’.

Il est impératif de ne rien modifier d’autre que cette passerelle distante.

**LFM2.5** — 7/8 (F=2 P=2 C=1 H=2) · 17.9s

> On remplace la valeur de « Passerelle distante » par « vpn.kalidea.com » et ne doit rien d’autre être modifié.

*Note du juge : Gemma: procédure complète + 'ne rien modifier d'autre'. LFM: correct mais minimaliste, phrase mal formée.*

---

## 🔍 Analyse qualitative

### Forces / faiblesses

**Gemma-4-E4B** :
- ✅ Réponses exhaustives et bien structurées (étapes complètes).
- ✅ Discipline exemplaire anti-hallucination : dit explicitement quand le contexte manque (Q13).
- ✅ Reste fidèlement en français.
- ⚠️ Plus lent en moyenne.

**LFM2.5** :
- ✅ Plus rapide (latence plus faible).
- ✅ Souvent correct sur les questions simples.
- ❌ Hallucinations (Q13 : invente une raison non documentée).
- ❌ Échecs purs de lecture du contexte (Q6 : nie l'existence d'un préfixe pourtant présent).
- ❌ Instabilité linguistique : répond en anglais sur 2 questions posées en français (Q3, Q15).
- ❌ Erreurs techniques subtiles (Q12 : confond `delete-keys` et `delete-secret-keys`).

## ✅ Recommandation

**Gemma-4-E4B** remporte ce benchmark (9.9/10 contre 8.7/10). 

Pour un usage de **base de connaissances technique en français**, Gemma-4-E4B est nettement préférable : moins d'hallucinations, aucune dérive linguistique, réponses plus complètes. LFM2.5 peut convenir pour des questions simples où la latence compte, mais sa propension à halluciner et à répondre en anglais le rend risqué pour un assistant d'exploitation.
