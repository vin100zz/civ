const { useState, useEffect, useRef } = React;
const { generateInitialTerrain } = window.mapGenerator;

// Constants
const TILE_SIZE = 50;
const VIEWPORT_WIDTH = 12;
const VIEWPORT_HEIGHT = 12;
const CIV_COLOR = '#ff00ff'; // Magenta color for your civilization

// Utility: convert hex color to {r,g,b}
function hexToRgb(hex) {
  if (!hex) return null;
  const h = hex.replace('#', '');
  const bigint = parseInt(h, 16);
  if (h.length === 3) {
    // shorthand e.g. #f0f -> ff00ff
    return {
      r: parseInt(h[0] + h[0], 16),
      g: parseInt(h[1] + h[1], 16),
      b: parseInt(h[2] + h[2], 16)
    };
  }
  return {
    r: (bigint >> 16) & 255,
    g: (bigint >> 8) & 255,
    b: bigint & 255
  };
}

// Utility: return rgba CSS string from hex and alpha
function hexToRgba(hex, alpha = 1) {
  const rgb = hexToRgb(hex);
  if (!rgb) return hex;
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`;
}

// Utility: choose black or white depending on background luminance
function contrastColor(hex) {
  const rgb = hexToRgb(hex);
  if (!rgb) return '#000';
  const luminance = (0.299 * rgb.r + 0.587 * rgb.g + 0.114 * rgb.b) / 255;
  return luminance > 0.6 ? '#000' : '#fff';
}

// Terrain and Unit Types
const TERRAIN_TYPES = {
  GRASSLAND: { name: 'Prairie', color: '#90EE90', food: 2, production: 1, movement: 1 },
  FOREST: { name: 'Forêt', color: '#228B22', food: 1, production: 2, movement: 2 },
  HILLS: { name: 'Collines', color: '#8B7355', food: 1, production: 2, movement: 2 },
  MOUNTAINS: { name: 'Montagnes', color: '#696969', food: 0, production: 1, movement: 3 },
  OCEAN: { name: 'Océan', color: '#4169E1', food: 1, production: 0, movement: 1 },
  DESERT: { name: 'Désert', color: '#F4A460', food: 0, production: 1, movement: 1 }
};

const UNIT_TYPES = {
  SETTLER: { name: 'Colon', attack: 0, defense: 1, movement: 1, icon: '🏠' },
  WARRIOR: { name: 'Guerrier', attack: 1, defense: 1, movement: 1, icon: '⚔️' }
};

const CivGame = () => {
  // Function to create initial game state
  const getInitialGameState = () => {
    const terrain = generateInitialTerrain();

    // Create 3 civilizations
    const initialCivs = [
      new Civilization(1, 'Yellow', '#FFFF00', 50),
      new Civilization(2, 'Green', '#00FF00', 50),
      new Civilization(3, 'Purple', '#ff00ff', 50)
    ];

    // Create cities for each civilization
    const initialCities = [
      new City(1, 'Yellcity', 3, 3, 1, 1),
      new City(2, 'Greencity', 4, 8, 1, 2),
      new City(3, 'Purpcity', 9, 7, 1, 3)
    ];

    // Initialize utilized tiles for each city
    initialCities.forEach(city => {
      city.initializeUtilizedTiles(terrain, initialCities);
    });

    return {
      terrain: terrain,
      selectedUnit: null,
      turn: 1,
      civilizations: initialCivs,
      cities: initialCities,
      units: [],
      resources: { food: 10, production: 10, gold: 50 },
      viewport: { x: 0, y: 0 }
    };
  };

  // Helper function to render repeated icons
  const renderIcons = (count, iconClass, color) => {
    return Array.from({ length: count }).map((_, i) => (
      <i key={i} className={iconClass} style={{ marginRight: '2px', color: color }}></i>
    ));
  };

  // Check if a tile is in the territory of any city
  const isTileInTerritory = (x, y) => {
    return gameState.cities.some(city => city.isInTerritory(x, y));
  };

  // Check if a tile is on the border of a territory
  const isTileOnBorder = (x, y) => {
    return gameState.cities.some(city => city.isOnBorder(x, y, gameState.cities));
  };

  // Check if a tile is utilized by any city
  const getTileUtilizedBy = (x, y) => {
    return gameState.cities.find(city => city.isTileUtilized(x, y));
  };

  // Check if a tile is an expanded territory tile of any city
  const getTerritoryTileBy = (x, y) => {
    return gameState.cities.find(city => city.isTerritoryTile(x, y));
  };

  // Get civilization by ID
  const getCivilizationById = (civId) => {
    return gameState.civilizations?.find(civ => civ.id === civId);
  };

  // Get city's civilization
  const getCitysCivilization = (city) => {
    return getCivilizationById(city.civId);
  };

  const [gameState, setGameState] = useState(() => {
    const savedState = localStorage.getItem('civGameState');
    if (savedState) {
      const state = JSON.parse(savedState);
      // Convert plain JSON objects back to Civilization instances
      state.civilizations = state.civilizations?.map(civObj => Civilization.fromObject(civObj)) || [];
      // Convert plain JSON objects back to City instances
      state.cities = state.cities.map(cityObj => City.fromObject(cityObj));
      return state;
    } else {
      return getInitialGameState();
    }
  });

  // Save game state to local storage
  useEffect(() => {
    localStorage.setItem('civGameState', JSON.stringify(gameState));
  }, [gameState]);

  const moveUnit = (dx, dy) => {
    if (!gameState.selectedUnit) return;

    const unit = gameState.units.find(u => u.id === gameState.selectedUnit);
    if (!unit || unit.movement <= 0) return;

    const newX = unit.x + dx;
    const newY = unit.y + dy;

    if (newX < 0 || newX >= mapGenerator.MAP_WIDTH || newY < 0 || newY >= mapGenerator.MAP_HEIGHT) return;

    const terrainType = TERRAIN_TYPES[gameState.terrain[newY][newX]];
    if (unit.movement < terrainType.movement) return;

    setGameState(prevState => {
      const newUnits = prevState.units.map(u =>
        u.id === prevState.selectedUnit
          ? { ...u, x: newX, y: newY, movement: u.movement - terrainType.movement }
          : u
      );

      const newXViewport = Math.max(0, Math.min(mapGenerator.MAP_WIDTH - VIEWPORT_WIDTH, newX - Math.floor(VIEWPORT_WIDTH / 2)));
      const newYViewport = Math.max(0, Math.min(mapGenerator.MAP_HEIGHT - VIEWPORT_HEIGHT, newY - Math.floor(VIEWPORT_HEIGHT / 2)));

      return {
        ...prevState,
        units: newUnits,
        viewport: { x: newXViewport, y: newYViewport }
      };
    });
  };

  const foundCity = () => {
    if (!gameState.selectedUnit) return;

    const unit = gameState.units.find(u => u.id === gameState.selectedUnit);
    if (!unit || unit.type !== 'SETTLER') return;

    const cityName = `Ville ${gameState.cities.length + 1}`;
    // Assign the city to civilization 1 (player civilization)
    const newCity = new City(gameState.cities.length + 1, cityName, unit.x, unit.y, 1, 1, 1);
    const newCities = [...gameState.cities, newCity];

    // Initialize utilized tiles for the new city
    newCity.initializeUtilizedTiles(gameState.terrain, newCities);

    setGameState(prevState => ({
      ...prevState,
      cities: newCities,
      units: prevState.units.filter(u => u.id !== prevState.selectedUnit),
      selectedUnit: null
    }));
  };

  const endTurn = () => {
    setGameState(prevState => {
      const newTurn = prevState.turn + 1;
      const newUnits = prevState.units.map(u => ({
        ...u,
        movement: UNIT_TYPES[u.type].movement
      }));

      // Update cities - manage resources at city level
      const newCities = prevState.cities.map(city => {
        city.update(prevState.terrain, prevState.cities);
        return city;
      });

      return {
        ...prevState,
        turn: newTurn,
        units: newUnits,
        cities: newCities
      };
    });
  };

  const resetGame = () => {
    if (confirm('Êtes-vous sûr de vouloir réinitialiser le jeu ? Toute progression sera perdue.')) {
      localStorage.removeItem('civGameState');
      // stop simulation if running
      if (simRef.current) {
        clearInterval(simRef.current);
        simRef.current = null;
      }
      setSimRunning(false);
      setGameState(getInitialGameState());
    }
  };

  const handleTileClick = (x, y) => {
    const unit = gameState.units.find(u => u.x === x && u.y === y);

    if (unit && unit.player === 1) {
      setGameState(prevState => ({
        ...prevState,
        selectedUnit: unit.id
      }));
    } else if (gameState.selectedUnit) {
      const selectedUnitObj = gameState.units.find(u => u.id === gameState.selectedUnit);
      if (selectedUnitObj) {
        const dx = x - selectedUnitObj.x;
        const dy = y - selectedUnitObj.y;
        if (Math.abs(dx) + Math.abs(dy) === 1) {
          moveUnit(dx, dy);
        }
      }
    }
  };

  const getVisibleMap = () => {
    const visible = [];
    for (let y = gameState.viewport.y; y < Math.min(gameState.viewport.y + VIEWPORT_HEIGHT, mapGenerator.MAP_HEIGHT); y++) {
      const row = [];
      for (let x = gameState.viewport.x; x < Math.min(gameState.viewport.x + VIEWPORT_WIDTH, mapGenerator.MAP_WIDTH); x++) {
        const unit = gameState.units.find(u => u.x === x && u.y === y);
        const city = gameState.cities.find(c => c.x === x && c.y === y);
        row.push({
          terrain: gameState.terrain[y][x],
          unit,
          city
        });
      }
      visible.push(row);
    }
    return visible;
  };

  const visibleMap = getVisibleMap();
  const selectedUnitData = gameState.units.find(u => u.id === gameState.selectedUnit);

  // Simulation mode: runs endTurn every 200ms when active
  const [simRunning, setSimRunning] = useState(false);
  const simRef = useRef(null);

  // Toggle simulation on/off
  const toggleSimulation = () => {
    if (simRunning) {
      // stop
      if (simRef.current) {
        clearInterval(simRef.current);
        simRef.current = null;
      }
      setSimRunning(false);
    } else {
      // start
      setSimRunning(true);
      // use setInterval to call endTurn every 200ms
      simRef.current = setInterval(() => {
        // call existing endTurn function
        endTurn();
      }, 200);
    }
  };

  // Ensure simulation stops when unmounting
  useEffect(() => {
    return () => {
      if (simRef.current) {
        clearInterval(simRef.current);
        simRef.current = null;
      }
    };
  }, []);

  return (
    <div className="w-full h-screen bg-gray-900 text-white p-4 flex flex-col">
      <div className="bg-gray-800 rounded-lg p-4 mb-4 flex justify-between items-center">
        <div className="flex gap-4 items-center">
          <div>Tour: <span className="font-bold text-yellow-400">{gameState.turn}</span></div>
          <div className="border-l border-gray-600 pl-4">
            {gameState.civilizations?.map(civ => (
              <div key={civ.id} className="inline-block mr-3 px-3 py-1 rounded" style={{ backgroundColor: civ.color, color: civ.color === '#FFFF00' ? '#000' : '#fff' }}>
                <span className="font-bold">{civ.name}</span>: <i className="fas fa-coins" style={{ marginRight: '4px', color: '#FFD700' }}></i><span>{civ.gold}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={endTurn}
            className="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded font-bold cursor-pointer"
          >
            Fin du tour
          </button>
          <button
            onClick={toggleSimulation}
            className={`px-4 py-2 rounded font-bold cursor-pointer ${simRunning ? 'bg-green-600 hover:bg-green-700' : 'bg-gray-600 hover:bg-gray-500'}`}
          >
            {simRunning ? 'Arrêter' : 'Simuler'}
          </button>
          <button
            onClick={resetGame}
            className="bg-red-600 hover:bg-red-700 px-6 py-2 rounded font-bold cursor-pointer"
          >
            Réinitialiser
          </button>
        </div>
      </div>

      <div className="flex gap-4 flex-1">
        <div className="bg-gray-800 rounded-lg p-4 flex-1">
          {/* map wrapper: position relative so absolute labels can be placed over/around tiles */}
          <div className="overflow-visible" style={{ position: 'relative', overflow: 'visible' }}>
            {visibleMap.map((row, y) => (
              <div key={y + gameState.viewport.y} className="flex">
                {row.map((tile, x) => {
                  const actualX = x + gameState.viewport.x;
                  const actualY = y + gameState.viewport.y;
                  const terrainInfo = TERRAIN_TYPES[tile.terrain];
                  const isSelected = tile.unit && tile.unit.id === gameState.selectedUnit;
                  // Prepare label colors based on city's civilization
                  let civForLabel = null;
                  if (tile.city) civForLabel = getCitysCivilization(tile.city);
                  const labelBg = hexToRgba(civForLabel?.color || '#ffffff', 0.9);
                  // always use black text for city labels per user's request
                  const labelColor = '#000';

                  return (
                    <div
                      key={`${actualX}-${actualY}`}
                      onClick={() => handleTileClick(actualX, actualY)}
                      className={`relative cursor-pointer ${isTileOnBorder(actualX, actualY) ? 'border-2' : 'border'} border-gray-700 ${isSelected ? 'ring-2 ring-yellow-400' : ''}`}
                      style={{
                        width: TILE_SIZE,
                        height: TILE_SIZE,
                        backgroundColor: tile.city ? (getCitysCivilization(tile.city)?.color || '#808080') : terrainInfo.color,
                        overflow: 'visible',
                        ...(isTileOnBorder(actualX, actualY) && { borderColor: getCitysCivilization(gameState.cities.find(c => c.isInTerritory(actualX, actualY)))?.color })
                      }}
                    >
                      {/* Terrain resources overlay */}
                      {!(tile.city && tile.city.x === actualX && tile.city.y === actualY) && (
                        <div className="absolute top-1 left-1 text-xs font-semibold opacity-60 pointer-events-none leading-tight">
                          <div>{renderIcons(terrainInfo.food, 'fas fa-apple-alt', '#22c55e')}</div>
                          <div>{renderIcons(terrainInfo.production, 'fas fa-hammer', '#9ca3af')}</div>
                        </div>
                      )}

                      {/* Utilized tile indicator */}
                      {getTileUtilizedBy(actualX, actualY) && !(tile.city && tile.city.x === actualX && tile.city.y === actualY) && (
                        <div className="absolute top-1 right-1 text-lg pointer-events-none">
                          <i className="fas fa-check-circle text-white" style={{ textShadow: '0 0 3px black' }}></i>
                        </div>
                      )}

                      {/* Territory expansion tile overlay */}
                      {getTerritoryTileBy(actualX, actualY) && !getTileUtilizedBy(actualX, actualY) && (
                        <div
                          className="absolute inset-0"
                          style={{ backgroundColor: getCitysCivilization(gameState.cities.find(c => c.isTerritoryTile(actualX, actualY)))?.color, opacity: 0.15 }}
                        />
                      )}

                      {tile.city && (
                        <>
                          <div
                            className="absolute inset-0 flex flex-col items-center justify-center"
                            style={{ backgroundColor: getCitysCivilization(tile.city)?.color, opacity: 0.3 }}
                          >
                            <div className="flex-1 flex items-center justify-center w-full" style={{ marginBottom: '12px' }}>
                              <div style={{ backgroundColor: 'rgba(0,0,0,0.65)', padding: '2px 8px', borderRadius: 6 }}>
                                <div className="text-white text-3xl font-extrabold" style={{ textShadow: '0 0 6px rgba(0,0,0,0.7)', lineHeight: '1' }}>
                                  {tile.city.population}
                                </div>
                              </div>
                            </div>
                          </div>
                          {/* Label juste sous la tuile */}
                          <div style={{ position: 'absolute', left: '50%', bottom: -6, transform: 'translateX(-50%)', whiteSpace: 'nowrap', backgroundColor: labelBg, color: labelColor, padding: '2px 4px', borderRadius: 6, fontWeight: 700, fontSize: '12px', lineHeight: '1', zIndex: 1000, pointerEvents: 'none', boxShadow: '0 1px 3px rgba(0,0,0,0.3)' }}>
                            {tile.city.name}
                          </div>
                        </>
                      )}
                      {tile.unit && (
                        <div
                          className="absolute inset-0 flex items-center justify-center text-2xl"
                          style={{ backgroundColor: getCivilizationById(1)?.color, opacity: 0.3 }}
                        >
                          {UNIT_TYPES[tile.unit.type].icon}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}

            {/* city-labels removed: labels are rendered per-tile to ensure exact positioning */}
          </div>

          <div className="w-64 bg-gray-800 rounded-lg p-4 space-y-4 flex flex-col">
            <div>
              <h3 className="text-lg font-bold mb-2">Unité sélectionnée</h3>
              {selectedUnitData ? (
                <div className="bg-gray-700 p-3 rounded space-y-2">
                  <div className="font-bold">{UNIT_TYPES[selectedUnitData.type].name}</div>
                  <div className="text-sm">Position: ({selectedUnitData.x}, {selectedUnitData.y})</div>
                  <div className="text-sm">Mouvement: {selectedUnitData.movement}/{UNIT_TYPES[selectedUnitData.type].movement}</div>

                  <div className="space-y-1 mt-3">
                    <button
                      onClick={() => moveUnit(0, -1)}
                      className="w-full bg-gray-600 hover:bg-gray-500 p-2 rounded flex items-center justify-center cursor-pointer"
                    >
                      ▲
                    </button>
                    <div className="flex gap-1">
                      <button
                        onClick={() => moveUnit(-1, 0)}
                        className="flex-1 bg-gray-600 hover:bg-gray-500 p-2 rounded flex items-center justify-center cursor-pointer"
                      >
                        ◀
                      </button>
                      <button
                        onClick={() => moveUnit(1, 0)}
                        className="flex-1 bg-gray-600 hover:bg-gray-500 p-2 rounded flex items-center justify-center cursor-pointer"
                      >
                        ▶
                      </button>
                    </div>
                    <button
                      onClick={() => moveUnit(0, 1)}
                      className="w-full bg-gray-600 hover:bg-gray-500 p-2 rounded flex items-center justify-center cursor-pointer"
                    >
                      ▼
                    </button>
                  </div>

                  {selectedUnitData.type === 'SETTLER' && (
                    <button
                      onClick={foundCity}
                      className="w-full bg-green-600 hover:bg-green-700 p-2 rounded mt-2 flex items-center justify-center gap-2 cursor-pointer"
                    >
                      ➕ Fonder une ville
                    </button>
                  )}
                </div>
              ) : (
                <div className="text-gray-500 text-sm">Aucune unité sélectionnée</div>
              )}
            </div>

            <div className="flex-1 flex flex-col overflow-hidden">
              <h3 className="text-lg font-bold mb-2">Villes ({gameState.cities.length})</h3>
              <div className="space-y-2 overflow-y-auto flex-1">
                {gameState.cities.map(city => {
                  const perTurn = city.getProductionPerTurn(gameState.terrain);
                  // consumption: 2 food per population per turn
                  const consumption = 2 * city.population;
                  const netFoodPerTurn = perTurn.food - consumption;
                  const civ = getCitysCivilization(city);
                  return (
                    <div key={city.id} className="bg-gray-700 p-2 rounded text-sm">
                      <div className="font-bold flex items-center gap-2">
                        <div style={{ width: '16px', height: '16px', backgroundColor: civ?.color, borderRadius: '3px' }}></div>
                        {city.name}
                      </div>
                      <div>Population: {city.population}</div>
                      <div className="text-xs"><i className="fas fa-apple-alt" style={{marginRight: '4px', color: '#22c55e'}}></i>Nourriture: {Math.floor(city.food)}/{city.foodNeeded} ({netFoodPerTurn >= 0 ? '+' + netFoodPerTurn : netFoodPerTurn}/tour)</div>
                      <div className="text-xs"><i className="fas fa-hammer" style={{marginRight: '4px', color: '#9ca3af'}}></i>Production: {Math.floor(city.production)} (+{perTurn.production}/tour)</div>
                      <div className="text-xs"><i className="fas fa-music" style={{marginRight: '4px', color: '#a78bfa'}}></i>Culture: {Math.floor(city.culture)}/{city.cultureNeeded} (+2/tour)</div>
                      <div className="text-xs text-gray-400">({city.x}, {city.y})</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<CivGame />);
