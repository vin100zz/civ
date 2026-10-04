# Civilization

Clone de Civilization I, de l'âge de pierre à la course vers Alpha du Centaure. Deux façons de s'en servir : diriger une civilisation contre l'IA, ou regarder l'IA les jouer toutes.
Le plan, l'architecture et les écarts par rapport au jeu d'origine sont dans [PLAN.md](PLAN.md).

## Lancer

Prérequis : Python 3.11 ou plus, avec `fastapi`, `uvicorn`, `websockets` et `pyyaml` (et `pytest`, `httpx` pour les tests).

```bash
python run.py
```

Puis ouvrir http://127.0.0.1:8005. Sous Windows, `start.bat` fait la même chose. `--port 9000` change le port.

Au démarrage, le serveur lance une partie observée. Le bouton **New game** (ou **Game** en cours de partie jouée) ouvre la fenêtre où l'on choisit le mode.

## Jouer une civilisation

Dans la fenêtre « Game » : mode **Play a civilization**, votre civilisation (ou « Pick at random »), le nombre de civilisations, la difficulté et le monde. La difficulté ne change que votre civilisation (mécontentement, coût de la recherche) : l'IA ne reçoit ni bonus ni malus.

Vous ne voyez que ce que votre civilisation connaît : les terres explorées, les unités en vue, les villes étrangères telles que vous les avez vues la dernière fois.

- **Barre du haut** : trésor et gain par tour, recherche en cours, taux d'impôts, puis **End turn** (Entrée).
- **Fin du tour** : comme dans le jeu d'origine, le tour se termine de lui-même dès que la dernière unité a reçu son ordre, sauf si une décision attend encore (ville sans production, recherche à choisir, proposition de paix). Tant qu'une décision attend, **End turn** est grisé et son infobulle dit laquelle. Un tour sans unité à déplacer se termine par **End turn**. Finir le tour alors que des unités attendent demande une confirmation.
- **Panneau Turn** : les décisions à prendre avant de finir le tour (recherche, ville sans production, proposition de paix), les conseils, les alertes, les unités qui attendent un ordre, vos villes et ce qui s'est passé depuis votre dernier tour.
- **Unité active** (cerclée d'or, elle clignote sur la carte) : ses ordres possibles sont dans la barre du bas, avec leur raccourci et leur durée. Le jeu passe à l'unité suivante dès qu'elle a reçu un ordre ou n'a plus de mouvement.
- **Sur la carte** : clic sur une de vos unités pour la prendre en main (clics répétés pour parcourir une pile), clic sur une case voisine pour y aller ou attaquer, clic droit n'importe où pour y envoyer l'unité. Au survol d'un ennemi voisin, l'infobulle donne les forces en présence et vos chances.
- **Clic sur une de vos villes** : choix de la production, achat, clic sur une case pour y mettre un citoyen au travail ou l'en retirer, clic sur un spécialiste pour changer son métier (villes de taille 5 et plus), clic sur un bâtiment pour le vendre, interrupteur **Governor** pour laisser la ville choisir seule ce qu'elle construit.
- **Empire** : taux d'impôts, luxe et science, révolution, guerre et paix avec les civilisations rencontrées, recherche, lancement du vaisseau.
- **Science** : clic sur une technologie accessible pour la rechercher.

| Touche | Ordre |
|---|---|
| Flèches, pavé numérique | Déplacer l'unité (les diagonales au pavé numérique, ou Début, Fin, Page préc., Page suiv.) |
| B | Fonder une ville, ou rejoindre la ville où se trouve le colon |
| R, I, M, P | Route (puis voie ferrée), irrigation, mine, dépollution |
| F | Fortifier (forteresse pour un colon qui ne peut pas se fortifier davantage) |
| S, V | Sentinelle ; réveiller ou reprendre en main |
| G | Aller à : choisir la destination sur la carte (Échap pour annuler) |
| X, A | Explorer tout seul ; colons automatiques |
| H, U | Changer de ville d'attache ; embarquer ou débarquer dans un port |
| K, T | Caravane : aider la merveille ; ouvrir une route commerciale |
| W, Espace | Attendre (revenir à l'unité plus tard) ; ne rien faire ce tour |
| C | Centrer la carte sur l'unité |
| Maj + D | Dissoudre l'unité (à confirmer) |
| Entrée | Finir le tour |

La partie s'enregistre d'elle-même tous les cinq tours sous le nom `autosave`. Si votre civilisation est détruite, la partie continue et vous pouvez la regarder jusqu'au bout.

## Observer

Mode **Watch the AI play them all** de la fenêtre « Game ».

- **Play / Step / Speed** : lecture continue, tour par tour, vitesse. Espace = lecture/pause, N = un tour.
- **New game, Save, Saved games** : ouvrent la fenêtre « Game ». Nouvelle partie (la même graine avec les mêmes choix redonne exactement la même partie) avec le choix du monde : forme des terres (continents, petites, moyennes ou grandes îles, deux continents, continents et îles, continent unique avec ou sans lacs, ceinture de terre qui fait le tour du monde, mer intérieure), relief (plat, normal, montagneux) et climat (sec, normal, humide). Enregistrement sous un nom (dossier `saves/`) et rechargement ; une partie rechargée se poursuit comme l'originale.
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

```bash
python simulate.py --seed 7 --turns 300 --shape small_islands --relief 2 --climate 0
```

`--shape` prend une des formes de `map.shapes` dans `config/game.yaml` (on peut en ajouter) ; `--relief` et `--climate` vont de 0 à 2.

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
