# Simulateur de dépannage Active Directory : scénarios du MVP

Seize scénarios d'incidents, écrits en YAML, pour un simulateur de support
où l'apprenant traite des tickets dans un environnement Windows simulé
(annuaire, postes, serveurs, DNS, DHCP, PKI, déploiement). Ce dossier contient
les **données** du simulateur : le monde de référence, les catalogues, les
scénarios, leur format et un validateur. Le moteur qui les exécute n'est pas
dans ce dépôt ; `FORMAT.md` décrit ce qu'il doit implémenter.

## Niveaux

| Niveau | Périmètre | Outils | Temps cible |
|---|---|---|---|
| N1 | Un compte ou un poste | Consoles graphiques, cmdlets de base, journaux du poste | 5 à 15 min |
| N2 | Poste, annuaire et réseau ensemble ; plusieurs causes à éliminer | + journaux des DC et serveurs, GPO, DNS, DHCP, nltest, w32tm, klist, gpresult, repadmin (lecture) | 15 à 35 min |
| N3 | Un site ou un service entier ; corrélation de plusieurs tickets ; risque d'aggravation | + réplication forcée, approbations, PKI, IIS, virtualisation, ciblage des déploiements | 30 à 60 min |

Les outils disponibles sont ceux du **parcours** de l'apprenant. Un apprenant
N1 qui reçoit un ticket N2 n'a que ses outils N1 : il doit faire un premier
diagnostic et **escalader** avec une note de transmission, notée sur les
éléments attendus. Escalader un cas de son niveau coûte 20 points. Le détail
des barèmes et des fourchettes de pénalités est dans
`catalogue/niveaux.yaml` et au § 7 de `FORMAT.md`.

## Scénarios

Tous se passent chez **Vellane**, distributeur fictif (siège à Paris, agences
à Lyon et Nantes, filiale Orbis dans une autre forêt), en novembre 2026.

### N1

| Id | Incident | Cause | Pièges | Action dangereuse |
|---|---|---|---|---|
| N1-01 | Compte verrouillé | Cinq erreurs de saisie (Verr. Maj) | Homonyme à Lyon, réinitialisation inutile, action sans vérifier l'identité | Déverrouiller tous les comptes du domaine |
| N1-02 | Mot de passe expiré | Le compte relève d'une PSO (14 caractères, 60 jours), pas de la stratégie du domaine | Donner la règle des 12 caractères, réinitialiser le compte d'un dirigeant sans vérification, mot de passe provisoire sans changement imposé | « N'expire jamais », retrait du groupe de la PSO |
| N1-03 | Lecteur réseau manquant | Mutation RH vers le contrôle de gestion, pas dans GG_CTRLGEST_Projets_RW | Session à rouvrir (jeton), groupe non validé, lecture seule ; droits RH résiduels à signaler | Copier les groupes d'un collègue |
| N1-04 | Spouleur planté | Travail d'impression corrompu qui le refait planter à chaque démarrage | Redémarrer en boucle, clôturer trop tôt ; fausse piste du pilote | Vider la file partagée du serveur, supprimer tout le dossier spool |
| N1-05 | Disque C plein | 148 Go de traces Compteo laissées au niveau 5 par l'éditeur | Nettoyage qui ne traite pas la cause, fichiers personnels sans accord | Dossiers système, Documents de l'utilisatrice, base Compteo |

### N2

| Id | Incident | Cause | Fausses pistes | Action dangereuse |
|---|---|---|---|---|
| N2-06 | GPO non appliquée | Poste recyclé resté dans l'OU de Lyon, puis filtrage sur GG_Postes_Compta, puis redémarrage nécessaire | GPO refusée par filtre WMI, compte de l'utilisateur, réplication | Ouvrir le filtrage, lier à la racine, toucher la Default Domain Policy |
| N2-07 | Relation d'approbation échouée | Compte ordinateur désactivé et déplacé par le script de nettoyage après six mois de congé | « Même nom sur le réseau » (texte du 3210), heure non synchronisée, DNS | Supprimer le compte ordinateur (clé BitLocker perdue) |
| N2-08 | Reverrouillage en boucle | Session déconnectée en salle de réunion avec l'ancien mot de passe (4740 du PDC) | Téléphone, attaque, poste habituel | Modifier la stratégie de verrouillage du domaine |
| N2-09 | Partage lent ou inaccessible | A statique vers l'ancienne adresse à côté du A dynamique après migration | Serveur lent, pare-feu (texte du 30803), poste de l'utilisateur | Supprimer le bon enregistrement, nettoyage DNS agressif |
| N2-10 | Kerberos en échec sur un poste | Source NTP manuelle posée par un logiciel de badges ; +7 min 42 s | Mise à jour Windows, compte, DC de Nantes | Élargir la tolérance Kerberos, changer l'heure d'un DC |
| N2-11 | Postes neufs sans IP | Étendue de Lyon pleine des baux des 42 postes remplacés | Câblage, pilote du nouveau modèle, serveur DHCP | Supprimer tous les baux, supprimer l'étendue |

### N3

| Id | Incident | Tickets | Cause | Fausses pistes | Action dangereuse |
|---|---|---|---|---|---|
| N3-12 | Modifications AD invisibles à Nantes | 3 | DNS de la nouvelle carte de DC-NTE-01 (routeur, 8.8.8.8), erreur 8524 ; un compte recréé à la main ce matin sur ce DC deviendra un doublon à la prochaine réplication | Lien WAN, « il faut attendre », DC à reconstruire (le 2087 propose le nettoyage) | Forcer la réplication avant d'avoir traité le doublon, retirer le DC, cohérence stricte |
| N3-13 | Site de Lyon bloqué | 6 dont 1 sans rapport | DC-LYO-01 en maintenance « sans impact » et option DHCP 006 avec ce seul DNS | GPO modifiée la veille, lien WAN, antivirus, mot de passe expiré | Retirer le DC, saisir des rôles FSMO, DNS public dans l'option 006 |
| N3-14 | Accès à Orbis cassé | 4 | Secret de l'approbation réinitialisé d'un seul côté par Orbis | Redirecteur conditionnel lent, mot de passe changé la veille, pare-feu | Supprimer l'approbation, désactiver le filtrage SID |
| N3-15 | Intranet inaccessible pour tous | 6 dont 1 sans rapport | Liaisons IIS sur le certificat échu ; le renouvelé est dans le magasin mais pas lié | Mises à jour de la nuit, CRL, IIS arrêté | Certificat auto-signé, GPO qui ignore les erreurs de certificat, renouveler l'AC |
| N3-16 | Déploiement en échec sur 23 postes | 4 | Visual C++ 2008 retiré du nouveau socle, non déclaré en dépendance (SideBySide 33) | Contenu en VPN, antivirus, droits, compatibilité 24H2 | Déployer le runtime partout, désinstaller l'application, modifier le master |

Chaque scénario a au moins un piège ; chaque N2/N3 a au moins une fausse
piste crédible et des actions dangereuses lourdement pénalisées, dont une au
moins est faisable avec les outils du niveau.

## Organisation

```
simulateur/
├── FORMAT.md                 format YAML et règles du moteur
├── catalogue/
│   ├── niveaux.yaml          outils, temps, barèmes, escalade
│   ├── actions.yaml          actions de l'apprenant (commandes, consoles, niveau)
│   ├── evenements.yaml       événements Windows (ID, source, message)
│   └── questions.yaml        intentions des questions aux demandeurs
├── environnements/
│   └── vellane.yaml          le monde de référence
├── scenarios/N1, N2, N3/     un fichier par scénario
└── outils/
    ├── valider.py            validation des scénarios
    └── test_valider.py       tests du validateur
```

## Valider

Python 3 et PyYAML :

```sh
python3 outils/valider.py --resume
python3 outils/test_valider.py
```

## Ajouter un scénario

1. Partir du scénario existant du même niveau le plus proche.
2. Ne décrire dans `monde` que les écarts à l'environnement de référence.
3. Prendre les événements dans `catalogue/evenements.yaml` (en ajouter avec
   leur vrai ID, leur source et leur message français si besoin).
4. Répartir les points des indices, des étapes et de la communication selon
   le barème du niveau ; prévoir les indices attendus de chaque parcours
   inférieur et une note d'escalade sur 30.
5. Lancer `outils/valider.py` jusqu'à zéro erreur, puis faire relire le
   réalisme par un formateur.
