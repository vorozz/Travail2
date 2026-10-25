#!/usr/bin/env python3
"""Validation des scénarios du simulateur.

Charge les catalogues et l'environnement, fusionne la section `monde` de
chaque scénario sur son environnement, puis vérifie :

- la structure et les références (actions, événements, comptes, machines,
  tickets, documents, équipes, indices, étapes) ;
- les règles du cahier des charges : au moins un piège partout ; au moins une
  fausse piste et une action dangereuse fortement pénalisée en N2/N3 ;
  pénalités dans les fourchettes du niveau ;
- les barèmes : points des indices, des étapes et de la communication égaux
  au barème du niveau, note d'escalade sur 30 ;
- l'accessibilité : chaque indice attendu d'un parcours inférieur est
  révélable avec les outils de ce parcours, chaque étape de résolution est
  réalisable au niveau du scénario.

Usage :
    python3 outils/valider.py              # tous les scénarios
    python3 outils/valider.py --resume     # + tableau récapitulatif Markdown
    python3 outils/valider.py scenarios/N2/N2-08-*.yaml

Code de sortie : 0 sans erreur, 1 sinon. Les avertissements ne bloquent pas.
"""

import argparse
import copy
import datetime
import glob
import os
import re
import sys

import yaml

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NIVEAUX = ['N1', 'N2', 'N3']
RANG = {n: i for i, n in enumerate(NIVEAUX)}

DUREE = re.compile(r'^[+-]?(?=\d)(\d+j)?(\d+h)?(\d+m)?(\d+s)?$')
CHAMP_MODELE = re.compile(r'\{(\w+)\}')
CHAMPS_AUTO = {'machine', 'machine_fqdn'}

OPERATEURS = {'egal', 'different', 'contient', 'ne_contient_pas', 'contient_un',
              'sup', 'inf', 'abs_inf', 'existe', 'egal_chemin'}
QUAND = {'periodique', 'a', 'apres_action'}
EFFETS = {'definir', 'ajouter', 'retirer', 'evenement', 'authentification',
          'ticket', 'message'}
CATEGORIES = {
    'N1': {'diagnostic'},
    'N2': {'diagnostic', 'elimination'},
    'N3': {'diagnostic', 'elimination', 'correlation'},
}
CLES_SCENARIO = ['schema', 'id', 'titre', 'niveau', 'temps_cible', 'environnement',
                 'horloge', 'resume', 'cause_racine', 'tickets', 'indices',
                 'pieges', 'resolution', 'communication', 'escalade', 'debrief']
COLLECTIONS_MACHINES = ('postes', 'serveurs', 'controleurs')
PRINCIPAUX_INTEGRES = {'Utilisateurs authentifiés', 'Utilisateurs du domaine',
                       'Admins du domaine', 'Tout le monde'}


def charger(chemin):
    with open(chemin, encoding='utf-8') as f:
        return yaml.safe_load(f)


def pieges_syntaxe(chemin):
    """Valeurs coupées par une virgule dans le style en ligne ({ } ou [ ]).

    En YAML, `{ ou: OU=Postes,OU=Lyon }` donne ou = 'OU=Postes' et une clé
    'OU=Lyon' sans valeur ; `[OU=Postes,OU=Lyon]` donne deux éléments. On
    signale les clés sans valeur et les virgules non suivies d'une espace.
    """
    with open(chemin, encoding='utf-8') as f:
        texte = f.read()
    problemes = []

    def parcourir(noeud):
        if isinstance(noeud, yaml.MappingNode):
            for k, v in noeud.value:
                if noeud.flow_style and isinstance(v, yaml.ScalarNode) and v.tag.endswith(':null') \
                        and v.value == '' and isinstance(k, yaml.ScalarNode) and k.style is None:
                    problemes.append(f'ligne {k.start_mark.line + 1} : clé sans valeur « {k.value} » '
                                     '(virgule dans une valeur en ligne ? la mettre entre guillemets)')
                parcourir(k)
                parcourir(v)
        elif isinstance(noeud, yaml.SequenceNode):
            for v in noeud.value:
                parcourir(v)
        if isinstance(noeud, (yaml.MappingNode, yaml.SequenceNode)) and noeud.flow_style:
            enfants = noeud.value if isinstance(noeud, yaml.SequenceNode) else [x for kv in noeud.value for x in kv]
            for v in enfants:
                if isinstance(v, yaml.ScalarNode) and v.style is None:
                    if v.value.count('(') != v.value.count(')') or v.value.count('«') != v.value.count('»'):
                        problemes.append(f'ligne {v.start_mark.line + 1} : « {v.value} » : parenthèse ou guillemet '
                                         'non refermé (valeur coupée par une virgule ?)')
                    fin = v.end_mark.index
                    if texte[fin:fin + 1] == ',' and texte[fin + 1:fin + 2] not in (' ', '\n', ''):
                        problemes.append(f'ligne {v.end_mark.line + 1} : « {v.value},{texte[fin + 1:fin + 12]}… » '
                                         'coupé par une virgule (mettre la valeur entre guillemets)')

    parcourir(yaml.compose(texte, Loader=yaml.SafeLoader))
    return problemes


def fusionner(base, ajout):
    """Fusion profonde : dictionnaires fusionnés, listes remplacées, None supprime."""
    if not isinstance(base, dict) or not isinstance(ajout, dict):
        return copy.deepcopy(ajout)
    res = copy.deepcopy(base)
    for k, v in ajout.items():
        if v is None:
            res.pop(k, None)
        elif isinstance(v, dict) and isinstance(res.get(k), dict):
            res[k] = fusionner(res[k], v)
        else:
            res[k] = copy.deepcopy(v)
    return res


def en_liste(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def segments(chemin):
    if isinstance(chemin, list):
        return [str(s) for s in chemin]
    return str(chemin).split('.')


def descendre(noeud, cle):
    if isinstance(noeud, dict):
        for k in noeud:
            if str(k) == cle:
                return True, noeud[k]
        return False, None
    if isinstance(noeud, list) and cle.isdigit() and int(cle) < len(noeud):
        return True, noeud[int(cle)]
    return False, None


class Validateur:
    def __init__(self):
        self.erreurs = []
        self.avertissements = []
        cat = os.path.join(RACINE, 'catalogue')
        self.niveaux = charger(os.path.join(cat, 'niveaux.yaml'))
        self.actions = charger(os.path.join(cat, 'actions.yaml'))['actions']
        self.cibles = charger(os.path.join(cat, 'actions.yaml'))['cibles']
        self.evenements = charger(os.path.join(cat, 'evenements.yaml'))['evenements']
        self.intentions = charger(os.path.join(cat, 'questions.yaml'))['intentions']
        self.environnements = {}
        for f in sorted(glob.glob(os.path.join(cat, '*.yaml'))) + sorted(glob.glob(os.path.join(RACINE, 'environnements', '*.yaml'))):
            self.contexte = os.path.relpath(f, RACINE)
            for p in pieges_syntaxe(f):
                self.err(p)
        for f in glob.glob(os.path.join(RACINE, 'environnements', '*.yaml')):
            env = charger(f)
            self.environnements[env['id']] = env
        self.contexte = 'catalogue'
        self.verifier_catalogues()
        for env in self.environnements.values():
            self.contexte = f"environnement {env['id']}"
            self.verifier_monde(env, env)

    # --- messages ----------------------------------------------------------
    def err(self, msg):
        self.erreurs.append(f'{self.contexte} : {msg}')

    def warn(self, msg):
        self.avertissements.append(f'{self.contexte} : {msg}')

    # --- outils ------------------------------------------------------------
    def duree(self, v, ou):
        if not isinstance(v, str) or not DUREE.match(v):
            self.err(f'{ou} : durée invalide {v!r} (format -3j4h12m30s)')
            return None
        signe = -1 if v.startswith('-') else 1
        total = 0
        for nb, unite in re.findall(r'(\d+)([jhms])', v):
            total += int(nb) * {'j': 86400, 'h': 3600, 'm': 60, 's': 1}[unite]
        return signe * total

    def date(self, v, ou):
        if isinstance(v, (datetime.date, datetime.datetime)):
            return
        if isinstance(v, str) and DUREE.match(v):
            return
        self.err(f'{ou} : date invalide {v!r} (date ISO ou durée relative)')

    def niveau_action(self, action, cible_type=None, portee=None):
        n = self.actions[action]['niveau']
        if isinstance(n, str):
            return RANG[n]
        if portee and portee in n:
            return RANG[n[portee]]
        if cible_type and cible_type in n:
            return RANG[n[cible_type]]
        return min(RANG[x] for x in n.values())

    @staticmethod
    def type_machine(monde, nom):
        for col, typ in (('postes', 'poste'), ('serveurs', 'serveur'), ('controleurs', 'dc')):
            if nom in (monde.get(col) or {}):
                return typ
        return None

    # --- catalogues --------------------------------------------------------
    def verifier_catalogues(self):
        for n, d in self.niveaux['niveaux'].items():
            if sum(d['bareme'].values()) != 100:
                self.err(f'barème {n} : total {sum(d["bareme"].values())} au lieu de 100')
            if set(d['bareme']) - {'temps'} != CATEGORIES[n] | {'resolution', 'communication'}:
                self.err(f'barème {n} : catégories inattendues {sorted(d["bareme"])}')
        if sum(self.niveaux['escalade']['bareme'].values()) != 100:
            self.err('barème d\'escalade : total différent de 100')
        for nom, a in self.actions.items():
            n = a.get('niveau')
            for x in (n.values() if isinstance(n, dict) else [n]):
                if x not in RANG:
                    self.err(f'action {nom} : niveau {x!r} inconnu')
            if a.get('type') not in ('lecture', 'modification', 'communication'):
                self.err(f'action {nom} : type {a.get("type")!r} inconnu')
            if a.get('cible') not in self.cibles:
                self.err(f'action {nom} : cible {a.get("cible")!r} absente de `cibles`')
        for nom, e in self.evenements.items():
            for champ in ('id', 'source', 'journal', 'niveau', 'modele'):
                if champ not in e:
                    self.err(f'événement {nom} : champ {champ} manquant')
            if not nom.endswith('/' + str(e.get('id'))):
                self.err(f'événement {nom} : la clé ne se termine pas par l\'ID {e.get("id")}')

    # --- monde ---------------------------------------------------------------
    def verifier_monde(self, monde, env):
        dom = monde['domaines']['vellane.local']
        ous = set(dom.get('ou', [])) | set(dom.get('conteneurs', []))
        groupes = set(monde.get('groupes') or {}) | PRINCIPAUX_INTEGRES
        utilisateurs = monde.get('utilisateurs') or {}
        sites = set(monde.get('sites') or {})
        socles = set(monde.get('socles') or {})
        machines = {}
        for col in COLLECTIONS_MACHINES:
            machines.update(monde.get(col) or {})
        for nom, u in utilisateurs.items():
            if u is None:
                continue
            if u.get('ou') and u['ou'] not in ous:
                self.err(f'utilisateur {nom} : OU {u["ou"]} inconnue')
            for g in u.get('groupes', []):
                if g not in groupes:
                    self.err(f'utilisateur {nom} : groupe {g} inconnu')
            if u.get('poste') and u['poste'] not in machines:
                self.err(f'utilisateur {nom} : poste {u["poste"]} inconnu')
            if u.get('manager') and u['manager'] not in utilisateurs:
                self.err(f'utilisateur {nom} : manager {u["manager"]} inconnu')
            if u.get('site') and u['site'] not in sites:
                self.err(f'utilisateur {nom} : site {u["site"]} inconnu')
        for col in COLLECTIONS_MACHINES:
            for nom, m in (monde.get(col) or {}).items():
                if m is None or m.get('externe'):
                    continue
                if m.get('ou') and m['ou'] not in ous:
                    self.err(f'{col} {nom} : OU {m["ou"]} inconnue')
                if m.get('site') and m['site'] not in sites:
                    self.err(f'{col} {nom} : site {m["site"]} inconnu')
                if m.get('socle') and m['socle'] not in socles:
                    self.err(f'{col} {nom} : socle {m["socle"]} inconnu')
                if m.get('utilisateur_principal') and m['utilisateur_principal'] not in utilisateurs:
                    self.err(f'{col} {nom} : utilisateur {m["utilisateur_principal"]} inconnu')
                for g in m.get('groupes', []):
                    if g not in groupes:
                        self.err(f'{col} {nom} : groupe {g} inconnu')
                for s in (m.get('sessions') or {}):
                    if s not in utilisateurs:
                        self.err(f'{col} {nom} : session d\'un compte inconnu {s}')
        for nom, g in (monde.get('groupes') or {}).items():
            for mb in g.get('membres', []) or []:
                if mb not in machines and mb not in utilisateurs:
                    self.err(f'groupe {nom} : membre {mb} inconnu')
        for nom, g in (monde.get('gpo') or {}).items():
            for lien in g.get('liens', []):
                if lien['cible'] not in ous and lien['cible'] != '':
                    self.err(f'GPO {nom} : lien vers une OU inconnue {lien["cible"]}')
            for liste in (g.get('filtrage') or {}).values():
                for p in liste:
                    if p not in groupes:
                        self.err(f'GPO {nom} : filtrage sur un groupe inconnu {p}')
            if g.get('filtre_wmi') and g['filtre_wmi'] not in (monde.get('filtres_wmi') or {}):
                self.err(f'GPO {nom} : filtre WMI inconnu {g["filtre_wmi"]}')
        for site, s in (monde.get('sites') or {}).items():
            for dc in s.get('controleurs', []):
                if dc not in (monde.get('controleurs') or {}):
                    self.err(f'site {site} : contrôleur {dc} inconnu')
        for dst, sources in ((monde.get('replication') or {}).get('connexions') or {}).items():
            for src in [dst] + list(sources or {}):
                if src not in (monde.get('controleurs') or {}):
                    self.err(f'réplication : contrôleur {src} inconnu')
        for hote, h in ((monde.get('virtualisation') or {}).get('hotes') or {}).items():
            for vm in h.get('vms', []):
                if vm not in machines:
                    self.err(f'hôte {hote} : VM {vm} inconnue')

    # --- références d'objets -----------------------------------------------
    def objets(self, monde, sc):
        """Ensemble des objets connus par type de cible."""
        machines = set()
        for col in COLLECTIONS_MACHINES:
            machines |= set(monde.get(col) or {})
        tickets = set(sc.get('tickets') or {})
        for bloc in ('pieges', 'actions_dangereuses'):
            for p in (sc.get(bloc) or {}).values():
                for e in p.get('effets', []) or []:
                    if 'ticket' in e:
                        tickets.add(e['ticket']['id'])
        for d in (sc.get('dynamiques') or {}).values():
            for e in d.get('effets', []) or []:
                if 'ticket' in e:
                    tickets.add(e['ticket']['id'])
        sites_web, files = set(), set()
        for nom, s in (monde.get('serveurs') or {}).items():
            for site in ((s.get('iis') or {}).get('sites') or {}):
                sites_web.add(f'{nom}/{site}')
            for f in (s.get('files_impression') or {}):
                files.add(f'{nom}\\{f}')
        dep = monde.get('deploiement') or {}
        return {
            'utilisateur': set(monde.get('utilisateurs') or {}),
            'groupe': set(monde.get('groupes') or {}),
            'ordinateur': machines,
            'machine': machines,
            'vm': machines,
            'gpo': set(monde.get('gpo') or {}),
            'zone_dns': set(((monde.get('dns') or {}).get('zones') or {})),
            'serveur_dhcp': set(monde.get('dhcp') or {}),
            'domaine': set(monde.get('domaines') or {}),
            'approbation': set(((monde.get('approbations') or {}).get('vellane.local') or {})),
            'deploiement': set(dep.get('deploiements') or {}),
            'application': set(dep.get('applications') or {}),
            'site_web': sites_web,
            'file_impression': files,
            'ticket': tickets,
            'equipe': set(monde.get('equipes') or {}),
            'document': set(monde.get('documents') or {}) | set(monde.get('changements') or {}),
        }

    def verifier_motif(self, motif, ou, monde, sc, objets, niveau_sc=None):
        """Vérifie un motif d'action ; renvoie le niveau minimal pour le réaliser."""
        if not isinstance(motif, dict):
            self.err(f'{ou} : motif invalide {motif!r}')
            return None
        if 'dynamique' in motif:
            if motif['dynamique'] not in (sc.get('dynamiques') or {}):
                self.err(f'{ou} : dynamique {motif["dynamique"]} inconnue')
            return RANG['N1']
        if 'action' not in motif:
            if 'si' in motif:
                self.verifier_conditions(motif['si'], ou, monde, sc)
                if 'apres' in motif:
                    self.verifier_apres(motif['apres'], ou, sc)
                return RANG['N1']
            self.err(f'{ou} : motif sans action ni condition')
            return None
        niveaux = []
        for a in en_liste(motif['action']):
            if a not in self.actions:
                self.err(f'{ou} : action {a} absente du catalogue')
                continue
            typ = self.actions[a]['cible']
            cibles = en_liste(motif.get('cible'))
            portee = (motif.get('parametres') or {}).get('portee')
            portees = en_liste(portee) if isinstance(portee, (str, list)) else [None]
            if cibles and typ not in ('aucune', 'annuaire'):
                for c in cibles:
                    connus = objets.get(typ)
                    if connus is not None and c not in connus and not (typ == 'ticket' and c in objets['ticket']):
                        # une action peut viser un ticket ou une machine d'un autre type déclaré
                        if not (len(en_liste(motif['action'])) > 1 and any(c in v for v in objets.values())):
                            self.err(f'{ou} : cible {c!r} inconnue pour {a} ({typ})')
                    tm = self.type_machine(monde, c) if typ in ('machine', 'ordinateur', 'vm') else None
                    for p in portees:
                        niveaux.append(self.niveau_action(a, tm, p))
            else:
                for p in portees:
                    niveaux.append(self.niveau_action(a, None, p))
        if 'si' in motif:
            self.verifier_conditions(motif['si'], ou, monde, sc)
        if 'apres' in motif:
            self.verifier_apres(motif['apres'], ou, sc)
        if 'occurrence' in motif and not isinstance(motif['occurrence'], int):
            self.err(f'{ou} : occurrence doit être un entier')
        inconnus = set(motif) - {'action', 'cible', 'parametres', 'si', 'apres', 'occurrence'}
        if inconnus:
            self.err(f'{ou} : clés inconnues dans le motif {sorted(inconnus)}')
        return min(niveaux) if niveaux else None

    def verifier_apres(self, apres, ou, sc):
        if apres.get('etape') not in ((sc.get('resolution') or {}).get('etapes') or {}):
            self.err(f'{ou} : `apres` vise une étape inconnue {apres.get("etape")}')
        self.duree(apres.get('delai', '0s'), ou + ' (apres.delai)')

    def verifier_chemin(self, chemin, ou, monde):
        segs = segments(chemin)
        racine = segs[0]
        if racine not in monde:
            self.err(f'{ou} : chemin {chemin!r} hors du monde (racine {racine!r})')
            return
        # profondeur jusqu'à l'objet visé : collection.objet, ou plus pour
        # les structures imbriquées (dns.zones.<zone>, dhcp.<serveur>.etendues.<étendue>...)
        profondeur = {'dns': 3, 'dhcp': 4, 'replication': 4, 'approbations': 3,
                      'deploiement': 3, 'virtualisation': 3}.get(racine, 2)
        noeud, i, faits = monde, 0, 0
        while faits < profondeur and i < len(segs):
            # Dans un chemin pointé, une clé peut contenir des points
            # (vellane.local, 10.20.10.0) : on prend la clé existante la plus longue.
            for j in range(len(segs), i, -1):
                ok, suivant = descendre(noeud, '.'.join(segs[i:j]))
                if ok:
                    noeud, i, faits = suivant, j, faits + 1
                    break
            else:
                self.err(f'{ou} : chemin {chemin!r} : {".".join(segs[:i + 1])} introuvable')
                return

    def verifier_conditions(self, conditions, ou, monde, sc):
        for c in en_liste(conditions):
            if not isinstance(c, dict):
                self.err(f'{ou} : condition invalide {c!r}')
                continue
            if 'indice' in c:
                if c['indice'] not in (sc.get('indices') or {}):
                    self.err(f'{ou} : indice {c["indice"]} inconnu')
                continue
            if 'etape' in c:
                if c['etape'] not in ((sc.get('resolution') or {}).get('etapes') or {}):
                    self.err(f'{ou} : étape {c["etape"]} inconnue')
                continue
            if 'chemin' not in c:
                self.err(f'{ou} : condition sans chemin {c!r}')
                continue
            ops = set(c) - {'chemin'}
            if len(ops) != 1 or not ops <= OPERATEURS:
                self.err(f'{ou} : opérateur invalide {sorted(ops)}')
            self.verifier_chemin(c['chemin'], ou, monde)
            if 'egal_chemin' in c:
                self.verifier_chemin(c['egal_chemin'], ou, monde)

    def verifier_effets(self, effets, ou, monde, sc, objets):
        for e in en_liste(effets):
            cles = set(e) & EFFETS
            if len(cles) != 1 or len(e) != 1:
                self.err(f'{ou} : effet invalide {e!r}')
                continue
            k = cles.pop()
            v = e[k]
            if k in ('definir', 'ajouter', 'retirer'):
                self.verifier_chemin(v['chemin'], ou, monde)
            elif k == 'evenement':
                if v.get('machine') not in objets['machine']:
                    self.err(f'{ou} : événement sur une machine inconnue {v.get("machine")}')
                self.verifier_evenement(v, ou, horodate=False)
            elif k == 'authentification':
                if v.get('compte') not in objets['utilisateur']:
                    self.err(f'{ou} : authentification d\'un compte inconnu {v.get("compte")}')
                if v.get('depuis') not in objets['machine']:
                    self.err(f'{ou} : authentification depuis une machine inconnue {v.get("depuis")}')
                if v.get('mdp') not in ('actuel', 'ancien', 'faux'):
                    self.err(f'{ou} : mdp doit valoir actuel, ancien ou faux')
            elif k == 'ticket':
                self.verifier_ticket(v['id'], v, ou, monde, objets)
            elif k == 'message':
                de = v.get('de')
                if de not in objets['utilisateur'] and de not in objets['equipe']:
                    self.err(f'{ou} : message d\'un émetteur inconnu {de}')

    def verifier_evenement(self, ev, ou, horodate=True):
        cle = ev.get('evenement')
        if cle not in self.evenements:
            self.err(f'{ou} : événement {cle} absent du catalogue')
            return
        if horodate:
            if 't' not in ev:
                self.err(f'{ou} : événement {cle} sans horodatage `t`')
            else:
                self.duree(ev['t'], f'{ou} ({cle}.t)')
        rep = ev.get('repeter')
        if rep:
            self.duree(rep.get('intervalle', '0s'), f'{ou} ({cle}.repeter.intervalle)')
            if 'jusqu_a' in rep:
                fin = self.duree(rep['jusqu_a'], f'{ou} ({cle}.repeter.jusqu_a)')
                debut = self.duree(ev['t'], f'{ou} ({cle}.t)') if 't' in ev else None
                if fin is not None and debut is not None and fin <= debut:
                    self.err(f'{ou} : {cle}.repeter.jusqu_a ({rep["jusqu_a"]}) avant le début ({ev["t"]})')
            if 'nombre' not in rep and 'jusqu_a' not in rep:
                self.err(f'{ou} : {cle}.repeter sans `nombre` ni `jusqu_a`')
        attendus = set(CHAMP_MODELE.findall(self.evenements[cle]['modele'])) - CHAMPS_AUTO
        fournis = set((ev.get('donnees') or {}).keys())
        if attendus - fournis:
            self.err(f'{ou} : {cle} sans les données {sorted(attendus - fournis)}')
        if fournis - attendus:
            self.warn(f'{ou} : {cle} données inutilisées {sorted(fournis - attendus)}')

    def verifier_ticket(self, num, t, ou, monde, objets):
        dem = t.get('demandeur')
        if dem not in objets['utilisateur'] and dem not in objets['equipe'] and dem != 'Supervision':
            self.err(f'{ou} ticket {num} : demandeur inconnu {dem}')
        if t.get('poste') and t['poste'] not in objets['machine']:
            self.err(f'{ou} ticket {num} : poste inconnu {t["poste"]}')
        if 'ouvert' in t:
            self.duree(t['ouvert'], f'{ou} ticket {num}.ouvert')
        for intention in (t.get('reponses') or {}):
            if intention != 'par_defaut' and intention not in self.intentions:
                self.err(f'{ou} ticket {num} : intention inconnue {intention}')

    # --- scénario ----------------------------------------------------------
    def verifier_scenario(self, chemin):
        self.contexte = os.path.relpath(chemin, RACINE)
        try:
            sc = charger(chemin)
        except yaml.YAMLError as e:
            self.err(f'YAML invalide : {e}')
            return None
        for p in pieges_syntaxe(chemin):
            self.err(p)
        for k in CLES_SCENARIO:
            if k not in sc:
                self.err(f'clé obligatoire manquante : {k}')
        if self.erreurs and self.erreurs[-1].startswith(self.contexte + ' : clé obligatoire'):
            return None
        niv = sc['niveau']
        if niv not in NIVEAUX:
            self.err(f'niveau {niv!r} inconnu')
            return None
        nom = os.path.basename(chemin)
        if not nom.startswith(sc['id'] + '-') or not sc['id'].startswith(niv + '-'):
            self.err(f'id {sc["id"]} incohérent avec le fichier {nom} ou le niveau {niv}')
        if os.path.basename(os.path.dirname(chemin)) != niv:
            self.err(f'le fichier doit être dans scenarios/{niv}/')
        cfg = self.niveaux['niveaux'][niv]
        t = self.duree(sc['temps_cible'], 'temps_cible')
        tmin = self.duree(cfg['temps_cible']['min'], 'niveaux')
        tmax = self.duree(cfg['temps_cible']['max'], 'niveaux')
        if t is not None and not (tmin <= t <= tmax):
            self.err(f'temps cible {sc["temps_cible"]} hors de la fourchette {niv} '
                     f'({cfg["temps_cible"]["min"]} à {cfg["temps_cible"]["max"]})')
        if not isinstance(sc['horloge'], datetime.datetime) or sc['horloge'].tzinfo is None:
            self.err('horloge : date et heure ISO avec fuseau attendues')
        env = self.environnements.get(sc['environnement'])
        if env is None:
            self.err(f'environnement {sc["environnement"]} inconnu')
            return None
        monde = fusionner(env, sc.get('monde') or {})
        self.verifier_monde(monde, env)
        objets = self.objets(monde, sc)
        for k in ('contacts',):
            for equipe in (sc.get(k) or {}):
                if equipe not in objets['equipe']:
                    self.err(f'contact vers une équipe inconnue {equipe}')

        # tickets
        if not sc['tickets']:
            self.err('aucun ticket')
        for num, tk in sc['tickets'].items():
            self.verifier_ticket(num, tk, 'tickets', monde, objets)
            for action, regles in (tk.get('retours') or {}).items():
                for r in regles:
                    if 'si' in r:
                        self.verifier_conditions(r['si'], f'ticket {num} retour {action}', monde, sc)
                    self.verifier_effets(r.get('effets', []), f'ticket {num} retour {action}', monde, sc, objets)
        if niv == 'N3' and len(sc['tickets']) < 2:
            self.err('un incident N3 doit réunir plusieurs tickets ou alertes')

        # événements des machines
        refs = {}
        for col in COLLECTIONS_MACHINES:
            for nom_m, m in (monde.get(col) or {}).items():
                for ev in (m or {}).get('journaux', []) or []:
                    self.verifier_evenement(ev, f'{col}.{nom_m}.journaux')
                    if 'ref' in ev:
                        if ev['ref'] in refs:
                            self.err(f'référence d\'événement en double : {ev["ref"]}')
                        refs[ev['ref']] = (col, nom_m)

        # dynamiques
        for nom_d, d in (sc.get('dynamiques') or {}).items():
            ou = f'dynamique {nom_d}'
            quand = d.get('quand') or {}
            if len(set(quand) & QUAND) != 1:
                self.err(f'{ou} : `quand` doit contenir periodique, a ou apres_action')
            if 'periodique' in quand:
                self.duree(quand['periodique'], ou)
            if 'a' in quand:
                self.duree(quand['a'], ou)
            if 'apres_action' in quand:
                self.verifier_motif(quand['apres_action'], ou, monde, sc, objets)
                self.duree(quand.get('delai', '0s'), ou)
            self.verifier_conditions(d.get('si', []), ou, monde, sc)
            self.verifier_effets(d.get('effets', []), ou, monde, sc, objets)

        # contacts
        for equipe, reponses in (sc.get('contacts') or {}).items():
            for r in reponses:
                ou = f'contact {equipe}'
                self.verifier_conditions(r.get('si', []), ou, monde, sc)
                for i in r.get('revele', []):
                    if i not in (sc.get('indices') or {}):
                        self.err(f'{ou} : révèle un indice inconnu {i}')
                self.verifier_effets(r.get('effets', []), ou, monde, sc, objets)

        # indices
        sommes = {c: 0 for c in CATEGORIES['N3']}
        niveau_indice = {}
        for nom_i, ind in sc['indices'].items():
            ou = f'indice {nom_i}'
            cat = ind.get('categorie')
            if cat not in CATEGORIES[niv]:
                self.err(f'{ou} : catégorie {cat!r} non prévue en {niv}')
            else:
                sommes[cat] += ind.get('points', 0)
            if not isinstance(ind.get('points'), int) or ind['points'] < 0:
                self.err(f'{ou} : points entiers positifs attendus')
            if not ind.get('revele_par'):
                self.err(f'{ou} : aucun moyen de le révéler')
            meilleurs = []
            for r in ind.get('revele_par', []):
                if 'evenement' in r:
                    if r['evenement'] not in refs:
                        self.err(f'{ou} : référence d\'événement inconnue {r["evenement"]}')
                    else:
                        col, m = refs[r['evenement']]
                        typ = {'postes': 'poste', 'serveurs': 'serveur', 'controleurs': 'dc'}[col]
                        meilleurs.append(self.niveau_action('machine.journal.lire', typ))
                elif 'question' in r:
                    if r['question'] not in self.intentions:
                        self.err(f'{ou} : intention inconnue {r["question"]}')
                    tk = r.get('ticket')
                    if tk not in sc['tickets']:
                        self.err(f'{ou} : ticket inconnu {tk}')
                    elif r['question'] not in (sc['tickets'][tk].get('reponses') or {}):
                        self.err(f'{ou} : le ticket {tk} ne répond pas à « {r["question"]} »')
                    meilleurs.append(RANG['N1'])
                elif 'contact' in r:
                    if r['contact'] not in (sc.get('contacts') or {}):
                        self.err(f'{ou} : pas de réponse prévue pour le contact {r["contact"]}')
                    if 'si' in r:
                        self.verifier_conditions(r['si'], ou, monde, sc)
                    meilleurs.append(RANG['N1'])
                else:
                    n = self.verifier_motif(r, ou, monde, sc, objets)
                    if n is not None:
                        if r.get('action') == 'document.consulter':
                            doc = (monde.get('documents') or {}).get(r.get('cible')) or {}
                            n = max(n, RANG.get(doc.get('niveau', 'N1'), 0))
                        meilleurs.append(n)
            if meilleurs:
                niveau_indice[nom_i] = min(meilleurs)

        bareme = cfg['bareme']
        for cat in CATEGORIES[niv]:
            if sommes[cat] != bareme[cat]:
                self.err(f'indices {cat} : {sommes[cat]} points au lieu de {bareme[cat]}')

        # fausses pistes
        fp = sc.get('fausses_pistes') or {}
        if niv != 'N1' and not fp:
            self.err(f'un scénario {niv} doit avoir au moins une fausse piste')
        for nom_f, f in fp.items():
            ou = f'fausse piste {nom_f}'
            if not f.get('eliminee_par'):
                self.err(f'{ou} : `eliminee_par` vide')
            for i in f.get('eliminee_par', []):
                if i not in sc['indices']:
                    self.err(f'{ou} : indice inconnu {i}')
                elif niv != 'N1' and sc['indices'][i].get('categorie') != 'elimination':
                    self.err(f'{ou} : l\'indice {i} devrait être de catégorie elimination')
            for m in f.get('actions_inutiles', []) or []:
                self.verifier_motif(m, ou, monde, sc, objets)

        # pièges et actions dangereuses
        pen = cfg['penalites']
        if not sc.get('pieges'):
            self.err('au moins un piège est obligatoire')
        for nom_p, p in (sc.get('pieges') or {}).items():
            ou = f'piège {nom_p}'
            v = p.get('penalite')
            if not isinstance(v, int) or not (pen['piege']['max'] <= v <= pen['piege']['min']):
                self.err(f'{ou} : pénalité {v} hors fourchette {niv} '
                         f'({pen["piege"]["min"]} à {pen["piege"]["max"]})')
            for m in en_liste(p.get('declencheur')):
                self.verifier_motif(m, ou, monde, sc, objets)
            self.verifier_effets(p.get('effets', []), ou, monde, sc, objets)
            if not p.get('retour'):
                self.err(f'{ou} : `retour` (explication au débriefing) manquant')
        ad = sc.get('actions_dangereuses') or {}
        if niv != 'N1' and not ad:
            self.err(f'un scénario {niv} doit avoir au moins une action dangereuse')
        accessibles = 0
        for nom_a, a in ad.items():
            ou = f'action dangereuse {nom_a}'
            v = a.get('penalite')
            if not isinstance(v, int) or not (pen['action_dangereuse']['max'] <= v <= pen['action_dangereuse']['min']):
                self.err(f'{ou} : pénalité {v} hors fourchette {niv} '
                         f'({pen["action_dangereuse"]["min"]} à {pen["action_dangereuse"]["max"]})')
            if a.get('gravite') not in ('majeure', 'critique'):
                self.err(f'{ou} : gravité majeure ou critique attendue')
            niveaux_a = [self.verifier_motif(m, ou, monde, sc, objets) for m in en_liste(a.get('declencheur'))]
            if any(n is not None and n <= RANG[niv] for n in niveaux_a):
                accessibles += 1
            self.verifier_effets(a.get('effets', []), ou, monde, sc, objets)
            if not a.get('retour'):
                self.err(f'{ou} : `retour` manquant')
        if niv != 'N1' and ad and not accessibles:
            self.err(f'aucune action dangereuse n\'est réalisable avec les outils {niv}')

        # résolution
        res = sc['resolution']
        self.verifier_conditions(res.get('conditions', []), 'resolution.conditions', monde, sc)
        total = 0
        for nom_e, e in (res.get('etapes') or {}).items():
            ou = f'étape {nom_e}'
            total += e.get('points', 0)
            niveaux_e = [self.verifier_motif(m, ou, monde, sc, objets) for m in e.get('valide_par', [])]
            if not any(n is not None and n <= RANG[niv] for n in niveaux_e):
                self.err(f'{ou} : aucune façon de la valider avec les outils {niv}')
        if total != bareme['resolution']:
            self.err(f'résolution : {total} points au lieu de {bareme["resolution"]}')

        # communication
        com = sc['communication']
        total = 0
        clo = com.get('cloture') or {}
        if clo:
            if clo.get('ticket') not in sc['tickets']:
                self.err(f'communication : ticket de clôture inconnu {clo.get("ticket")}')
            for nom_c, el in (clo.get('elements') or {}).items():
                total += el.get('points', 0)
                if not el.get('mots_cles'):
                    self.err(f'communication {nom_c} : mots-clés manquants')
        for nom_c, act in (com.get('actions') or {}).items():
            total += act.get('points', 0)
            for m in act.get('valide_par', []):
                self.verifier_motif(m, f'communication {nom_c}', monde, sc, objets)
        if total != bareme['communication']:
            self.err(f'communication : {total} points au lieu de {bareme["communication"]}')

        # escalade
        esc = sc['escalade'] or {}
        for eq in esc.get('equipes', []):
            if eq not in objets['equipe']:
                self.err(f'escalade : équipe inconnue {eq}')
        inferieurs = NIVEAUX[:RANG[niv]]
        if niv == 'N1':
            if esc.get('equipes') or esc.get('note'):
                self.err('un scénario N1 ne prévoit pas d\'escalade (elle est injustifiée)')
        else:
            if not esc.get('equipes'):
                self.err('escalade : équipes compétentes à indiquer')
            self.duree(esc.get('delai_cible'), 'escalade.delai_cible')
            attendus = esc.get('indices_attendus') or {}
            for p in inferieurs:
                if p not in attendus:
                    self.err(f'escalade : indices attendus du parcours {p} manquants')
                for i in attendus.get(p, []):
                    if i not in sc['indices']:
                        self.err(f'escalade {p} : indice inconnu {i}')
                    elif niveau_indice.get(i, 99) > RANG[p]:
                        self.err(f'escalade {p} : l\'indice {i} n\'est pas révélable avec les outils {p}')
            note = sum(el.get('points', 0) for el in ((esc.get('note') or {}).get('elements') or {}).values())
            if note != self.niveaux['escalade']['bareme']['note_transmission']:
                self.err(f'note de transmission : {note} points au lieu de '
                         f'{self.niveaux["escalade"]["bareme"]["note_transmission"]}')
        if not sc.get('debrief'):
            self.err('débriefing vide')
        return sc

    # --- résumé ------------------------------------------------------------
    @staticmethod
    def ligne(sc):
        ad = sc.get('actions_dangereuses') or {}
        pire = min([a['penalite'] for a in ad.values()], default=0)
        return (f"| {sc['id']} | {sc['titre']} | {sc['temps_cible']} | {len(sc['tickets'])} | "
                f"{len(sc['pieges'])} | {len(sc.get('fausses_pistes') or {})} | {len(ad)} | "
                f"{pire if ad else '-'} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('fichiers', nargs='*', help='scénarios à valider (tous par défaut)')
    ap.add_argument('--resume', action='store_true', help='afficher le tableau récapitulatif')
    args = ap.parse_args()
    v = Validateur()
    fichiers = args.fichiers or sorted(glob.glob(os.path.join(RACINE, 'scenarios', 'N*', '*.yaml')))
    scenarios = [s for s in (v.verifier_scenario(os.path.abspath(f)) for f in fichiers) if s]
    for a in v.avertissements:
        print('avertissement :', a)
    for e in v.erreurs:
        print('ERREUR :', e)
    if args.resume:
        print('\n| Id | Titre | Temps cible | Tickets | Pièges | Fausses pistes | Actions dangereuses | Pire pénalité |')
        print('|---|---|---|---|---|---|---|---|')
        for sc in scenarios:
            print(v.ligne(sc))
    print(f'\n{len(fichiers)} scénario(s), {len(v.erreurs)} erreur(s), {len(v.avertissements)} avertissement(s)')
    return 1 if v.erreurs else 0


if __name__ == '__main__':
    sys.exit(main())
