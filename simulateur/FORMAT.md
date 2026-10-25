# Format des scénarios et extensions du moteur

Ce document décrit les fichiers YAML du simulateur : l'environnement (le
« monde » simulé), les scénarios qui y superposent un incident, et les règles
que le moteur doit appliquer pour produire des sorties cohérentes (commandes,
journaux, réactions des utilisateurs). Il sert de contrat entre les auteurs de
scénarios et le moteur. `outils/valider.py` en contrôle l'essentiel.

## 1. Fichiers

| Fichier | Contenu |
|---|---|
| `catalogue/niveaux.yaml` | Niveaux N1 à N3 : outils, temps cible, barème, fourchettes de pénalités, règles d'escalade |
| `catalogue/actions.yaml` | Vocabulaire des actions de l'apprenant, niveau requis, commandes et consoles reconnues |
| `catalogue/evenements.yaml` | Événements Windows (vrai ID, source, journal, message en français avec des champs) |
| `catalogue/questions.yaml` | Intentions reconnues quand l'apprenant questionne un demandeur |
| `environnements/vellane.yaml` | Le monde de référence, dans son état normal |
| `scenarios/N<n>/N<n>-<nn>-<nom>.yaml` | Un scénario par fichier |

## 2. Conventions

- **Durées et dates relatives** : `-3j4h12m30s`, `+82m`, `0s` (j, h, m, s).
  Négatif = passé. Toute date relative se compte depuis `horloge` du scénario.
  Les dates absolues (`2026-11-26T06:00:00+01:00`, `2021-03-15`) restent
  possibles pour les validités longues.
- **Tailles** : `412Mo`, `1.8Go`, `237Go`.
- **DN** : écrits sans le suffixe du domaine (`OU=Standard,OU=Postes,OU=Paris`),
  le moteur ajoute `DC=vellane,DC=local`. Dans une valeur en ligne (`{ }` ou
  `[ ]`), un DN se met entre guillemets, sinon YAML le coupe aux virgules
  (le validateur le signale).
- **Chemins** : `utilisateurs.lbernard.verrouillage.verrouille` ou, si une clé
  contient des points ou des barres obliques, une liste :
  `['postes', 'PC-PAR-0233', 'fichiers', 'C:\Windows\...\00017.SPL', 'existe']`.
  Dans un chemin pointé, une clé qui contient elle-même des points
  (`vellane.local`, `10.20.10.0`) est reconnue : le moteur prend la clé
  existante la plus longue. Les index de liste s'écrivent en chiffres
  (`liaisons.0.certificat`). Les clés numériques (options DHCP) se comparent
  comme du texte.
- **Fusion** de `monde` sur l'environnement : dictionnaires fusionnés en
  profondeur, listes remplacées entières, `~` (null) supprime la clé.
- **Objets** : les dictionnaires sont indexés par nom (`utilisateurs.<sAMAccountName>`,
  `postes.<nom>`), jamais par position, pour que la fusion reste simple.

## 3. Environnement (modèle du monde)

### 3.1 Annuaire

| Section | Champs principaux |
|---|---|
| `forets.<nom>` | `racine`, `niveau_fonctionnel`, `maitre_schema`, `maitre_nommage`, `duree_vie_tombstone`, `externe` |
| `domaines.<nom>` | `netbios`, `sid`, `fsmo { pdc, rid, infrastructure }`, `strategie_mdp`, `strategie_verrouillage { seuil, duree, fenetre_observation }`, `kerberos { tolerance_horloge }`, `pso.<nom>`, `ou` (liste), `conteneurs`, `controleurs` (domaine externe) |
| `approbations.<domaine local>.<domaine distant>` | `type` (foret, externe), `sens`, `transitive`, `authentification_selective`, `filtrage_sid`, `secret { version, dernier_changement }`, `coordination` (posé par un contact) |
| `sites.<nom>` | `sous_reseaux`, `controleurs` |
| `replication` | `partitions`, `liens_de_sites.<nom> { sites, cout, intervalle }`, `connexions.<DC destination>.<DC source> { derniere_tentative, derniere_reussite, premier_echec, erreur, echecs_consecutifs, prochaine }`, `etat_par_defaut` |

### 3.2 Machines

`postes`, `serveurs` et `controleurs` partagent les mêmes champs ; seuls les
écarts à la normale sont écrits.

| Champ | Sens | Défaut |
|---|---|---|
| `site`, `ou`, `description`, `groupes` | Compte ordinateur dans l'annuaire | — |
| `compte_ad { active, existe, mdp_version, mdp_dernier_changement, derniere_connexion }` | État du compte ordinateur | actif, mot de passe identique à `mdp_machine_local` |
| `mdp_machine_local` | Version du mot de passe machine connue du poste | celle du compte |
| `os`, `socle`, `type` (portable), `logiciels` | Système et logiciels (ceux du socle plus `logiciels`) | — |
| `allume`, `demarrage`, `arret` | État et heure du dernier démarrage ou arrêt | allumé |
| `reseau { ip, passerelle, dns, mac, apipa, adresse_auto, carte }` | Configuration IP ; `ip: ~` et `apipa: true` pour un poste sans bail | DHCP, DNS de l'option 006 |
| `dns { cache.<nom>: [adresses], inscription }` | Cache du client DNS (ordre = ordre d'essai) | vide |
| `horloge { decalage, derive, type, source, configuration, derniere_synchro }` | Service de temps ; `type` NT5DS (domaine) ou NTP (manuel) | synchronisé sur un DC |
| `kerberos { tickets_purges }` | Vrai après `klist purge` ou une nouvelle session | faux |
| `sessions.<compte> { id, etat, ouverte, deconnectee, mdp_version, jeton, applications, lecteurs_mappes }` | Sessions ouvertes ; `jeton` = groupes figés à l'ouverture | — |
| `identifiants_en_cache` | Comptes qui peuvent ouvrir une session hors ligne | utilisateur principal |
| `services.<nom> { etat, demarrage, recuperation }` | Services Windows (`en_cours`, `arrete`) | services standard démarrés |
| `disques.<lettre> { taille, libre }` | Volumes | — |
| `fichiers.<chemin> { taille, modifie, contenu, type, existe }` | Fichiers et dossiers utiles au scénario | — |
| `journaux` | Liste d'événements (§ 3.9) | vide |
| `ecran` | Message affiché à l'ouverture de session | — |
| `acces_distant` | Faux : seule une session locale (LAPS) ou en cache hors réseau est possible | vrai |
| `bitlocker { actif, cles_dans_ad }`, `laps { derniere_rotation }` | Objets stockés sur le compte ordinateur | — |
| `vm { hote }` | Machine virtuelle et son hôte | — |
| `certificats.<empreinte> { sujet, san, emetteur, modele, debut, fin, cle_privee, archive }` | Magasin Ordinateur\Personnel ; `archive` masque le certificat par défaut | — |
| `iis { sites.<nom>.liaisons, hsts, reliure_auto_certificat }` | Sites et liaisons (`certificat` = empreinte) | — |
| `partages.<nom> { chemin, acces }`, `files_impression.<nom> { pilote, ip, travaux }` | Serveurs de fichiers et d'impression | — |
| `externe` | Machine d'une autre forêt : lecture limitée, actions refusées | — |

### 3.3 Comptes, groupes et divergence entre DC

- `utilisateurs.<sAMAccountName>` : `nom`, `matricule`, `service`, `fonction`,
  `site`, `ou`, `poste`, `telephone` (poste interne), `manager`, `groupes`,
  `description`, `attributs`, `mdp { dernier_changement, version, expire_jamais,
  changer_a_la_connexion }`, `verrouillage { verrouille, depuis, dc }`,
  `mauvais_mdp.<DC> { compteur, dernier }` et `derniere_connexion.<DC>`
  (attributs non répliqués, propres à chaque DC).
- `groupes.<nom>` : `ou`, `etendue`, `description`, `membres` (ordinateurs ;
  les membres utilisateurs se déduisent de `utilisateurs.*.groupes`),
  `membres_generes` (§ 3.8).
- **Divergence entre contrôleurs** : un objet peut porter `origine` (DC où il
  a été créé ou modifié) et `cree`. Une modification d'attribut se décrit dans
  `modifications_ad` : `{ objet, operation, valeur, origine, t, par }`. Le
  moteur calcule ce que voit chaque DC à partir de l'état de la réplication
  (§ 4.8). Deux objets peuvent partager un sAMAccountName : le second a une
  clé distincte et le champ `sam` (`ychevalier~NTE: { sam: ychevalier }`).

### 3.4 Stratégies de groupe

`gpo.<nom>` : `guid`, `description`, `liens [{ cible: <OU> }]` (`""` = racine
du domaine), `filtrage { appliquer: [...], lire: [...] }`, `filtre_wmi`,
`parametres` (texte), `lecteurs.<lettre> { chemin, ciblage_groupes }`,
`imprimantes`, `version`. `filtres_wmi.<nom> { requete }`.

### 3.5 DNS

`dns.serveurs`, `dns.redirecteurs`, `dns.redirecteurs_conditionnels.<zone> { serveurs }`,
`dns.zones.<zone> { type, etendue_replication, mises_a_jour, vieillissement,
nettoyage, enregistrements_generes, enregistrements.<nom>: [{ type, donnees,
statique, horodatage, cree }] }`. `enregistrements_generes` liste les machines
dont le moteur crée lui-même les enregistrements (A, PTR, SRV et CNAME des
DC) ; un nom écrit dans `enregistrements` remplace l'enregistrement généré.

### 3.6 DHCP

`dhcp.<serveur>.etendues.<réseau>` : `nom`, `masque`, `plage [début, fin]`,
`exclusions [[début, fin]]`, `duree_bail`, `options.<code>` (3 passerelle,
6 DNS, 15 domaine), `occupation` (taux de remplissage généré) ou `baux` :

- `{ postes: [noms] }` : baux des postes déclarés, à leur adresse ;
- `{ generer: { nombre, nom: "PC-LYO-{n:04}", n_debut, expire: [min, max], hors_ligne, note } }` :
  baux générés ; `hors_ligne` = machines éteintes (pas de réponse au ping).

### 3.7 PKI

`pki.autorites.<nom>` : `type`, `serveur`, `parent`, `validite { debut, fin }`,
`crl { base, delta: { publiee, prochaine, url } }`, `modeles.<nom> { validite,
inscription_automatique, renouvellement }`.

### 3.8 Socles, déploiement, générateurs

- `socles.<nom>` : `os`, `logiciels`, `notes_de_version`.
- `deploiement.applications.<id>` : `nom`, `type`, `commande`, `contexte`,
  `detection`, `contenu`, `dependances` (déclarées), `prerequis_reels` (ce
  dont l'application a vraiment besoin, connu du moteur seul).
- `deploiement.deploiements.<id>` : `application`, `cible` (groupe),
  `obligatoire`, `disponible`, `echeance`, `fenetre`, `etat_par_poste.<poste>`
  (`succes` ou `{ etat, code, detail }`), `etat_genere.<socle | vpn>` pour les
  postes générés.
- `groupes.<nom>.membres_generes: [{ nombre, nom, n_debut, socle, vpn }]` :
  postes générés pour les populations nombreuses.

### 3.9 Journaux d'événements

```yaml
journaux:
  - evenement: securite/4740        # clé du catalogue
    ref: verrouillage_pdc            # facultatif, unique dans le scénario, cité par les indices
    t: -24m                          # horodatage relatif
    niveau: Échec de l'audit         # facultatif, remplace le niveau du catalogue
    repeter: { intervalle: 45m, jusqu_a: -1h20m }   # ou { nombre: 5, intervalle: 30s }
    donnees: { compte: cmartin, appelant: PC-PAR-SR04 }
```

Le message affiché est le `modele` du catalogue rempli avec `donnees`
({machine} et {machine_fqdn} sont remplis par le moteur). Le moteur ajoute un
bruit de fond réaliste (ouvertures de session 4624, 7036, 1500) sans jamais
masquer les événements du scénario.

### 3.10 Équipes, documents, changements

- `equipes.<id>` : `libelle`, `niveau`, `traite` (sujets), `externe`, `contact`.
- `documents.<id>` : `titre`, `niveau` (outil N1 à N3), `contenu`. Base de
  connaissances, notes de version, demandes validées.
- `changements.<id>` : `titre`, `date`, `auteur`, `contenu`. Calendrier des
  changements, consultable avec `document.consulter`.

## 4. Règles du moteur (extensions N2/N3)

Les propriétés suivantes ne s'écrivent pas : le moteur les calcule à partir
de l'état et les scénarios peuvent les tester dans leurs conditions.

| Propriété calculée | Calcul |
|---|---|
| `<objet>.existe` | Vrai tant que l'objet n'a pas été supprimé |
| `postes.<p>.canal_securise.etat` | `ok` si le compte ordinateur existe, est actif et que `compte_ad.mdp_version` = `mdp_machine_local` (ou la version précédente), sinon `casse` |
| `postes.<p>.jeton_ordinateur` | Groupes du compte ordinateur vus par le DC du site au dernier démarrage |
| `postes.<p>.gpo_appliquees` | GPO dont un lien couvre l'OU du poste (héritage, blocage, application forcée), dont le filtrage accepte le jeton ordinateur et dont le filtre WMI est vrai, au dernier démarrage ou gpupdate |
| `postes.<p>.sessions.<u>.lecteurs` | Lecteurs de GPO_U_Lecteurs_Reseau dont le ciblage croise le `jeton` de la session |
| `postes.<p>.reseau.apipa` | Vrai pour un poste DHCP sans bail |
| `dhcp.<s>.etendues.<e>.libres` | Adresses de la plage, hors exclusions, réservations et baux actifs |
| `postes.<p>.reseau.dns` (DHCP) | Option 006 reçue au dernier bail (démarrage, `ipconfig /renew`, renouvellement à mi-bail) |

### 4.1 Authentification et verrouillage

L'effet `authentification` (et chaque ouverture de session) choisit le DC du
site de la machine. Mot de passe faux ou ancien : `mauvais_mdp` augmente sur
ce DC et sur l'émulateur PDC (transmission de l'échec), 4771 (code 0x18) ou
4776/4625 selon le protocole. Au seuil, le compte est verrouillé (écrit sur le
PDC, réplication urgente), 4740 sur le PDC et sur le DC d'origine avec
l'ordinateur appelant. Le verrouillage tombe seul après
`strategie_verrouillage.duree`. Un mot de passe expiré donne 4771 code 0x17.
La stratégie effective d'un compte est la PSO de plus petite priorité qui le
vise, sinon celle du domaine ; un changement de mot de passe non conforme est
refusé avec le message Windows standard.

### 4.2 Jetons, groupes et GPO

Le jeton d'une session est calculé à l'ouverture, par le DC qui authentifie,
avec la vue de ce DC (§ 4.8). `gpupdate` relit les GPO mais pas les jetons ;
un jeton utilisateur se renouvelle par fermeture et réouverture de session,
un jeton ordinateur par redémarrage (ou `klist -li 0x3e7 purge` suivi de
`gpupdate`). `gpresult /r` affiche les GPO appliquées et filtrées avec la
raison : « Refusé (Sécurité) », « Refusé (filtre WMI) » ; une GPO hors de
portée n'apparaît pas.

### 4.3 Canal sécurisé

Sans canal sécurisé : écran « La relation d'approbation... a échoué », NETLOGON
3210/5719 sur le poste, 5805 et 4768 (0x12 si compte désactivé) sur le DC,
`Test-ComputerSecureChannel` = False, `nltest /sc_verify` = ERROR_ACCESS_DENIED.
`machine.canal_securise.reparer` aligne les deux mots de passe mais ne
réactive pas un compte désactivé. `machine.domaine.joindre` réutilise un
compte existant (même désactivé, il le réactive) et le laisse dans son OU.

### 4.4 Heure et Kerberos

Si |`horloge.decalage`| dépasse `kerberos.tolerance_horloge`, toute demande
Kerberos de la machine échoue : 4771 code 0x25 sur le DC, LsaSrv 40960
(0xc0000133) sur le poste ; les accès retombent en NTLM quand c'est possible,
sinon refus. `w32tm /query /source` donne `source` (Local CMOS Clock quand
rien ne répond), `/configuration` la configuration, `/stripchart` l'écart
avec la référence. Une source NTP injoignable laisse la dérive s'accumuler
(`derive` par jour). `w32tm /config /syncfromflags:domhier /update` puis
`/resync` remet `type` à NT5DS et l'écart à moins d'une seconde.

### 4.5 DNS

Le client interroge ses serveurs dans l'ordre ; un serveur injoignable coûte
un délai puis le suivant est essayé ; sans réponse, DNS-Client 1014. Un nom à
plusieurs A est renvoyé en tourniquet ; le client met en cache la réponse
(TTL 1 h) et essaie les adresses dans l'ordre de son cache ; une adresse
morte coûte environ 21 s par tentative SMB (SMBClient 30803 avec l'adresse).
Le serveur DNS répond à partir de sa copie de la zone (réplication AD), puis
des redirecteurs conditionnels, puis des redirecteurs. Le vieillissement ne
supprime jamais un enregistrement statique.

### 4.6 Localisateur de DC

Requête DNS `_ldap._tcp.<site>._sites.dc._msdcs`, puis ping LDAP du DC ; sans
réponse, recherche dans tout le domaine. Sans résolution DNS du tout, aucun
DC n'est trouvé : « Aucun serveur d'accès n'est actuellement disponible... »
pour qui n'a pas d'identifiants en cache, session en cache sans aucune
ressource pour les autres.

### 4.7 DHCP

Un poste sans bail demande une adresse au démarrage puis toutes les
5 minutes ; si `libres` = 0 : DHCP-Client 1001 côté poste, DHCP 1063 et ligne
d'audit ID 14 côté serveur, 1020 aux seuils de 90 et 100 %. Supprimer un bail
encore utilisé par un poste allumé provoque, à l'attribution suivante, un
conflit d'adresse. Une adresse hors plage d'exclusion attribuée à un
équipement fixe provoque un conflit.

### 4.8 Réplication

Chaque DC a sa vue de l'annuaire. Une modification d'origine O, datée t, est
visible sur le DC D s'il existe un chemin de connexions de O vers D dont
chaque `derniere_reussite` est postérieure à t. Une connexion réussit à son
heure `prochaine` (intervalle du lien de sites), ou à une réplication forcée,
si le DC destination résout le CNAME `<guid_dsa>._msdcs` de la source avec ses
propres serveurs DNS et la joint en RPC ; sinon `erreur` 8524 (DNS) ou 1722
(RPC), NTDS 2087/1925, DFSR 5002. `repadmin /replsummary`, `/showrepl`,
`Get-ADReplicationFailure` et `dcdiag` lisent `replication.connexions`. Deux
objets de même sAMAccountName qui se rencontrent par réplication donnent un
nom en conflit (CNF:) et KDC 11 ; le compte ne peut plus s'authentifier.

### 4.9 Certificats et TLS

Un client HTTPS valide le certificat de la liaison (date, nom ou SAN, chaîne
jusqu'à une racine approuvée, révocation par la CRL). Erreurs : date
(`NET::ERR_CERT_DATE_INVALID`, alerte TLS 45 côté serveur, Schannel 36887),
nom, autorité non approuvée, révocation. Avec HSTS, aucun contournement.
L'inscription automatique renouvelle le certificat à l'approche de
l'expiration et archive l'ancien ; la liaison IIS ne suit que si
`reliure_auto_certificat` est vrai. Supprimer un certificat encore lié :
HttpEvent 15021, connexion réinitialisée.

### 4.10 Approbations

Une approbation fonctionne si les deux côtés ont la même `secret.version` (ou
la précédente) et que les DC de l'autre forêt se résolvent par les
redirecteurs conditionnels. Sinon : NETLOGON 5719 (domaine distant) et 5805
(DC distant), `netdom trust /verify` et `nltest /sc_verify:<domaine>` en
ERROR_ACCESS_DENIED, refus dans les deux sens. `ad.approbation.reinitialiser_mdp`
côté `local` change seulement le secret local ; `les_deux` exige
`coordination` (identifiants de l'autre forêt, obtenus par contact) et aligne
les deux côtés.

### 4.11 Déploiement

Une installation réussit si les `prerequis_reels` de l'application sont
présents sur le poste (socle, logiciels installés, dépendances déployées
avant). Sinon le moteur produit les traces propres au prérequis (pour un
runtime Visual C++ 2005/2008 : SideBySide 33, MSI 11904, 11708, 1033 statut
1603, journal MSI verbeux, code 0x643). Un poste en VPN sans accès au point de
distribution échoue en 0x87D00607 avant toute installation. La console
regroupe les états par socle, site ou code.

### 4.12 Temps simulé et réactions

Chaque action consomme du temps simulé (lecture 15 à 30 s, modification 30 s
à 2 min, redémarrage 3 min) ; `temps.attendre` en ajoute. Les dynamiques et
les échéances (`prochaine`, `a`) se déclenchent au passage de l'heure.
`ticket.demander_action_utilisateur` applique d'abord l'effet standard
(`fermer_session` : nouvelle session et nouveau jeton ; `redemarrer_poste` :
redémarrage, jeton ordinateur, GPO, bail DHCP ; `reessayer_connexion` :
ouverture de session avec le mot de passe actuel), puis la première règle
`retours` dont les conditions sont vraies donne la réponse.

## 5. Scénario

```yaml
schema: scenario/1
id: N2-08                      # = début du nom de fichier, préfixe = niveau
titre: ...
niveau: N2                     # N1, N2 ou N3
temps_cible: 25m               # dans la fourchette du niveau
environnement: vellane
horloge: 2026-11-16T09:05:00+01:00
competences: [...]
resume: >                      # pour le formateur
cause_racine: >                # pour le formateur et le débriefing
tickets: {...}
monde: {...}                   # superposé à l'environnement
dynamiques: {...}
contacts: {...}
indices: {...}
fausses_pistes: {...}          # obligatoire en N2/N3
pieges: {...}                  # obligatoire, au moins un
actions_dangereuses: {...}     # obligatoire en N2/N3
resolution: {...}
communication: {...}
escalade: {...}
debrief: [...]
```

### 5.1 Tickets

```yaml
tickets:
  INC0031702:
    ouvert: -13m
    demandeur: cmartin          # compte, équipe ou Supervision
    poste: PC-PAR-0142
    canal: telephone            # telephone, portail, courriel, supervision
    priorite: P2
    objet: ...
    description: |              # les mots du demandeur
    historique: [{ t, auteur, texte }]       # interventions déjà faites
    reponses: { <intention>: texte, par_defaut: texte }
    verification_identite: { matricule, manager }
    retours:
      <action utilisateur>: [{ si: [...], message, effets: [...] }, ...]
```

Un incident N3 réunit plusieurs tickets ou alertes, dont parfois un ticket
sans rapport qu'il ne faut pas rattacher.

### 5.2 Dynamiques

```yaml
dynamiques:
  session_obsolete:
    quand: { periodique: 3m }     # ou { a: +82m } ou { apres_action: <motif>, delai: 20s }
    si: [<conditions>]
    effets: [<effets>]
```

### 5.3 Contacts

Réponses d'une équipe à `equipe.contacter`, la première dont les conditions
sont vraies : `{ si, reponse, revele: [indices], effets }`. Une réponse peut
dépendre de ce que l'apprenant a déjà établi : une question précise obtient
une réponse précise.

### 5.4 Indices

```yaml
indices:
  evenement_4740_pdc:
    description: ...
    categorie: diagnostic         # diagnostic ; elimination (N2, N3) ; correlation (N3)
    points: 10
    revele_par:                   # un seul suffit
      - { evenement: lockout_pdc }                         # événement affiché
      - { action: ad.utilisateur.lire, cible: cmartin }    # motif d'action
      - { question: changement_recent, ticket: INC0031702 }
      - { contact: Orbis-IT, si: [...] }
```

Un indice est acquis quand l'apprenant a vu l'information. Les points d'une
catégorie font exactement le barème du niveau. Un indice à 0 point sert de
condition ou d'élément de note.

### 5.5 Fausses pistes, pièges, actions dangereuses

- **Fausse piste** : `description`, `pourquoi_credible`, `eliminee_par`
  (indices d'élimination), `actions_inutiles` (motifs), `penalite` appliquée
  à chaque action inutile faite avant l'élimination.
- **Piège** : comportement tentant mais faux. `declencheur` (motif ou liste de
  motifs), `penalite` dans la fourchette du niveau, `effets`, `retour`
  (explication au débriefing).
- **Action dangereuse** : action qui aggrave la situation. Même structure,
  `gravite` (majeure, critique), pénalité forte (N2 : -25 à -50 ; N3 : -40 à
  -80), `fin_scenario: true` pour arrêter le scénario. Au moins une est
  réalisable avec les outils du niveau.

### 5.6 Résolution et communication

- `resolution.conditions` : état final exigé à la clôture.
- `resolution.etapes.<id> { description, points, valide_par: [motifs] }` :
  points de résolution ; au moins une façon de valider chaque étape avec les
  outils du niveau.
- `communication.cloture { ticket, elements.<id> { description, mots_cles, points } }` :
  contenu attendu de la note de clôture (rapprochement par mots-clés, revue
  du formateur possible).
- `communication.actions.<id> { description, points, valide_par }` : messages
  à une population, information d'une équipe, rattachement de tickets.

### 5.7 Escalade

```yaml
escalade:
  equipes: [N3-Infrastructure]     # équipes compétentes ; vide en N1 (escalade injustifiée)
  delai_cible: 15m
  indices_attendus:                # par parcours inférieur au niveau du scénario
    N1: [...]                      # révélables avec les outils N1 (contrôlé)
    N2: [...]
  note:
    elements.<id> { description, mots_cles, points }   # total 30
```

## 6. Motifs, conditions, effets

**Motif d'action** : `action` (une ou plusieurs), `cible` (une ou plusieurs),
`parametres`, `si`, `occurrence` (n-ième fois), `apres { etape, delai }`.
Paramètres : une valeur simple doit être égale ; une liste = l'une des
valeurs ; `~` = paramètre absent ; `{ inclut: [...] }`, `{ exclut: [...] }`,
`{ contient: x }`, `{ sup: x }`, `{ inf: x }`. Un motif sans `action`, avec
seulement `si`, valide un état. `{ dynamique: <id> }` déclenche un piège quand
la dynamique se produit.

**Condition** : `{ chemin, <opérateur>: valeur }` avec `egal`, `different`,
`contient`, `ne_contient_pas`, `contient_un`, `sup`, `inf`, `abs_inf` (valeur
absolue d'une durée), `existe`, `egal_chemin` (comparer deux chemins). Aussi
`{ indice: <id> }`, `{ indice: <id>, revele: false }`,
`{ etape: <id>, validee: false }`. `contient` sur une liste d'objets accepte
un objet partiel (`contient: { donnees: 10.10.2.21 }`).

**Effets** : `definir { chemin, valeur }`, `ajouter { chemin, valeur }` (ajout
à une liste ou augmentation d'une taille), `retirer`, `evenement { machine,
evenement, donnees }`, `authentification { compte, depuis, mdp: actuel |
ancien | faux, protocole, dc }`, `ticket { ... }` (nouveau ticket),
`message { de, texte }`.

## 7. Notation

Barème par niveau dans `catalogue/niveaux.yaml` (total 100) :

| Niveau | Diagnostic | Élimination | Corrélation | Résolution | Communication | Temps |
|---|---|---|---|---|---|---|
| N1 | 30 | — | — | 40 | 15 | 15 |
| N2 | 30 | 15 | — | 30 | 15 | 10 |
| N3 | 25 | 10 | 15 | 25 | 15 | 10 |

- Temps : plein jusqu'au temps cible, zéro au double.
- Pénalités : pièges et actions dangereuses s'ajoutent (une fois par piège,
  sauf `occurrence`) ; une action dangereuse `fin_scenario` plafonne la note
  à 20.
- Escalade depuis un parcours inférieur : diagnostic préliminaire 30 (indices
  attendus), décision 30 (bonne équipe), note de transmission 30, temps 10
  (`delai_cible`). Escalade d'un cas du niveau du parcours : -20. Mauvaise
  équipe : -10.

## 8. Validation

```sh
python3 outils/valider.py            # erreurs et avertissements
python3 outils/valider.py --resume   # tableau récapitulatif
python3 outils/test_valider.py       # tests du validateur
```

Le validateur contrôle la syntaxe (valeurs en ligne coupées par une virgule),
les références, les barèmes, les fourchettes de pénalités, la présence des
pièges, fausses pistes et actions dangereuses, et l'accessibilité des indices
et des étapes selon les outils de chaque niveau. Il ne juge pas le réalisme :
la relecture par un formateur reste nécessaire.
