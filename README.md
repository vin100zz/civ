# Civilization — mode observateur

Clone de Civilization I : l'IA joue toutes les civilisations, vous regardez, de l'âge de pierre à la course vers Alpha du Centaure.
Le plan, l'architecture et les écarts par rapport au jeu d'origine sont dans [PLAN.md](PLAN.md).

## Lancer

Prérequis : Python 3.11 ou plus, avec `fastapi`, `uvicorn`, `websockets` et `pyyaml` (et `pytest`, `httpx` pour les tests).

```bash
python run.py
```

Puis ouvrir http://127.0.0.1:8005. Sous Windows, `start.bat` fait la même chose. `--port 9000` change le port.

Dans l'interface :

- **Play / Step / Speed** : lecture continue, tour par tour, vitesse. Espace = lecture/pause, N = un tour.
- **New game, Save, Saved games** : ouvrent la fenêtre « Game ». Nouvelle partie (la même graine redonne exactement la même partie), enregistrement sous un nom (dossier `saves/`) et rechargement ; une partie rechargée se poursuit comme l'originale.
- **Sur la carte** : « View as » pour voir le monde comme une civilisation (brouillard compris), les calques Territory / Grid / AI missions, le zoom et la mini-carte. Sous ces boutons : cases polluées, niveau de réchauffement, vaisseaux en vol.
- **Rail de droite** : World (classement des civilisations), Empire, City, Science, History, Chronicle. Science et History occupent toute la largeur ; Échap ou « Back to map » ramène à la carte.
- **Clic sur une ville** : production, citoyens, cases exploitées, pollution, et pourquoi l'IA a choisi cette production.
- **Clic sur une unité ou un territoire** : panneau Empire de la civilisation, avec son vaisseau spatial, ce que son IA veut, ses expéditions outre-mer et ses missions. Le calque « AI missions » les dessine sur la carte.
- **Science, History, Chronicle** : arbre des technologies, courbes par civilisation, journal des événements (cliquer une ligne la situe sur la carte).

Une partie se termine par la conquête du monde, par l'arrivée d'un vaisseau spatial sur Alpha du Centaure, ou au score en 2060.

## Simuler sans interface

```bash
python simulate.py --seeds 1 2 3 --turns 610 --events
```

Affiche un rapport par civilisation et signale les blocages de l'IA. `--csv fichier.csv` exporte les chiffres tour par tour, `--every 50` affiche un rapport intermédiaire.

```bash
python simulate.py --seed 7 --turns 300 --save saves/seed7.json
```

```bash
python simulate.py --load saves/seed7.json --turns 100
```

Une sauvegarde faite ici se charge aussi dans l'interface (et inversement).

## Tester

```bash
python -m pytest
```

Un des tests joue une partie entière (environ une minute). Pour ne lancer que les autres :

```bash
python -m pytest -m "not slow"
```

## Régler le jeu

Tout est dans `config/` :

| Fichier | Contenu |
|---|---|
| `game.yaml` | Carte, calendrier, règles de ville, combat, déplacements, huttes, barbares, pollution, nucléaire, vaisseau spatial, score, victoire |
| `terrains.yaml`, `units.yaml`, `buildings.yaml`, `wonders.yaml` | Données du jeu ; les effets des bâtiments et les capacités des unités sont déclarés ici |
| `technologies.yaml`, `governments.yaml`, `civilizations.yaml` | Arbre des techs, gouvernements, civilisations et personnalités |
| `ai.yaml` | Poids et seuils de l'IA |

Quelques réglages utiles dans `game.yaml` : `enabled_unit_domains` (retirer `sea` ou `air` pour une partie terrestre), `victory` (conquête, vaisseau), `calendar.max_turns` (fin au score), `pollution.enabled`.

Une erreur de config (clé inconnue, référence inexistante, sprite manquant) empêche le serveur de démarrer et dit où elle se trouve.
