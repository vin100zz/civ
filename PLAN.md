# Plan — clone de Civilization I

Document de référence du projet. Plan validé le 2026-10-02 ; jalons M0 à M7 réalisés le même jour, M8 à M12 (joueur humain) le 2026-10-04.
Pour lancer le jeu, voir [README.md](README.md).

## 1. Objectif et décisions

Un clone de Civilization I, de 4000 av. J.-C. jusqu'à une victoire, en deux modes :

- **observer** : l'IA joue toutes les civilisations au tour par tour, l'utilisateur regarde et comprend ce qu'elle fait ;
- **jouer** : l'utilisateur dirige une civilisation contre les autres, jouées par l'IA.

| Sujet | Décision |
|---|---|
| Règles | Fidèles à Civ 1 partout où elles sont documentées. On réutilise tout ce qui est réutilisable, sans viser le un-pour-un |
| IA | Réécrite de zéro, lisible et paramétrable. L'original sert d'inspiration, pas de modèle à porter |
| Priorité de conception | Code lisible et évolutif avant tout |
| Honnêteté de l'IA | L'IA ne connaît que ce que sa civilisation a exploré ou voit. Aucun bonus caché |
| Honnêteté envers le joueur | Son navigateur ne reçoit que ce que sa civilisation sait : terres explorées, unités en vue, villes mémorisées, événements dont elle a connaissance |
| Difficulté | Cinq niveaux qui ne changent que la civilisation du joueur (mécontentement, coût de la recherche). L'IA joue toujours avec les valeurs « Prince » |
| Carte | 80×50, aléatoire, monde cylindrique (raccord est-ouest). Paramétrable |
| Civilisations | 7 par partie plus les barbares, paramétrable jusqu'à 14 |
| Périmètre | M0 à M5 : jeu terrestre complet. M6 : mer et air. M7 : fin de partie. M8 à M12 : joueur humain. Tous réalisés |
| Stack | Python 3.11, FastAPI, uvicorn, PyYAML, pytest. Client en JS vanilla (modules ES, sans étape de build), canvas 2D, WebSocket |
| Langue | Code, identifiants, config et interface en anglais. Documentation en français |

### Sources de vérité pour les règles

Par ordre de priorité :

1. Tables de données d'OpenCivOne (`GameData.cs`) : unités, bâtiments, merveilles, techs, terrains, nations.
2. Code lisible d'OpenCivOne : `CityWorker.cs` (villes, pollution), `Segment_29f3.cs` (combat, arme nucléaire), `CheckPlayerTurn.cs` (déplacements, aménagements, transport, carburant), `MapInitAndIntro.cs` (carte), `Segment_1238.cs` (calendrier, réchauffement), `UnitManagement.cs` (huttes).
3. Manuel et règles connues de Civ 1, quand le code est illisible.
4. Notre jugement, en dernier recours. Tout écart volontaire est noté dans la section 9.

Tout se trouve sous `C:\V\Abandonware-France\Civilization\OpenCivOne\src\Game`. Chaque règle reprise cite sa source en commentaire.

## 2. Architecture

### Principes

- **Moteur indépendant du web.** `engine/` est du Python pur, sans entrée-sortie (sauf `persistence.py`, qui lit et écrit les sauvegardes). Il tourne à l'identique derrière le serveur et dans le simulateur.
- **Déterminisme.** Un seul générateur aléatoire, initialisé par la graine. Même graine, même partie. Une partie sauvegardée puis rechargée se poursuit exactement comme l'originale.
- **Un seul chemin de mutation.** Un contrôleur de joueur (IA ou personne) émet des actions (`engine/actions.py`). Le moteur les valide, les applique et émet des événements. Une action refusée ne change rien et dit pourquoi.
- **Règles pilotées par la config.** Aucune constante de jeu dans le code. Les YAML sont chargés dans des structures immuables et validés au démarrage : clé inconnue, mauvais type, référence inexistante ou sprite manquant arrêtent le serveur avec la liste complète des erreurs.
- **Vue par joueur.** L'IA reçoit une `PlayerView` (`engine/view.py`) : cases explorées, villes étrangères mémorisées, unités en vue. Elle n'a pas accès à l'état complet. Ce qui est envoyé au navigateur d'un joueur passe par la même vue.
- **Client passif.** Le client affiche ce que le serveur envoie et ne contient aucune règle : les ordres possibles d'une unité, les productions possibles d'une ville et les chances d'un combat viennent du serveur.

### Arborescence

```
config/                 données de jeu (YAML)
  game.yaml             constantes : carte, calendrier, ville, combat, déplacements, barbares,
                        pollution, nucléaire, vaisseau spatial, score, victoire
  terrains.yaml  governments.yaml  civilizations.yaml
  ai.yaml               poids, seuils et personnalités de l'IA
  rulesets/             un dossier par jeu de règles, choisi à la création d'une partie
    civ1/               Civilization I : ruleset.yaml (nom), technologies.yaml, units.yaml,
                        buildings.yaml, wonders.yaml ; ses fichiers passent avant ceux de config/
    golden_ages/        Golden Ages : la progression des unités à chaque époque, des merveilles
                        sans obsolescence, des gouvernements sans Sénat (governments.yaml)
                        (propositions : https://claude.ai/artifact/U8n59wP4ADT1XQV78eBpsu)
resources/              sprites, servis tels quels
saves/                  parties sauvegardées (JSON, hors dépôt)
run.py  simulate.py     lanceurs (serveur, simulateur)
src/
  server/
    main.py             point d'entrée du serveur
    api/                app (FastAPI), session (partie en cours, navigateurs, sauvegardes),
                        commands (ordres du joueur -> actions), serialize (JSON),
                        replay (ce que montre le replay de fin de partie, noté tour par tour)
    engine/
      rules/            schema.py (structures typées), loader.py (chargement + validation)
      model/            worldmap, entities (Unit, City, Player, Spaceship), game (état complet)
      mapgen/           generator (les 8 étapes d'origine), continents, sites (score de site)
      systems/          city, cities, budget (ce que vaut un bâtiment, lequel vendre),
                        production, research, movement (terre, mer, air, transport),
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
    human/
      controller.py     contrôleur d'une civilisation dirigée par une personne : ce qu'elle délègue
                        (aller à, unités automatiques, gouverneurs de ville)
      orders.py         ordres ouverts à une unité, aperçu d'un déplacement (combat, trajet)
      report.py         alertes : ennemis près des villes, villes en difficulté
    sim/                runner (parties sans UI), metrics (chiffres par tour, détection de blocage)
  client/
    index.html  css/style.css
    js/  main.js  net.js  state.js  icons.js
         play.js        mode jeu : unité active, file d'attente, ordres, clavier, fin de tour
         replay.js      mouvements vus par le joueur, rejoués avant que le message qui les porte soit appliqué
         dialogs.js     partie (nouvelle, sauvegardes), choix de recherche, messages, fin de partie
         toasts.js      messages du tour
         tips.js        infobulles des panneaux (éléments marqués data-tip)
         renderer/      map (carte), ground (sol), minimap, sprites
         panels/        turn (tour du joueur), civs (monde, empire d'une IA), empire (empire du
                        joueur), city, tech, chart, log, unitbar (barre de l'unité active),
                        replay (la partie rejouée sur la carte du monde)
  tests/                207 tests : config, carte, villes, unités, empire, mer et air,
                        fin de partie et sauvegardes, IA, joueur humain, API
```

Dépendances : `api` → `sim` → `human` → `ai` → `engine`. Le moteur ne dépend de rien d'autre.

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
- Commandes de l'observateur : `new_game` (graine, nombre de civs, monde), `play`, `pause`, `step`, `speed`, `pov` (tout voir ou voir comme une civ), `city` et `player` (détails, avec les raisons de l'IA), `save` et `load` (par nom, dans `saves/`), `replay` (le replay de la partie, message `replay` ; refusé tant qu'une personne dirige une civilisation).
- Commandes du joueur : `new_game` avec `mode: play`, `civ` et `level` ; `action` (un ordre, voir `api/commands.py`) ; `end_turn` ; `goto`, `automate`, `govern` (délégations) ; `unit` (détail et ordres possibles d'une unité) ; `preview` (ce que ferait un déplacement).
- Messages propres au mode jeu : `update` après chaque ordre (résultat, état, cases modifiées ou découvertes, événements, détail de l'unité ou de la ville concernée), `unit`, `preview`. L'état porte alors `play` (qui est le joueur), `me` (ses affaires : recherche, budget, relations, propositions de paix), `alerts` et `notes`.
- `update` et `turn` portent aussi `steps` : les pas d'unités que le joueur a vus (les siens après un ordre, ceux des autres pendant qu'ils jouaient), dans l'ordre. Le moteur signale chaque pas (`Game.watcher`), la session ne garde que ceux dont une case au moins était en vue à ce moment-là, avec les unités présentes sur ces cases après le pas.

### Sauvegardes

`engine/persistence.py` écrit tout ce qui décide de la suite d'une partie : carte, joueurs, villes, unités, relations, merveilles, vaisseaux, réchauffement, et l'état du générateur aléatoire. Une partie jouée se sauvegarde au milieu du tour du joueur : le fichier dit qui est dirigé par une personne (`humans`) et à qui c'est de jouer. Elle s'enregistre aussi d'elle-même tous les cinq tours sous le nom `autosave`. Ce qui se déduit (quelle case porte quelle ville, chiffres des villes) est recalculé au chargement. Les contrôleurs enregistrent leur mémoire par `save_state()` / `load_state()` ; celle de l'IA ne contient que des données simples (expéditions en cours, missions des unités). L'historique des courbes, le journal de l'observateur et le replay voyagent dans le même fichier.

### Replay (`api/replay.py`, `panels/replay.js`)

À chaque ligne de l'historique des courbes (une par tour : le monde au début du tour), la session note pour le replay ce qui a changé dans les villes depuis la ligne d'avant : `["found", tour, ville, propriétaire, x, y, nom, taille]`, `["owner", tour, ville, propriétaire]`, `["size", tour, ville, taille]`, `["gone", tour, ville]`. La comparaison des villes attrape toutes les façons dont une ville naît, change de main ou disparaît (colons, huttes, prises, barbares). Elle garde aussi, parmi les événements lus, les grands événements (villes fondées, prises, rasées, civilisations détruites, merveilles, gouvernements, guerres, paix, contacts, vaisseau, arme nucléaire, réchauffement, fin de partie) et les combats (case, vainqueur, perdant). Le journal de l'observateur, limité aux 600 derniers événements, n'y suffirait pas. Une partie complète de 580 tours en donne environ 1 300 changements de ville, 280 événements et 540 combats, soit 66 Ko sur les 575 Ko de la sauvegarde. Le client rebâtit chaque tour à partir de ces changements et dessine la carte comme la mini-carte, avec la même règle de territoire. Une image du replay porte l'année du tour qui vient d'être joué, dont elle montre les événements. Une sauvegarde d'avant le replay n'a que ses villes du moment, posées au tour qui suit leur fondation (`City.founded_turn`), et les grands événements de son journal ; le replay dit à partir de quand il est complet.

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
2. **Diplomatie.** Propositions de paix et déclarations de guerre, selon la personnalité et le rapport de forces estimé. Une déclaration de guerre rompt un traité : le moteur l'inscrit au dossier de la civilisation qui la déclare (`Player.broken_treaties`), et l'IA s'en méfie d'autant, sa victime surtout, les civilisations qui l'ont appris un peu moins ; la méfiance s'efface en 60 tours et compte double pour un traité rompu moins de 16 tours après sa signature. Une civilisation connue bien plus forte que toutes les autres voit les autres se liguer : elles font moins volontiers la paix avec elle, plus volontiers entre ennemis de cette civilisation, et lui déclarent la guerre en comptant les forces de ses autres ennemis. Une guerre se prépare avant d'être déclarée (`memory["war_plan"]`) : le tirage qui la décide choisit une cible, un voisin terrestre plus faible ; l'empire produit alors comme en temps de guerre et masse ses attaquants dans sa ville la plus proche de la cible (missions `attack_city` au stade `rally`), puis déclare la guerre quand il a les trois quarts de sa force de guerre, ou au bout de 25 tours s'il a de quoi former un groupe d'assaut ; sinon il y renonce. Une guerre qu'elle a déclarée, l'IA la poursuit au moins 20 tours, sauf si elle y perd des villes ; ensuite chaque ville prise à l'ennemi dans les 30 derniers tours, moins chaque ville perdue, l'éloigne de la paix (`diplomacy.momentum`, villes prises notées par `AIController._note_conquests`). Une civilisation qui n'a plus de site libre sur ses terres cherche plus volontiers la guerre. Seules les guerres contre un voisin qu'on peut atteindre à pied empêchent d'en préparer une autre. Une République ou une Démocratie, dont les unités au loin rendent les citoyens mécontents, prépare moins volontiers une guerre, et les chefs agressifs leur préfèrent la Monarchie ou le Communisme.
3. **Plan.** Missions publiées avec une priorité : défendre une ville, intercepter un ennemi, prendre une ville (ralliement puis assaut ; une ville qu'on a perdue passe en premier pendant 80 tours), fonder une ville, aménager ou dépolluer une case, explorer la terre ou la mer, embarquer pour une expédition, aider une merveille. Puis affectation des unités et calcul de ce qui manque à l'empire (défenseurs, colons, ouvriers, attaquants, explorateurs, navires, avions). Un ennemi débarqué près d'une ville appelle une contre-attaque : un attaquant de plus par envahisseur, même sans ville ennemie à portée, et les défenseurs en surnombre qui ont de bonnes chances (60 %) vont le frapper.
4. **Recherche, impôts, gouvernement.**
5. **Gouverneurs de ville.** Chaque production possible reçoit un score = poids du besoin × urgence × efficacité. Les meilleurs candidats sont conservés pour l'observateur. Lancement du vaisseau spatial quand il est prêt.
6. **Unités.** Chaque unité exécute sa mission selon son rôle. Les avions frappent d'abord, les navires bougent en dernier, une fois leurs passagers à bord.

**Travaux de terrain** (`strategic.improve_missions`). Un travail vaut ce qu'il rapporte par tour de travail, si long soit-il : irrigation, mine, route qui apporte du commerce, chemin de fer partout où il augmente le rendement, jungle et marais changés en prairie (jamais sur une ressource ; les forêts restent). Les routes, puis les chemins de fer, qui relient les villes d'une même terre passent en priorité : les villes les plus proches d'abord jusqu'à ce que toutes soient reliées, en suivant les routes déjà faites.

Tous les poids et seuils sont dans `ai.yaml`. Les trois traits de `civilizations.yaml` (humeur, politique, idéologie) les modulent.

### Mer et air (`ai/overseas.py`, `unit_ai/ship.py`, `unit_ai/aircraft.py`)

- **Exploration.** Un navire par mer connue tant qu'il reste des rivages inconnus. Les trirèmes longent les côtes connues (elles peuvent se perdre au large).
- **Expéditions.** Une expédition rassemble des passagers dans un port, les transporte jusqu'à un rivage proche de son but et les débarque ; l'IA terrestre prend ensuite le relais. Deux sortes : *colonie* (un colon et une escorte, quand il n'y a plus de site accessible à pied) et *invasion* (un groupe d'attaquants vers une ville ennemie qu'on ne peut atteindre que par mer ; pour reprendre une ville perdue, il suffit d'être à moitié aussi fort). Étapes : `gather` (trouver ou faire construire un navire, appeler les passagers par des missions `embark`), `sail`, débarquement. Les expéditions vivent dans la mémoire du contrôleur et dans les sauvegardes.
- **Marine.** En guerre, des navires de combat chassent les navires ennemis en vue et bombardent les défenseurs des villes côtières assiégées.
- **Aviation.** Les avions ne prennent pas de mission : chacun frappe la meilleure cible à portée de sa base en gardant de quoi rentrer, sinon se rapproche du front. L'arme nucléaire vise la plus grande ville ennemie à portée.
- **Fin de partie.** Les colons dépolluent en priorité ; les villes polluantes construisent transports en commun, centrale propre ou recyclage ; les grandes villes construisent une défense SDI quand l'arme nucléaire existe. Une fois le Programme Apollo construit, les villes productives fabriquent les pièces d'un vaisseau minimal avec quelques moteurs de plus.

### Outillage

- **Simulateur** : `python simulate.py --seeds 1 2 3 --turns 610`. Rapport par civ, export CSV, détection de blocage (ville sans production, civ qui stagne, faillite), `--save` et `--load` pour reprendre une partie.
- **Journal de décision** : dans l'interface, onglet City (« Why this production ») et onglet Empire (besoins, expéditions, missions, classement des recherches).
- **Tests** : règles une à une sur de petits mondes fabriqués, invariants de l'état pendant une partie complète, reproductibilité par graine et après chargement, honnêteté de la vue, scénarios d'IA (colonie et invasion par mer, frappe aérienne et nucléaire).

## 5. Joueur humain

### Le tour (`engine/systems/turn.py`)

`play_turn` joue un tour entier, pour le simulateur et le mode observateur. `advance` joue la même séquence mais s'arrête quand vient le tour d'un contrôleur marqué `interactive` : ses villes sont traitées, ses unités prêtes, et le moteur attend. La session applique alors les ordres un par un (`actions.apply`), puis rappelle `advance`, qui clôt ce tour et fait jouer les autres. Une partie sans joueur donne exactement les mêmes résultats par les deux chemins (testé). Si la civilisation du joueur est détruite, la partie continue en mode observateur.

### Ce que le joueur délègue (`human/controller.py`)

Le `HumanController` ne décide rien à la place du joueur ; il exécute au début de chaque tour ce qui lui a été confié, avec les outils de l'IA et à travers la même `PlayerView` :

- **Aller à.** L'unité suit le chemin connu jusqu'à sa destination, sur plusieurs tours, sans jamais engager le combat : elle s'arrête devant une unité ou une ville étrangère.
- **Exploration automatique** (`unit_ai/explorer.py`) pour une unité terrestre ou un navire, jusqu'à ce qu'il n'y ait plus rien à découvrir.
- **Colons automatiques** : ils se partagent les travaux de terrain qu'une IA ferait autour des villes (`strategic.improve_missions`).
- **Gouverneur de ville** : la ville choisit sa production comme une ville de l'IA (`city_governor.py`), sans armer d'expédition outre-mer.
- **Sentinelles** : une unité en sentinelle se réveille quand un ennemi arrive à côté d'elle.

Tout ordre donné à la main reprend l'unité. Ces délégations sont des données simples, enregistrées avec la partie.

### Ce que le joueur sait (`api/serialize.py`, `PlayerView.knows_event`)

- La carte envoyée ne contient que les cases explorées ; les autres sont de la mer anonyme, et arrivent quand elles sont découvertes.
- Les unités étrangères ne sont envoyées que si elles sont en vue ; les villes étrangères telles qu'elles ont été vues la dernière fois.
- D'une civilisation non rencontrée, rien, pas même son nom. D'une civilisation rencontrée : nom, gouvernement, villes vues, merveilles, guerres et traités avec les civilisations que le joueur connaît. Trésor, science et armées restent secrets.
- Les événements : ceux qui touchent le joueur, ceux qui se passent sous ses yeux, et les nouvelles du monde (merveille, civilisation détruite, vaisseau lancé, frappe nucléaire, réchauffement).
- Les courbes ne suivent que sa propre civilisation. Tout est dévoilé à la fin de la partie, replay compris.

### Diplomatie

Une IA qui propose la paix au joueur n'obtient pas de réponse immédiate : la proposition reste sur la table (`Relation.pending_from`) jusqu'au tour du joueur, qui accepte ou refuse (`AnswerPeace`). Sans réponse à la fin de son tour, elle est refusée. Le joueur propose la paix et déclare la guerre par les mêmes actions que l'IA.

### Interface

Barre du haut : à gauche, le temple et le nom du jeu, le dossier « Game » et la roue dentée des calques de la carte ; puis l'horloge, gouvernement, trésor, recherche, taux, l'état de la planète dès qu'il y a de la pollution (cases polluées, jauge du réchauffement, vaisseaux en vol, les chiffres dans l'infobulle), et la fin de tour. Le survol d'un bouton donne sa fonction (`data-hint`, `tips.js`) à la place de l'infobulle du navigateur. Panneau « Turn » : décisions en attente, alertes, unités sans ordre, villes, nouvelles. Quand le trésor sera vide d'ici cinq tours, une alerte dit quel bâtiment serait vendu (`human/report.py`), la pastille du trésor passe à l'ambre puis au rouge, et le bouton « Balance » (dans l'alerte et dans Empire) applique les taux que propose le serveur : l'impôt monte, la science cède d'abord, le luxe ensuite tant qu'aucune ville ne se révolte. Barre de l'unité active avec les ordres possibles et leurs raccourcis. Le tour se termine de lui-même quand la dernière unité a reçu son ordre ; sans unité à déplacer, c'est au joueur de le finir. Tant qu'une décision attend (ville sans production, recherche à choisir, proposition de paix), le tour ne peut pas finir : le bouton est grisé et dit pourquoi. Chaque demande de fin de tour nomme le tour qu'elle clôt, pour que deux fenêtres ouvertes sur la même partie ne puissent pas en sauter un. L'unité active clignote, comme dans l'original (pas de clignotement si le système demande de réduire les animations). Sur la carte : clic pour choisir une unité ou avancer d'une case, clic droit pour y envoyer l'unité, aperçu des chances au survol d'un ennemi, trajet et durée d'un « aller à ». Fiche de ville : production, file de production (Ctrl+clic ; `City.queue`, enregistrée avec la partie : à la fin d'un élément, le premier élément encore constructible de la file prend la suite, `production.take_from_queue` ; sans file une unité est reconstruite, sauf les colons, après lesquels le contrôleur de la personne laisse la ville sans production pour qu'elle choisisse ; un gouverneur ne touche pas à une ville qui a une file), achat, citoyens placés à la main, spécialistes, vente, gouverneur. Science : objectif de recherche (`Player.research_goal`) : à chaque avance obtenue, de quelque façon que ce soit, la recherche vide passe à la première avance du chemin (`research.goal_path`, prérequis d'abord, ordre des règles sinon). Empire : budget, révolution, affaires étrangères, vaisseau. Les unités qui changent de case glissent à l'écran le long du chemin suivi. Au début du tour, les pas et les combats des autres civilisations vus par le joueur sont rejoués un par un, caméra à l'appui (Échap pour passer) ; un combat se voit : l'attaquant s'élance, le perdant disparaît dans un éclair. La caméra ne quitte jamais un mouvement en cours : elle attend sa fin avant d'aller à l'unité suivante, et les touches d'ordre sont ignorées pendant ce court instant.

## 6. Jalons

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
| **M8** Tour du joueur | Tour reprenable, nouvelle partie avec sa civilisation, ordres et fin de tour par WebSocket, vue verrouillée, sauvegarde en plein tour | Fait |
| **M9** Unités | Unité active et file d'attente, déplacement au clavier et à la souris, barre d'ordres, piles, aller à, réveil des sentinelles | Fait |
| **M10** Villes et empire | Production et achat, citoyens et spécialistes, vente, recherche, taux, révolution, vaisseau, décisions du tour | Fait |
| **M11** Diplomatie et information | Réponse aux propositions de paix, guerre et paix depuis l'empire, carte, événements, détails et courbes limités à ce que le joueur sait, messages du tour, défaite et victoire | Fait |
| **M12** Confort | Colons et explorateurs automatiques, gouverneur de ville, sauvegarde automatique, glissement des unités, niveaux de difficulté | Fait, sauf le réglage de l'IA contre un humain |

Ensuite : régler l'IA contre un joueur humain à partir de vraies parties, écran de négociation, diplomates, éditeur de carte (la Terre est jouable depuis le 17 octobre 2026).

### Ce que donnent les parties simulées (7 civs, partie complète)

Neuf graines jouées jusqu'au bout (1, 2, 4 à 10), sans plantage ni blocage signalé :

- Les neuf parties se terminent par l'arrivée d'un vaisseau sur Alpha du Centaure, entre 1876 et 2031. La conquête totale et la victoire au score en 2060 existent (et sont testées) mais ne se sont pas produites.
- La plupart des civilisations ont de 5 à 20 villes ; les plus grandes dépassent 30. Une civ mal placée peut rester à quelques villes.
- De 56 à 79 villes fondées par partie, dont des colonies outre-mer ; de 11 à 15 merveilles ; de 30 à 70 technologies pour les civs qui se développent.
- Des guerres dans chaque partie, des villes prises, parfois une civilisation détruite.
- Chaque civ entretient un à cinq navires ; l'aviation apparaît dans les parties qui durent. La pollution reste contenue (les colons nettoient) : aucun réchauffement, aucune frappe nucléaire dans ces parties.
- De 60 à 110 ms par tour en moyenne sur une partie complète.

### Guerres préparées (octobre 2026)

Une partie observée de 14 civilisations sur une carte à 70 % de terres finissait toujours par la course à l'espace : une cinquantaine de déclarations de guerre pour 130 traités de paix, la paix signée en général le tour même de la rencontre, une quarantaine de villes prises, une civilisation détruite au plus. Le moteur de combat n'y était pour rien (une unité de siège de son époque bat un défenseur fortifié 5 à 7 fois sur 10) ; l'IA déclarait la guerre sans armée (0,15 attaquant par ville en paix), et ses guerres duraient une vingtaine de tours : elle proposait ou acceptait la paix sans regarder si elle gagnait. Une IA prépare désormais ses guerres et les poursuit tant qu'elles tournent bien (section 4), et Golden Ages n'a plus de Sénat. Sur 8 graines (`golden_ages`, 14 civs, `--land 70`), avant puis après :

| | Avant | Après |
|---|---|---|
| Déclarations de guerre | 50 | 65 |
| Villes prises (dont rasées) | 39 (12) | 114 (29) |
| Civilisations détruites | 1,1 | 3,75 |
| Combats | 600 | 1 400 |
| Fin de partie | vaisseau, tour 406 en moyenne | vaisseau 5 fois, score en 2060 3 fois ; tour 561 en moyenne |

Avec les règles `civ1` (7 civs, carte par défaut) : 23 villes prises au lieu de 11, 2,1 civilisations détruites au lieu de 0,6, une partie sur huit finit à deux civilisations.

## 7. Assets

Les sprites de `resources/` suffisent : terrains et surcouches en 60×60 avec transparence (dont la pollution), unités en 30×30 environ (terre, mer, air), ville en 30×30.

Dessinés au canvas, sans sprite :

- carré à la couleur de la civ derrière l'unité et la ville, taille de la ville, étoile de la capitale, enceinte de pierre crénelée autour d'une ville à murailles ;
- marqueurs d'ordre (F fortifiée, S sentinelle, R route, I irrigation, M mine, P dépollution), point jaune des vétérans ;
- sentinelle grisée et hachurée, unité fortifiée à bordure épaisse ;
- rivières, routes et voies ferrées, reliées de case en case (les sprites `river_overlay` et `route` ne se raccordent pas) ; une voie ferrée est un trait fin barré de traverses, comme sur les cartes, tracé par-dessus les routes ;
- huttes, forteresses, territoires, brouillard.

En mer, la case montre le navire et non ses passagers. Les transitions de côte ne sont pas traitées.

## 8. Conventions

- Tout identifiant de config est en `snake_case` et sert de clé partout (code, sérialisation, client).
- Une règle de jeu correspond à une fonction testable, avec la source citée quand elle vient d'OpenCivOne.
- L'IA ne lit le jeu qu'à travers `PlayerView` (seule exception : les barbares, qui ne sont pas une civilisation).
- Un paramètre d'IA va dans `ai.yaml`, un paramètre de règle dans `game.yaml`.
- La mémoire d'un contrôleur ne contient que des données simples (JSON), pour entrer dans les sauvegardes.

## 9. Écarts volontaires par rapport à Civ 1

| Écart | Raison |
|---|---|
| IA réécrite, honnête, sans bonus | Décisions de conception |
| Formule de mécontentement du joueur humain appliquée à toutes les civs | L'original en a une plus clémente pour l'IA |
| Placement des citoyens par un « maire » à poids configurables | La règle d'origine laisse les grandes villes sans production |
| Une ville de taille 1 ne peut pas produire de colons | L'original la dissout, ou offre le colon à une civ d'une seule ville |
| Score de site : la case de la ville compte quatre fois | L'original donne ce poids à la case au nord, par erreur d'index |
| Contact : guerre tant qu'aucun traité n'est signé, sans écran de négociation | Ni tribut ni échange de techs, pour l'IA comme pour le joueur |
| Le joueur voit ses chances avant d'attaquer | Le moteur sait les calculer ; l'original les cache |
| Une unité envoyée quelque part (« aller à ») n'attaque jamais d'elle-même | Le joueur décide de chaque combat |
| Les niveaux de difficulté ne changent que la civilisation du joueur | L'IA reste sans bonus ni malus |
| Vente d'un bâtiment : un or par bouclier, un bâtiment par ville et par tour | Même prix que la vente forcée de l'original |
| Trésor vide : le bâtiment vendu est celui dont l'empire a le moins besoin (ce qu'il rapporte à sa ville, moins son entretien), pas celui dont l'entretien tombe | L'original vend celui dont l'entretien fait passer le trésor sous zéro, quel qu'il soit : des Universités et des Cathédrales partaient avant des Casernes inutiles |
| Le maire replace tous les citoyens quand la ville grandit ou rétrécit | Les retouches à la main du joueur valent jusque-là |
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

## 10. Limites connues

- Diplomate désactivé (ambassade, vol de tech, sabotage non codés).
- Pas de guerre civile à la prise d'une capitale, pas de catastrophes aléatoires, pas de pillage.
- Le maire n'utilise que des amuseurs (ni percepteurs ni savants).
- L'IA ne construit pas de forteresses et ne construit pas de porte-avions (le moteur les gère).
- Le bombardier peut attaquer plusieurs fois par tour ; le sous-marin n'est pas invisible ; les chasseurs n'interceptent pas pendant le tour adverse.
- Les invasions par mer sont rares : l'IA n'en lance que si elle n'a aucune cible accessible à pied et se juge plus forte.
- La course à l'espace clôt en général la partie avant que l'arme nucléaire et le réchauffement n'aient pesé.
- Un test joue une partie entière et dure environ une minute (`python -m pytest -m "not slow"` pour l'éviter).
- L'IA n'a été réglée que contre elle-même : son niveau face à un joueur humain n'a pas été mesuré.
- Mode jeu : un seul joueur humain ; pas de pillage ; les unités débarquées par un navire restent endormies jusqu'à ce que le joueur les réveille ; une seule sauvegarde automatique, écrasée tous les cinq tours.
