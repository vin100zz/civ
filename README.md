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

- **Barre du haut** : gouvernement (en rouge avec les tours restants pendant une révolution), trésor et gain par tour (en ambre puis en rouge, marqué d'un panneau, quand le trésor va se vider), recherche en cours, taux d'impôts, puis **End turn** (Entrée).
- **Fin du tour** : comme dans le jeu d'origine, le tour se termine de lui-même dès que la dernière unité a reçu son ordre, sauf si une décision attend encore (ville sans production, recherche à choisir, proposition de paix). Tant qu'une décision attend, **End turn** est grisé et son infobulle dit laquelle. Un tour sans unité à déplacer se termine par **End turn**. Finir le tour alors que des unités attendent demande une confirmation.
- **Panneau Turn** : les décisions à prendre avant de finir le tour (recherche, ville sans production, proposition de paix), les conseils, les alertes, les unités qui attendent un ordre et vos villes (une pastille dorée « +N » après la production dit combien d'éléments attendent dans la file, son infobulle les nomme). Sans file, une unité terminée est reconstruite, comme dans le jeu d'origine, sauf les colons : la ville attend alors votre choix. Un gouverneur ne touche pas à la file et reprend la main quand elle est finie. Quand le trésor sera vide d'ici cinq tours, l'alerte dit quel bâtiment serait vendu, et **Balance** monte l'impôt juste assez (la science cède d'abord, puis le luxe tant qu'aucune ville ne se révolte) ; **Raise taxes** quand même l'impôt maximum ne suffit pas. Faute d'or, le trésor vend le bâtiment dont l'empire a le moins besoin : une Caserne dans une ville qui ne fait pas d'unités, des Remparts loin de l'ennemi, un Temple qui ne calme personne, avant ce qui nourrit, produit, rapporte ou maintient l'ordre. Les villes restent dans l'ordre de leur fondation ; chaque ligne donne la production en cours, son prix d'achat, les tours restants, puis la nourriture, la production et le commerce par tour et le nombre de mécontents. Une ville à corriger a son nom en rouge (désordre, famine, unités non entretenues) ou en ambre (le prochain habitant la mettrait en désordre, elle ne grandit plus, sa production est à l'arrêt), suivi d'une icône par problème ; le chiffre en cause porte une pastille de la même couleur.
- **Panneau Cities** : toutes vos villes d'un coup d'œil, un onglet par sujet (Food, Production, Trade, Gold, Science, Happiness, Military). Chaque onglet montre ses bâtiments en colonnes (carré plein = construit, gris qui se remplit = en construction, ambre = Aqueduct qui manque pour grandir, ★ = merveille), puis ce que la ville en tire : réserve et tours avant croissance ; boucliers, entretien des unités et risque de pollution ; partage du commerce et corruption ; impôts face à l'entretien des bâtiments ; science et part de la recherche ; un visage par habitant (compté au-delà de 17) ; unités dans la ville et unités au loin. Une colonne de bâtiment n'apparaît qu'une fois son avance connue. Un clic sur un titre de colonne trie la liste (décroissant, puis croissant, puis retour à l'ordre de fondation), un clic sur une ville ouvre sa fiche.
- **Panneau Wonders** : les merveilles dans l'ordre des règles. Une merveille construite porte un carré à la couleur de la civilisation qui la détient, avec sa ville et l'année de son achèvement ; elle est grisée avec ⊘ quand une avance l'a rendue obsolète. Comme dans Civ 1, une merveille dont la ville est détruite est perdue : elle n'agit plus et personne ne peut la reconstruire (carré gris, « destroyed » après le nom de la ville). Les autres disent où elles en sont : en construction dans une de vos villes (progression, tours restants), « You can build it » si vous connaissez son avance, « Needs … » sinon, « Too late » si elle est devenue obsolète avant que quiconque la bâtisse. L'infobulle donne l'effet, le coût, l'avance requise et, si la ville a changé de mains, la civilisation qui l'a construite. Un clic ouvre votre ville, ou montre la ville étrangère sur la carte. Les chantiers des autres civilisations restent secrets.
- **Unité active** (cerclée d'or, elle clignote sur la carte) : la barre du bas tient sur une ligne : nom, ville d'attache, attaque, défense et mouvements, puis ses ordres possibles en icônes, la touche du raccourci dans le coin (le nom de l'ordre et sa durée sont dans l'infobulle), puis les autres unités de la case avec une pastille pour ce qu'elles font (un clic en active une), Wait (W) et Skip turn (Espace). Le jeu passe à l'unité suivante dès qu'elle a reçu un ordre ou n'a plus de mouvement ; la caméra attend la fin de son dernier mouvement, ou l'issue de son combat, avant d'y aller.
- **Unités sur la carte** : une sentinelle est grisée et hachurée, une unité fortifiée a une bordure épaisse doublée d'un filet clair. Les unités d'une ville sont dessinées de la même façon dans son panneau.
- **Ville en désordre civil** : cerclée de rouge sur la carte, à tous les zooms, avec son nom sur une plaque rouge marquée d'un panneau d'avertissement.
- **Mouvements des autres** : au début de votre tour, les déplacements et les combats des autres civilisations qui se sont passés sous vos yeux sont rejoués un par un, la caméra les suit. Échap, Espace ou Entrée (ou le bouton **Skip**) passent directement à votre tour.
- **Sur la carte** : clic sur une de vos unités pour la prendre en main (clics répétés pour parcourir une pile), clic sur une case voisine pour y aller ou attaquer, clic droit n'importe où pour y envoyer l'unité. Au survol d'un ennemi voisin, l'infobulle donne les forces en présence et vos chances.
- **Clic sur une de vos villes** : choix de la production (un clic la construit tout de suite), file de production (Ctrl+clic ajoute un élément à la file, autant de fois qu'on veut d'unités, une fois pour un bâtiment ; la ligne **Then** sous la production en cours montre la file, chaque élément avec le nombre de tours avant qu'il soit fini, et sa croix le retire ; les boucliers en trop passent à l'élément suivant), achat, clic sur une case pour y mettre un citoyen au travail ou l'en retirer, clic sur un spécialiste pour changer son métier (villes de taille 5 et plus), clic sur un bâtiment pour le vendre, interrupteur **Governor** pour laisser la ville choisir seule ce qu'elle construit, clic sur une unité soutenue pour centrer la carte dessus. Sous chaque unité soutenue, ce qu'elle coûte à la ville à chaque tour, une icône par point comme dans le jeu d'origine : boucliers, nourriture des colons et, en République ou en Démocratie, citoyens mécontents pour une unité militaire hors de la ville ; sous l'Anarchie et le Despotisme, les premières unités, autant que la ville a d'habitants, n'ont pas de bouclier : le gouvernement les entretient. Le panneau montre des chiffres et des barres (surplus de nourriture, de boucliers et de commerce, ce qui part au soutien des unités ou à la corruption, risque de pollution) ; le détail est dans les infobulles : coût, entretien et effet d'un bâtiment ou d'une unité, ce que mangent les citoyens et les colons, ville d'attache d'une unité, origine de la pollution.
- **Empire** : taux d'impôts, luxe et science (avec le déficit et **Balance** quand le trésor perd de l'or), révolution, guerre et paix avec les civilisations rencontrées, recherche, lancement du vaisseau.
- **L'IA** se souvient des traités rompus : rompre la paix (surtout tout juste signée) rend la victime, et dans une moindre mesure ceux qui l'apprennent, plus rétifs à la paix pendant une soixantaine de tours. Une civilisation bien plus forte que les autres les voit se liguer contre elle. L'IA reprend en priorité les villes qu'on lui a prises, et répond à un débarquement : attaquants mis en chantier, défenseurs en surnombre qui frappent l'envahisseur quand leurs chances sont bonnes. Une civilisation en République ou en Démocratie reste tenue par son Sénat d'accepter la paix.
- **Science** : clic sur une technologie accessible pour la rechercher, clic sur une technologie plus lointaine pour en faire l'objectif (un drapeau dans la barre du haut) : à chaque découverte, la recherche passe d'elle-même à l'avance suivante sur le chemin, en pointillés dorés dans l'arbre. Le bandeau du panneau donne l'objectif, le nombre d'avances et de tours qu'il reste ; sa croix, ou un clic sur l'objectif, l'abandonne. L'objectif atteint, vous choisissez de nouveau.

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
- **Rail de droite** : World (classement des civilisations), Empire, City, Wonders, Science, History, Chronicle (en partie jouée, Turn et Cities en plus). Science et History occupent toute la largeur ; Échap ou « Back to map » ramène à la carte.
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
