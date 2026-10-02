# Plan — clone de Civilization I

Document de référence du projet. Plan validé le 2026-10-02 ; jalons M0 à M7 réalisés le même jour.
Pour lancer le jeu, voir [README.md](README.md).

## 1. Objectif et décisions

Un clone de Civilization I où, dans la première version, l'utilisateur observe : l'IA joue toutes les civilisations au tour par tour, de 4000 av. J.-C. jusqu'à une victoire.

| Sujet | Décision |
|---|---|
| Règles | Fidèles à Civ 1 partout où elles sont documentées. On réutilise tout ce qui est réutilisable, sans viser le un-pour-un |
| IA | Réécrite de zéro, lisible et paramétrable. L'original sert d'inspiration, pas de modèle à porter |
| Priorité de conception | Code lisible et évolutif avant tout |
| Honnêteté de l'IA | L'IA ne connaît que ce que sa civilisation a exploré ou voit. Aucun bonus caché |
| Carte | 80×50, aléatoire, monde cylindrique (raccord est-ouest). Paramétrable |
| Civilisations | 7 par partie plus les barbares, paramétrable jusqu'à 14 |
| Périmètre | M0 à M5 : jeu terrestre complet. M6 : mer et air. M7 : fin de partie. Tous réalisés |
| Stack | Python 3.11, FastAPI, uvicorn, PyYAML, pytest. Client en JS vanilla (modules ES, sans étape de build), canvas 2D, WebSocket |
| Langue | Code, identifiants, config et interface en anglais. Documentation en français |

### Sources de vérité pour les règles

Par ordre de priorité :

1. Tables de données d'OpenCivOne (`GameData.cs`) : unités, bâtiments, merveilles, techs, terrains, nations.
2. Code lisible d'OpenCivOne : `CityWorker.cs` (villes, pollution), `Segment_29f3.cs` (combat, arme nucléaire), `CheckPlayerTurn.cs` (déplacements, aménagements, transport, carburant), `MapInitAndIntro.cs` (carte), `Segment_1238.cs` (calendrier, réchauffement), `UnitManagement.cs` (huttes).
3. Manuel et règles connues de Civ 1, quand le code est illisible.
4. Notre jugement, en dernier recours. Tout écart volontaire est noté dans la section 8.

Tout se trouve sous `C:\V\Abandonware-France\Civilization\OpenCivOne\src\Game`. Chaque règle reprise cite sa source en commentaire.

## 2. Architecture

### Principes

- **Moteur indépendant du web.** `engine/` est du Python pur, sans entrée-sortie (sauf `persistence.py`, qui lit et écrit les sauvegardes). Il tourne à l'identique derrière le serveur et dans le simulateur.
- **Déterminisme.** Un seul générateur aléatoire, initialisé par la graine. Même graine, même partie. Une partie sauvegardée puis rechargée se poursuit exactement comme l'originale.
- **Un seul chemin de mutation.** Un contrôleur de joueur (IA aujourd'hui, humain demain) émet des actions (`engine/actions.py`). Le moteur les valide, les applique et émet des événements.
- **Règles pilotées par la config.** Aucune constante de jeu dans le code. Les YAML sont chargés dans des structures immuables et validés au démarrage : clé inconnue, mauvais type, référence inexistante ou sprite manquant arrêtent le serveur avec la liste complète des erreurs.
- **Vue par joueur.** L'IA reçoit une `PlayerView` (`engine/view.py`) : cases explorées, villes étrangères mémorisées, unités en vue. Elle n'a pas accès à l'état complet.
- **Client passif.** Le client affiche ce que le serveur envoie et ne contient aucune règle.

### Arborescence

```
config/                 données de jeu (YAML)
  game.yaml             constantes : carte, calendrier, ville, combat, déplacements, barbares,
                        pollution, nucléaire, vaisseau spatial, score, victoire
  terrains.yaml  units.yaml  buildings.yaml  wonders.yaml
  technologies.yaml  governments.yaml  civilizations.yaml
  ai.yaml               poids, seuils et personnalités de l'IA
resources/              sprites, servis tels quels
saves/                  parties sauvegardées (JSON, hors dépôt)
run.py  simulate.py     lanceurs (serveur, simulateur)
src/
  server/
    main.py             point d'entrée du serveur
    api/                app (FastAPI), session (partie en cours, observateurs, sauvegardes),
                        serialize (JSON)
    engine/
      rules/            schema.py (structures typées), loader.py (chargement + validation)
      model/            worldmap, entities (Unit, City, Player, Spaceship), game (état complet)
      mapgen/           generator (les 8 étapes d'origine), continents, sites (score de site)
      systems/          city, cities, production, research, movement (terre, mer, air, transport),
                        combat, visibility, diplomacy, government, trade, huts, barbarians,
                        pollution, nuclear, spaceship, calendar, turn
      effects.py        effets typés des bâtiments et merveilles
      actions.py        commandes acceptées par le moteur
      view.py           PlayerView : ce qu'un joueur sait
      persistence.py    sauvegarde et chargement (JSON)
      setup.py          nouvelle partie, positions de départ
    ai/
      controller.py     un contrôleur par civilisation
      knowledge.py      image du monde connue de la civ (régions, mers, menaces, sites)
      strategic.py      plan du tour : missions et besoins de l'empire
      overseas.py       expéditions outre-mer (colonies, invasions), marine, aviation
      missions.py       missions et affectation des unités
      city_governor.py  choix de production, achats, course à l'espace
      research.py  economy.py  diplomacy.py  pathfinding.py
      unit_ai/          settler, defender, attacker, explorer, caravan, ship, aircraft
      barbarian.py      contrôleur des barbares
    sim/                runner (parties sans UI), metrics (chiffres par tour, détection de blocage)
  client/
    index.html  css/style.css
    js/  main.js  net.js  state.js
         renderer/      map (carte), minimap, sprites
         panels/        civs (liste et empire), city, tech, chart, log
  tests/                119 tests : config, carte, villes, unités, empire, mer et air,
                        fin de partie et sauvegardes, IA, API
```

Dépendances : `api` → `sim` → `ai` → `engine`. Le moteur ne dépend de rien d'autre.

### Effets pilotés par la config

Un bâtiment déclare ce qu'il fait ; le code des règles interroge les effets (`engine/effects.py`) au lieu de tester des noms de bâtiments.

```yaml
- id: library
  cost: 80
  upkeep: 1
  requires: writing
  effects:
    - {type: yield_bonus, yield: science, percent: 50, mode: additive}

- id: nuclear_plant
  cost: 160
  requires: nuclear_power
  requires_building: factory
  effects:
    - {type: yield_bonus, yield: shields, percent: 50, mode: additive, exclusive_group: power}
    - {type: pollution_percent, percent: 50}
    - {type: meltdown_risk, safe_tech: fusion_power}

- id: ss_module                 # pièce de vaisseau : va au vaisseau, pas à la ville
  cost: 320
  requires: robotics
  requires_wonder: apollo_program
  effects:
    - {type: spaceship_part, part: module}
```

Portée d'un effet : `city` (défaut), `player` (toutes les villes du propriétaire) ou `continent`. Conditions possibles : `requires_tech`, `requires_building`. La liste des types d'effets est en tête de `buildings.yaml` et `wonders.yaml`. Ajouter un bâtiment dont les effets existent déjà ne demande aucun code.

Les unités suivent le même principe : `domain` (terre, mer, air), `abilities` (`coastal`, `attack_air`, `no_shore_attack`, `nuclear`…), `capacity` et `carries` pour le transport, `fuel` pour l'autonomie des avions.

### Protocole client-serveur

- HTTP : fichiers statiques, sprites (`/resources`), règles (`/api/rules`).
- WebSocket `/ws` : message `init` à la connexion (règles, carte, état, historique, journal, liste des sauvegardes), puis un message `turn` par tour (état, cases modifiées, événements).
- Commandes de l'observateur : `new_game` (graine, nombre de civs), `play`, `pause`, `step`, `speed`, `pov` (tout voir ou voir comme une civ), `city` et `player` (détails, avec les raisons de l'IA), `save` et `load` (par nom, dans `saves/`).

### Sauvegardes

`engine/persistence.py` écrit tout ce qui décide de la suite d'une partie : carte, joueurs, villes, unités, relations, merveilles, vaisseaux, réchauffement, et l'état du générateur aléatoire. Ce qui se déduit (quelle case porte quelle ville, chiffres des villes) est recalculé au chargement. Les contrôleurs enregistrent leur mémoire par `save_state()` / `load_state()` ; celle de l'IA ne contient que des données simples (expéditions en cours, missions des unités). L'historique des courbes et le journal de l'observateur voyagent dans le même fichier.

## 3. Config : corrections apportées aux données extraites

| Fichier | Correction |
|---|---|
| governments | `chieftainship` et `fundamentalism` retirés (absents de Civ 1), anarchie ajoutée. Taux maximum et corruption repris du code d'origine |
| technologies | La tech « Religion » a l'id `religion` (les merveilles la référençaient, le fichier l'appelait `theology`). Tech future ajoutée |
| terrains | Ressources de Civ 2 remplacées par celles de Civ 1. Défense de la rivière : 1.5. Irrigation, mines et transformations avec leurs durées |
| buildings | `airport`, `sewer_system` et `research_lab` retirés (Civ 2). Limite de l'aqueduc : taille 10. Pièces du vaisseau spatial ajoutées. Effets de pollution, bouclier nucléaire, risque de fusion du réacteur |
| wonders | Effets alignés sur le code d'origine : Pyramides (changement de gouvernement sans anarchie), Chapelle de Michel-Ange (+2 par cathédrale), Collège de Newton (+1/3 par bibliothèque et université), Phare et Magellan (+1 déplacement en mer, non cumulable), Barrage Hoover (pollution réduite sur le continent) |
| game | Calendrier d'origine : 20 ans par tour jusqu'à 1000, puis 10, 5, 2, 1. Fin en 2060 (niveau Prince). Sections pollution, nucléaire, vaisseau, score, victoire |
| units | `role` pour l'IA, `domain`, `abilities`, `sight`, `fuel`, `capacity` et `carries`. Porte-avions : 8 avions. Missile nucléaire lié au Projet Manhattan |
| civilizations | Barbares ajoutés, nom du peuple (`nation`) ajouté |

## 4. IA

### Déroulement d'un tour (`ai/controller.py`)

1. **Connaissance.** Régions connues (terres explorées contiguës ; une ville étrangère ferme le passage), mers connues et leurs ports, frontières de l'inconnu, menaces près des villes, sites de ville classés.
2. **Diplomatie.** Propositions de paix et déclarations de guerre, selon la personnalité et le rapport de forces estimé.
3. **Plan.** Missions publiées avec une priorité : défendre une ville, intercepter un ennemi, prendre une ville (ralliement puis assaut), fonder une ville, aménager ou dépolluer une case, explorer la terre ou la mer, embarquer pour une expédition, aider une merveille. Puis affectation des unités et calcul de ce qui manque à l'empire (défenseurs, colons, ouvriers, attaquants, explorateurs, navires, avions).
4. **Recherche, impôts, gouvernement.**
5. **Gouverneurs de ville.** Chaque production possible reçoit un score = poids du besoin × urgence × efficacité. Les meilleurs candidats sont conservés pour l'observateur. Lancement du vaisseau spatial quand il est prêt.
6. **Unités.** Chaque unité exécute sa mission selon son rôle. Les avions frappent d'abord, les navires bougent en dernier, une fois leurs passagers à bord.

Tous les poids et seuils sont dans `ai.yaml`. Les trois traits de `civilizations.yaml` (humeur, politique, idéologie) les modulent.

### Mer et air (`ai/overseas.py`, `unit_ai/ship.py`, `unit_ai/aircraft.py`)

- **Exploration.** Un navire par mer connue tant qu'il reste des rivages inconnus. Les trirèmes longent les côtes connues (elles peuvent se perdre au large).
- **Expéditions.** Une expédition rassemble des passagers dans un port, les transporte jusqu'à un rivage proche de son but et les débarque ; l'IA terrestre prend ensuite le relais. Deux sortes : *colonie* (un colon et une escorte, quand il n'y a plus de site accessible à pied) et *invasion* (un groupe d'attaquants vers une ville ennemie qu'on ne peut atteindre que par mer). Étapes : `gather` (trouver ou faire construire un navire, appeler les passagers par des missions `embark`), `sail`, débarquement. Les expéditions vivent dans la mémoire du contrôleur et dans les sauvegardes.
- **Marine.** En guerre, des navires de combat chassent les navires ennemis en vue et bombardent les défenseurs des villes côtières assiégées.
- **Aviation.** Les avions ne prennent pas de mission : chacun frappe la meilleure cible à portée de sa base en gardant de quoi rentrer, sinon se rapproche du front. L'arme nucléaire vise la plus grande ville ennemie à portée.
- **Fin de partie.** Les colons dépolluent en priorité ; les villes polluantes construisent transports en commun, centrale propre ou recyclage ; les grandes villes construisent une défense SDI quand l'arme nucléaire existe. Une fois le Programme Apollo construit, les villes productives fabriquent les pièces d'un vaisseau minimal avec quelques moteurs de plus.

### Outillage

- **Simulateur** : `python simulate.py --seeds 1 2 3 --turns 610`. Rapport par civ, export CSV, détection de blocage (ville sans production, civ qui stagne, faillite), `--save` et `--load` pour reprendre une partie.
- **Journal de décision** : dans l'interface, onglet City (« Why this production ») et onglet Empire (besoins, expéditions, missions, classement des recherches).
- **Tests** : règles une à une sur de petits mondes fabriqués, invariants de l'état pendant une partie complète, reproductibilité par graine et après chargement, honnêteté de la vue, scénarios d'IA (colonie et invasion par mer, frappe aérienne et nucléaire).

## 5. Jalons

| | Contenu | État |
|---|---|---|
| **M0** Fondations | Config restructurée, chargeur et validation, serveur et client, tests | Fait |
| **M1** Monde | Génération de carte, rendu canvas, déplacement, zoom, minicarte, nouvelle partie par graine | Fait |
| **M2** Villes | Boucle de tours, fondation, rendements, croissance, production, contrôles de lecture, panneau de ville, simulateur | Fait |
| **M3** Expansion et science | Déplacements, exploration, brouillard par civ, expansion par score de site, aménagements, arbre de recherche, huttes | Fait |
| **M4** Économie | Commerce, impôts, luxe, science, bonheur et désordre, effets des bâtiments, entretien, corruption, gouvernements, merveilles, caravanes | Fait |
| **M5** Guerre | Combat, zones de contrôle, prise de villes, diplomatie, IA stratégique, missions, barbares | Fait |
| **M6** Mer et air | Navires, transport, débarquements, combat naval, aviation et carburant, barbares venus de la mer, IA navale et aérienne | Fait |
| **M7** Fin de partie | Pollution et réchauffement, nucléaire, vaisseau spatial, score et conditions de victoire, sauvegarde | Fait |

Ensuite : joueur humain (l'API d'actions est prête), diplomates, carte de la Terre, éditeur de carte.

### Ce que donnent les parties simulées (7 civs, partie complète)

Neuf graines jouées jusqu'au bout (1, 2, 4 à 10), sans plantage ni blocage signalé :

- Les neuf parties se terminent par l'arrivée d'un vaisseau sur Alpha du Centaure, entre 1876 et 2031. La conquête totale et la victoire au score en 2060 existent (et sont testées) mais ne se sont pas produites.
- La plupart des civilisations ont de 5 à 20 villes ; les plus grandes dépassent 30. Une civ mal placée peut rester à quelques villes.
- De 56 à 79 villes fondées par partie, dont des colonies outre-mer ; de 11 à 15 merveilles ; de 30 à 70 technologies pour les civs qui se développent.
- Des guerres dans chaque partie, des villes prises, parfois une civilisation détruite.
- Chaque civ entretient un à cinq navires ; l'aviation apparaît dans les parties qui durent. La pollution reste contenue (les colons nettoient) : aucun réchauffement, aucune frappe nucléaire dans ces parties.
- De 60 à 110 ms par tour en moyenne sur une partie complète.

## 6. Assets

Les sprites de `resources/` suffisent : terrains et surcouches en 60×60 avec transparence (dont la pollution), unités en 30×30 environ (terre, mer, air), ville en 30×30.

Dessinés au canvas, sans sprite :

- carré à la couleur de la civ derrière l'unité et la ville, taille de la ville, étoile de la capitale ;
- marqueurs d'ordre (F fortifiée, S sentinelle, R route, I irrigation, M mine, P dépollution), point jaune des vétérans ;
- rivières et routes, reliées de case en case (les sprites `river_overlay` et `route` ne se raccordent pas) ;
- huttes, forteresses, territoires, brouillard.

En mer, la case montre le navire et non ses passagers. Les transitions de côte ne sont pas traitées.

## 7. Conventions

- Tout identifiant de config est en `snake_case` et sert de clé partout (code, sérialisation, client).
- Une règle de jeu correspond à une fonction testable, avec la source citée quand elle vient d'OpenCivOne.
- L'IA ne lit le jeu qu'à travers `PlayerView` (seule exception : les barbares, qui ne sont pas une civilisation).
- Un paramètre d'IA va dans `ai.yaml`, un paramètre de règle dans `game.yaml`.
- La mémoire d'un contrôleur ne contient que des données simples (JSON), pour entrer dans les sauvegardes.

## 8. Écarts volontaires par rapport à Civ 1

| Écart | Raison |
|---|---|
| IA réécrite, honnête, sans bonus | Décisions de conception |
| Formule de mécontentement du joueur humain appliquée à toutes les civs | L'original en a une plus clémente pour l'IA |
| Placement des citoyens par un « maire » à poids configurables | La règle d'origine laisse les grandes villes sans production |
| Une ville de taille 1 ne peut pas produire de colons | L'original la dissout, ou offre le colon à une civ d'une seule ville |
| Score de site : la case de la ville compte quatre fois | L'original donne ce poids à la case au nord, par erreur d'index |
| Contact : guerre tant qu'aucun traité n'est signé, sans écran de négociation | Pas de joueur humain ; ni tribut ni échange de techs |
| En paix : pas d'attaque ni d'entrée dans les villes de l'autre, mais pas d'expulsion du territoire | Simplicité |
| Zones de contrôle exercées seulement par les ennemis | Évite les blocages entre civs en paix |
| Barbares : la moitié des raids débarque d'un navire, l'autre apparaît à terre, hors de vue | Les villes de l'intérieur ne sont pas à l'abri |
| Transport explicite : une unité est à bord d'un navire précis | L'original déduit le chargement de la position ; l'explicite est plus lisible |
| Une unité débarquée d'un navire peut entrer dans une ville ennemie vide | Elle ne peut pas attaquer depuis le navire, comme dans l'original |
| La pollution touche toutes les civilisations | L'original en dispense les joueurs ordinateur |
| Vaisseau spatial simplifié : trois sortes de pièces, durée de vol selon les moteurs et la masse, arrivée certaine | Le code d'origine du vaisseau est illisible |
| Une ville dotée d'une défense SDI abat le missile qui la vise : rien n'explose | L'original protège seulement la case de la ville |
| Score : formule d'origine plus 2 points par technologie | Départage les civilisations en début de partie |
| Couleur propre à chacune des 14 civs | L'original partage 7 couleurs |
| Pas de limite à 128 unités et 128 villes | Limite mémoire de l'original |

## 9. Limites connues

- Diplomate désactivé (ambassade, vol de tech, sabotage non codés).
- Pas de guerre civile à la prise d'une capitale, pas de catastrophes aléatoires, pas de pillage.
- Le maire n'utilise que des amuseurs (ni percepteurs ni savants).
- L'IA ne construit pas de forteresses, ne relie pas ses villes par des routes de façon délibérée et ne construit pas de porte-avions (le moteur les gère).
- Le bombardier peut attaquer plusieurs fois par tour ; le sous-marin n'est pas invisible ; les chasseurs n'interceptent pas pendant le tour adverse.
- Les invasions par mer sont rares : l'IA n'en lance que si elle n'a aucune cible accessible à pied et se juge plus forte.
- La course à l'espace clôt en général la partie avant que l'arme nucléaire et le réchauffement n'aient pesé.
- Un test joue une partie entière et dure environ une minute (`python -m pytest -m "not slow"` pour l'éviter).
