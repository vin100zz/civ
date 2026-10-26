# Civilization

Clone de Civilization I, de l'âge de pierre à la course vers Alpha du Centaure. Deux façons de s'en servir : diriger une civilisation contre l'IA, ou regarder l'IA les jouer toutes.
Le plan, l'architecture et les écarts par rapport au jeu d'origine sont dans [PLAN.md](PLAN.md).

## Lancer

Prérequis : Python 3.11 ou plus, avec `fastapi`, `uvicorn`, `websockets` et `pyyaml` (et `pytest`, `httpx` pour les tests).

```bash
python run.py
```

Puis ouvrir http://127.0.0.1:8005. `--port 9000` change le port. `--resume` reprend la dernière partie sauvegardée (la plus récente du dossier `saves/`, sauvegarde automatique comprise) ; sous Windows, `start.bat` lance le serveur de cette façon. Lancer une fois `shortcut.bat` crée sur le Bureau un raccourci « Civ », avec l'icône du temple (`resources/civ.ico`), qui s'épingle à la barre des tâches (clic droit, « Épingler à la barre des tâches »). Il lance `launcher.pyw` sans console : la dernière partie reprend dans sa propre fenêtre Chrome (Edge si Chrome est absent), à l'icône du jeu, et le serveur s'arrête quand on la ferme. Le journal du serveur est dans `launcher.log`. Relancer `shortcut.bat` pour mettre à jour un raccourci créé auparavant.

Au démarrage, le serveur lance une partie observée, ou, avec `--resume`, recharge la dernière sauvegarde (une partie neuve s'il n'y en a pas). Le bouton **New game** (ou **Game** en cours de partie jouée) ouvre la fenêtre où l'on choisit le mode.

## Jouer une civilisation

Dans la fenêtre « Game » : mode **Play a civilization**, votre civilisation (ou « Pick at random »), le nombre de civilisations, la difficulté et le monde. La difficulté ne change que votre civilisation (mécontentement, coût de la recherche) : l'IA ne reçoit ni bonus ni malus.

Vous ne voyez que ce que votre civilisation connaît : les terres explorées, les unités en vue, les villes étrangères telles que vous les avez vues la dernière fois.

- **Barre du haut** : gouvernement (en rouge avec les tours restants pendant une révolution), trésor et gain par tour (en ambre puis en rouge, marqué d'un panneau, quand le trésor va se vider), recherche en cours, taux d'impôts, l'état de la planète (voir Observer), puis **End turn** (Entrée). À gauche, après le nom du jeu : le dossier « Game » (nouvelle partie, sauvegarde, chargement) et la roue dentée des calques de la carte (Territory, Grid). Le survol d'un bouton donne sa fonction.
- **Fin du tour** : comme dans le jeu d'origine, le tour se termine de lui-même dès que la dernière unité a reçu son ordre, sauf si une décision attend encore (ville sans production, recherche à choisir, proposition de paix). Tant qu'une décision attend, **End turn** est grisé et son infobulle dit laquelle. Un tour sans unité à déplacer se termine par **End turn**. Finir le tour alors que des unités attendent demande une confirmation.
- **Grandes nouvelles** : une merveille achevée, une civilisation détruite, une de vos villes perdue, une guerre qu'on vous déclare, une frappe nucléaire, le réchauffement, un vaisseau lancé ou perdu s'affichent dans un bandeau en haut de la carte, à la couleur de la civilisation concernée. Le bandeau reste d'un tour à l'autre jusqu'à ce que vous le fermiez ; les flèches passent d'une nouvelle à l'autre, **Show** amène la carte à l'endroit.
- **Panneau Turn** : les décisions à prendre avant de finir le tour (recherche, ville sans production, proposition de paix), les conseils, les alertes, ce qui s'est passé depuis votre dernier tour (**Since your last turn** : combats, villes prises, huttes, contacts, bâtiments vendus…, un clic montre l'endroit), les unités qui attendent un ordre (une sentinelle réveillée ou un « aller à » bloqué dit pourquoi) et vos villes (une pastille dorée « +N » après la production dit combien d'éléments attendent dans la file, son infobulle les nomme). Sans file, une unité terminée est reconstruite, comme dans le jeu d'origine, sauf les colons : la ville attend alors votre choix. Un gouverneur ne touche pas à la file et reprend la main quand elle est finie. Quand le trésor sera vide d'ici cinq tours, l'alerte dit quel bâtiment serait vendu, et **Balance** monte l'impôt juste assez (la science cède d'abord, puis le luxe tant qu'aucune ville ne se révolte) ; **Raise taxes** quand même l'impôt maximum ne suffit pas. Faute d'or, le trésor vend le bâtiment dont l'empire a le moins besoin : une Caserne dans une ville qui ne fait pas d'unités, des Remparts loin de l'ennemi, un Temple qui ne calme personne, avant ce qui nourrit, produit, rapporte ou maintient l'ordre. Les villes restent dans l'ordre de leur fondation ; chaque ligne donne la production en cours, son prix d'achat, les tours restants, puis la nourriture, la production et le commerce par tour et le nombre de mécontents. Une ville à corriger a son nom en rouge (désordre, famine, unités non entretenues) ou en ambre (le prochain habitant la mettrait en désordre, elle ne grandit plus, sa production est à l'arrêt), suivi d'une icône par problème ; le chiffre en cause porte une pastille de la même couleur.
- **Panneau Cities** : toutes vos villes d'un coup d'œil, un onglet par sujet (Food, Production, Trade, Gold, Science, Happiness, Culture avec les règles Renaissance, Military). Chaque onglet montre ses bâtiments en colonnes (carré plein = construit, gris qui se remplit = en construction, ambre = Aqueduct qui manque pour grandir, ★ = merveille), puis ce que la ville en tire : réserve et tours avant croissance ; boucliers, entretien des unités et risque de pollution ; partage du commerce et corruption ; impôts face à l'entretien des bâtiments ; science et part de la recherche ; un visage par habitant (compté au-delà de 17) ; culture par tour, tours avant la prochaine case et cases du rayon de la ville dans votre territoire ; unités dans la ville et unités au loin. Une colonne de bâtiment n'apparaît qu'une fois son avance connue. Un clic sur un titre de colonne trie la liste (décroissant, puis croissant, puis retour à l'ordre de fondation), un clic sur une ville ouvre sa fiche.
- **Panneau Wonders** : les merveilles dans l'ordre des règles. Une merveille construite porte un carré à la couleur de la civilisation qui la détient, avec sa ville et l'année de son achèvement ; elle est grisée avec ⊘ quand une avance l'a rendue obsolète. Comme dans Civ 1, une merveille dont la ville est détruite est perdue : elle n'agit plus et personne ne peut la reconstruire (carré gris, « destroyed » après le nom de la ville). Les autres disent où elles en sont : en construction dans une de vos villes (progression, tours restants), « You can build it » si vous connaissez son avance, « Needs … » sinon, « Too late » si elle est devenue obsolète avant que quiconque la bâtisse. L'infobulle donne l'effet, le coût, l'avance requise et, si la ville a changé de mains, la civilisation qui l'a construite. Un clic ouvre votre ville, ou montre la ville étrangère sur la carte. Les chantiers des autres civilisations restent secrets.
- **Panneau Space** : la course à l'espace. En tête, qui atterrit le premier sur Alpha du Centaure et dans combien de tours, et si quelqu'un peut encore le rattraper (un vaisseau qui partirait maintenant vole 6 ans au mieux) ; sinon, la capitale à prendre ou à défendre, puisque le vaisseau est perdu avec elle. Une frise des années montre les vols en cours (trait plein) et les départs prévus (pointillés) quand toutes les pièces qui manquent sont en chantier. Puis une ligne par civilisation, de la plus proche de l'arrivée à la plus lointaine : une jauge par type de pièce (Structural, Component, Module), une case par pièce possible, pleine une fois construite, qui se remplit en chantier, le trait doré marquant le minimum pour décoller ; en dessous, les villes qui construisent une pièce (un clic ouvre la ville), la date de départ et d'arrivée prévue, ou le bouton **Launch** quand votre vaisseau est prêt. Les pièces construites des civilisations rencontrées sont publiques, leurs chantiers restent secrets. Sur le rail, une pastille donne les tours avant le premier atterrissage, en rouge quand c'est un rival. En bas, le rappel des règles (coût, avance, nombre de pièces, durée du vol).
- **Unité active** (cerclée d'or, elle clignote sur la carte) : la barre du bas tient sur une ligne : nom, ville d'attache, attaque, défense et mouvements, puis ses ordres possibles en icônes, la touche du raccourci dans le coin (le nom de l'ordre et sa durée sont dans l'infobulle), puis les autres unités de la case avec une pastille pour ce qu'elles font (un clic en active une), Wait (W) et Skip turn (Espace). Le jeu passe à l'unité suivante dès qu'elle a reçu un ordre ou n'a plus de mouvement ; la caméra attend la fin de son dernier mouvement, ou l'issue de son combat, avant d'y aller.
- **Unités sur la carte** : une sentinelle est grisée et hachurée, une unité fortifiée a une bordure épaisse doublée d'un filet clair. Les unités d'une ville sont dessinées de la même façon dans son panneau.
- **Ville en désordre civil** : cerclée de rouge sur la carte, à tous les zooms, avec son nom sur une plaque rouge marquée d'un panneau d'avertissement.
- **Mouvements des autres** : au début de votre tour, les déplacements et les combats des autres civilisations qui se sont passés sous vos yeux sont rejoués un par un, la caméra les suit. Échap, Espace ou Entrée (ou le bouton **Skip**) passent directement à votre tour.
- **Sur la carte** : clic sur une de vos unités pour la prendre en main (clics répétés pour parcourir une pile), clic sur une case voisine pour y aller ou attaquer, clic droit n'importe où pour y envoyer l'unité. Au survol d'un ennemi voisin, l'infobulle donne les forces en présence et vos chances.
- **Culture et frontières** (règles Renaissance seulement, en violet dans l'interface) : une ville neuve ne tient que les 8 cases qui l'entourent. Sa culture, accumulée tour après tour, lui gagne une à une les 12 cases de son anneau extérieur, la meilleure case libre d'abord, puis, au-delà des cases qu'elle travaille, les 4 coins de son carré 5 × 5 et un troisième anneau de 20 cases, la plus proche d'abord, chacune voisine d'une case qu'elle tient déjà, jamais une case que pourrait travailler une ville d'une autre civilisation. La n-ième case demande n × 5 de culture de plus que la précédente (390 pour l'anneau extérieur, 3 330 pour les 36). Ses citoyens ne travaillent que les cases du territoire de leur civilisation, et personne d'autre ne peut y fonder de ville. Chaque ville fait 1 de culture par tour ; le Temple ajoute 1, le Théâtre (Drama) 3, le Musée (Humanism, sur un Théâtre) 2 puis +50 % ; chaque merveille donne 3 à sa ville, le Parthénon (Drama) 2 à chaque ville, le Louvre (Humanism) agit comme un Musée dans chaque ville. Une ville en désordre ne fait pas de culture. Une case tenue par une autre civilisation reste à elle (pas de vol de cases), et l'on peut toujours entrer sur le territoire des autres. Le score compte 1 point par 200 de culture des villes de la civilisation. La fiche de la ville montre sa culture (ligne Culture) et grise les cases hors des frontières, en pointillés violets quand la culture peut encore les gagner.
- **Pillage** : une unité militaire terrestre détruit un aménagement de sa case, au prix du reste de son tour, dans cet ordre : irrigation, mine, voie ferrée, forteresse, route. Pas dans une ville, ni sur le territoire d'une civilisation avec qui l'on n'est pas en guerre ; sur le sien, oui (terre brûlée). L'IA pille irrigation, mines et voies ferrées autour de la ville qu'elle assiège tant que ses chances d'attaque sont trop faibles.
- **Clic sur une de vos villes** : choix de la production (un clic la construit tout de suite), file de production (Ctrl+clic ajoute un élément à la file, autant de fois qu'on veut d'unités, une fois pour un bâtiment ; la ligne **Then** sous la production en cours montre la file, chaque élément avec le nombre de tours avant qu'il soit fini, et sa croix le retire ; les boucliers en trop passent à l'élément suivant), achat, clic sur une case pour y mettre un citoyen au travail ou l'en retirer, clic sur un spécialiste pour changer son métier (villes de taille 5 et plus), clic sur un bâtiment pour le vendre, interrupteur **Governor** pour laisser la ville choisir seule ce qu'elle construit, clic sur une unité soutenue pour centrer la carte dessus. Sous chaque unité soutenue, ce qu'elle coûte à la ville à chaque tour, une icône par point comme dans le jeu d'origine : boucliers, nourriture des colons et, en République ou en Démocratie, citoyens mécontents pour une unité militaire hors de la ville ; sous l'Anarchie et le Despotisme, les premières unités, autant que la ville a d'habitants, n'ont pas de bouclier : le gouvernement les entretient. Le panneau montre des chiffres et des barres (surplus de nourriture, de boucliers et de commerce, ce qui part au soutien des unités ou à la corruption, risque de pollution) ; le détail est dans les infobulles : coût, entretien et effet d'un bâtiment ou d'une unité, ce que mangent les citoyens et les colons, ville d'attache d'une unité, origine de la pollution.
- **Empire** : taux d'impôts, luxe et science (avec le déficit et **Balance** quand le trésor perd de l'or), révolution, guerre et paix avec les civilisations rencontrées, recherche, lancement du vaisseau.
- **L'IA** se souvient des traités rompus : rompre la paix (surtout tout juste signée) rend la victime, et dans une moindre mesure ceux qui l'apprennent, plus rétifs à la paix pendant une soixantaine de tours. Une civilisation bien plus forte que les autres les voit se liguer contre elle. Une IA qui veut la guerre la prépare : elle lève une armée et la masse dans sa ville la plus proche de sa cible, en pleine paix, puis déclare la guerre quand l'armée est prête. Elle ne signe pas la paix dans la vingtaine de tours qui suit sa déclaration, sauf si la guerre tourne mal, ni tant qu'elle prend plus de villes qu'elle n'en perd ; à court de terres libres, elle cherche plus volontiers la guerre, en République ou en Démocratie moins volontiers. L'IA reprend en priorité les villes qu'on lui a prises, et répond à un débarquement : attaquants mis en chantier, défenseurs en surnombre qui frappent l'envahisseur quand leurs chances sont bonnes. Avec les règles Civilization I, une civilisation en République ou en Démocratie ne peut pas déclarer la guerre et reste tenue par son Sénat d'accepter la paix ; Golden Ages n'a pas de Sénat.
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
| Maj + P | Piller la case |
| Maj + D | Dissoudre l'unité (à confirmer) |
| Entrée | Finir le tour |

Une nouvelle partie se nomme avant d'être lancée (champ **Save as**, obligatoire, à côté du bouton de lancement) : elle s'enregistre d'elle-même tous les cinq tours sous ce nom. Si une sauvegarde porte déjà ce nom, le dialogue prévient qu'elle sera remplacée et propose un nom libre. Si votre civilisation est détruite, la partie continue et vous pouvez la regarder jusqu'au bout. À la fin de la partie, **Replay the game** (fenêtre de fin de partie) rejoue toute la partie sur la carte du monde (voir Observer). Le replay montre toutes les civilisations : il n'est ouvert qu'une fois la partie finie, ou votre civilisation détruite.

## Observer

Mode **Watch the AI play them all** de la fenêtre « Game ».

- **Speed / Step / Play** (à droite de la barre du haut, à la place de End turn) : vitesse, tour par tour, lecture continue. Espace = lecture/pause, N = un tour.
- **Dossier** (à côté de la roue dentée, comme en partie jouée) : ouvre la fenêtre « Game ». Nouvelle partie (la graine est tirée au hasard ; la même graine avec les mêmes choix redonne exactement la même partie) avec le choix du monde : un monde généré ou la Terre du jeu original (départs historiques ou tirés au hasard). Pour un monde généré : la forme des terres (continents, petites îles, continents et îles, continent unique, ceinture de terre qui fait le tour du monde, continent à lacs, mer intérieure, isthme, Nouveau Monde où personne ne démarre, archipels en arc, continent fendu, ou Surprise qui tire tout au hasard sans le dire), la part de terres (20 à 80 %), le relief (plat, normal, accidenté), le climat (sec, normal, humide), la température (froid, tempéré, chaud) et l'âge (jeune, normal, vieux), chacun expliqué par une bulle au survol de son nom ; et les huttes (aucune, normales, nombreuses). Enregistrement sous un nom (dossier `saves/`) et rechargement ; une partie rechargée se poursuit comme l'originale.
- **Sur la carte** : « View as » pour voir le monde comme une civilisation (brouillard compris), le zoom et la mini-carte. Les calques Territory / Grid / AI missions sont derrière la roue dentée de la barre du haut.
- **État de la planète** (barre du haut, après les taux, dès qu'il y a de la pollution) : cases polluées, jauge du réchauffement (orange à mi-chemin du seuil, rouge aux trois quarts), tours avant l'arrivée d'un vaisseau spatial ; l'infobulle donne les chiffres.
- **Rail de droite** : World (classement des civilisations), Empire, City, Wonders, Space (la course à l'espace, toutes les civilisations), Science, History, Replay, Chronicle (en partie jouée, Turn et Cities en plus, Replay une fois la partie finie). Science, History et Replay occupent toute la largeur ; Échap ou « Back to map » ramène à la carte.
- **Clic sur une ville** : production, citoyens, cases exploitées, pollution, et pourquoi l'IA a choisi cette production.
- **Clic sur une unité ou un territoire** : panneau Empire de la civilisation, avec son vaisseau spatial, ce que son IA veut, ses expéditions outre-mer et ses missions. Le calque « AI missions » les dessine sur la carte.
- **Science, History, Chronicle** : arbre des technologies, courbes par civilisation, journal des événements (cliquer une ligne la situe sur la carte).
- **Replay** : toute la partie rejouée sur la carte du monde, comme à la fin d'une partie de Civ 1. Les villes apparaissent, changent de couleur quand elles sont prises et disparaissent quand elles sont rasées ; le territoire de chaque civilisation suit ses villes. Les combats s'allument en rouge et s'éteignent en six tours ; une étoile marque une merveille, un cercle une ville prise, une croix une ville rasée (calques Territory, Battles, Events). L'année et le dernier grand événement s'affichent sur la carte ; dessous, le classement et la chronique de ce moment (filtres Conquests, War & peace, Wonders, Governments, New cities ; un clic sur une ligne y amène la carte et cerne l'endroit). Lecture et pause (Espace), tour par tour (flèches), grand événement précédent ou suivant (Maj + flèches), début et fin (Début, Fin), barre de progression, vitesse Slow, Normal ou Fast. Aux vitesses lentes, la lecture marque une courte pause sur les grands événements. Une partie sauvegardée avant l'arrivée du replay n'a que ses villes du moment, chacune posée à sa date de fondation, et les événements que sa chronique gardait : le replay n'est complet qu'à partir du chargement, et le dit.

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
python simulate.py --seed 7 --turns 300 --shape small_islands --land 40 --relief 2 --climate 0
```

`--shape` prend une des formes de `map.shapes` dans `config/game.yaml` (on peut en ajouter, et un monde fixe se dessine dans `config/maps/`, comme `earth.yaml`) ; `--land` va de 20 à 80 par pas de 10 ; `--relief`, `--climate`, `--temperature`, `--age` et `--huts` vont de 0 à 2.

```bash
python simulate.py --seed 7 --turns 300 --rules golden_ages
```

`--rules` choisit le jeu de règles (un dossier de `config/rulesets/`, `civ1` par défaut) ; une partie chargée avec `--load` garde le sien.

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
| `terrains.yaml`, `governments.yaml`, `civilizations.yaml` | Terrains, gouvernements, civilisations et personnalités |
| `ai.yaml` | Poids et seuils de l'IA |
| `rulesets/<id>/` | Un jeu de règles : `technologies.yaml`, `units.yaml`, `buildings.yaml`, `wonders.yaml` (les effets des bâtiments et les capacités des unités sont déclarés ici), et son nom dans `ruleset.yaml` |

Chaque partie se joue avec un jeu de règles, choisi dans la fenêtre de nouvelle partie et enregistré dans ses sauvegardes : `civ1` (Civilization I), `golden_ages` (Golden Ages : une unité nouvelle à chaque époque, des canons qui ignorent les remparts, une seule Power Plant, Sewer System et Harbour, des merveilles qui ne deviennent jamais obsolètes, pas de Sénat pour tenir en paix une République ou une Démocratie) ou `renaissance` (Renaissance : Golden Ages avec la culture qui repousse les frontières, voir plus haut). Les fichiers de `renaissance/` sont une copie de ceux de `golden_ages/` avec la culture en plus : un changement de Golden Ages est à reporter dans Renaissance. Un fichier du dossier d'un jeu de règles remplace celui de `config/` qui porte le même nom ; `game.yaml` et `ai.yaml` y sont fusionnés clé par clé, pour ne changer que ce qui diffère (par exemple les unités que nomme `game.yaml` : unités de départ, mercenaires, barbares). Pour créer un jeu de règles, copier `config/rulesets/civ1/` sous un autre nom : le nom du dossier est l'identifiant que gardent les sauvegardes. Les parties sauvegardées avant ce choix sont des parties `civ1`.

Quelques réglages utiles dans `game.yaml` : `enabled_unit_domains` (retirer `sea` ou `air` pour une partie terrestre), `victory` (conquête, vaisseau), `calendar.max_turns` (fin au score), `pollution.enabled`.

Une erreur de config (clé inconnue, référence inexistante, sprite manquant) empêche le serveur de démarrer et dit où elle se trouve.
