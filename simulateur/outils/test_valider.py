#!/usr/bin/env python3
"""Tests du validateur : chaque test abîme une copie des scénarios et vérifie
que l'erreur attendue est signalée.

Usage : python3 outils/test_valider.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def valider(dossier):
    r = subprocess.run([sys.executable, os.path.join(dossier, 'outils', 'valider.py')],
                       capture_output=True, text=True)
    return r.returncode, r.stdout


class TestValidateur(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.copie = os.path.join(self.tmp, 'simulateur')
        shutil.copytree(RACINE, self.copie, ignore=shutil.ignore_patterns('__pycache__'))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def lire(self, relatif):
        with open(os.path.join(self.copie, relatif), encoding='utf-8') as f:
            return f.read()

    def ecrire(self, relatif, texte):
        with open(os.path.join(self.copie, relatif), 'w', encoding='utf-8') as f:
            f.write(texte)

    def modifier(self, relatif, avant, apres):
        texte = self.lire(relatif)
        self.assertIn(avant, texte, f'motif introuvable dans {relatif}')
        self.ecrire(relatif, texte.replace(avant, apres, 1))

    def attendre(self, fragment):
        code, sortie = valider(self.copie)
        self.assertEqual(code, 1, sortie)
        self.assertIn(fragment, sortie)

    def test_reference_valide(self):
        code, sortie = valider(self.copie)
        self.assertEqual(code, 0, sortie)

    def test_points_des_indices(self):
        self.modifier('scenarios/N1/N1-01-compte-verrouille.yaml',
                      'Léa Bernard, Achats, Paris), pas lbernard2 (Louis Bernard, Logistique, Lyon).\n    categorie: diagnostic\n    points: 8',
                      'Léa Bernard, Achats, Paris), pas lbernard2 (Louis Bernard, Logistique, Lyon).\n    categorie: diagnostic\n    points: 9')
        self.attendre('indices diagnostic : 31 points au lieu de 30')

    def test_piege_obligatoire(self):
        relatif = 'scenarios/N1/N1-01-compte-verrouille.yaml'
        texte = self.lire(relatif)
        debut, fin = texte.index('\npieges:'), texte.index('\nactions_dangereuses:')
        self.ecrire(relatif, texte[:debut] + '\npieges: {}' + texte[fin:])
        self.attendre('au moins un piège est obligatoire')

    def test_fausse_piste_obligatoire_en_n2(self):
        relatif = 'scenarios/N2/N2-08-verrouillage-en-boucle.yaml'
        texte = self.lire(relatif)
        debut, fin = texte.index('\nfausses_pistes:'), texte.index('\npieges:')
        self.ecrire(relatif, texte[:debut] + '\nfausses_pistes: {}' + texte[fin:])
        self.attendre('doit avoir au moins une fausse piste')

    def test_action_dangereuse_peu_penalisee(self):
        self.modifier('scenarios/N2/N2-08-verrouillage-en-boucle.yaml',
                      'penalite: -40\n    gravite: critique', 'penalite: -10\n    gravite: critique')
        self.attendre('pénalité -10 hors fourchette N2')

    def test_indice_inaccessible_au_n1(self):
        self.modifier('scenarios/N2/N2-06-gpo-non-appliquee.yaml',
                      'N1: [mauvaise_ou, pas_dans_groupe, compte_ok]',
                      'N1: [mauvaise_ou, pas_dans_groupe, compte_ok, gpo_absente]')
        self.attendre("l'indice gpo_absente n'est pas révélable avec les outils N1")

    def test_evenement_inconnu(self):
        self.modifier('scenarios/N1/N1-01-compte-verrouille.yaml',
                      'evenement: securite/4740\n          ref: verrouillage_pdc',
                      'evenement: securite/9999\n          ref: verrouillage_pdc')
        self.attendre('événement securite/9999 absent du catalogue')

    def test_donnees_d_evenement_manquantes(self):
        self.modifier('scenarios/N1/N1-01-compte-verrouille.yaml',
                      'donnees: { compte: lbernard, appelant: PC-PAR-0187 }\n    DC-PAR-01:',
                      'donnees: { compte: lbernard }\n    DC-PAR-01:')
        self.attendre("sans les données ['appelant']")

    def test_action_inconnue(self):
        self.modifier('scenarios/N2/N2-09-dns-obsolete.yaml',
                      'action: dns.enregistrement.lire', 'action: dns.enregistrement.lir')
        self.attendre('action dns.enregistrement.lir absente du catalogue')

    def test_dn_coupe_par_une_virgule(self):
        self.modifier('scenarios/N2/N2-06-gpo-non-appliquee.yaml',
                      "si: [{ chemin: postes.PC-PAR-0298.ou, egal: 'OU=Postes,OU=Lyon' }]",
                      'si: [{ chemin: postes.PC-PAR-0298.ou, egal: OU=Postes,OU=Lyon }]')
        self.attendre('clé sans valeur « OU=Lyon »')

    def test_note_de_transmission(self):
        self.modifier('scenarios/N2/N2-07-relation-approbation-poste.yaml',
                      "mots_cles: [PC-PAR-0175]\n        points: 6", "mots_cles: [PC-PAR-0175]\n        points: 7")
        self.attendre('note de transmission : 31 points au lieu de 30')

    def test_etape_irrealisable(self):
        self.modifier('scenarios/N2/N2-11-dhcp-sature.yaml',
                      '        - action: dhcp.bail.supprimer\n          cible: SRV-DHCP-01\n          parametres: { etendue: 10.20.10.0, tous: [false, ~] }',
                      '        - action: dns.nettoyage.lancer\n          cible: DC-PAR-01')
        self.attendre("étape baux_liberes : aucune façon de la valider avec les outils N2")

    def test_reference_d_indice_inconnue(self):
        self.modifier('scenarios/N3/N3-13-vague-tickets-site.yaml',
                      'eliminee_par: [gpo_hors_cause]', 'eliminee_par: [gpo_hors_sujet]')
        self.attendre('fausse piste gpo_d_hier : indice inconnu gpo_hors_sujet')


if __name__ == '__main__':
    unittest.main(verbosity=2)
