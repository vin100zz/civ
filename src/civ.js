const { useState, useEffect } = React;
const { generateInitialTerrain } = window.mapGenerator;

// Constants
const TILE_SIZE = 50;
const VIEWPORT_WIDTH = 12;
const VIEWPORT_HEIGHT = 10;
const CIV_COLOR = '#ff00ff'; // Magenta color for your civilization

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
  const [gameState, setGameState] = useState(() => {
    const savedState = localStorage.getItem('civGameState');
    if (savedState) {
      const state = JSON.parse(savedState);
      // Convert plain JSON objects back to City instances
      state.cities = state.cities.map(cityObj => City.fromObject(cityObj));
      return state;
    } else {
      return {
        terrain: generateInitialTerrain(),
        selectedUnit: null,
        turn: 1,
        cities: [],
        units: [
          { id: 1, type: 'SETTLER', x: 6, y: 7, movement: 1, player: 1 },
          { id: 2, type: 'SETTLER', x: 2, y: 3, movement: 1, player: 1 },
          { id: 3, type: 'WARRIOR', x: 7, y: 3, movement: 1, player: 1 }
        ],
        resources: { food: 10, production: 10, gold: 50 },
        viewport: { x: 0, y: 0 }
      };
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
    const newCity = new City(gameState.cities.length + 1, cityName, unit.x, unit.y, 1, 1);
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
      setGameState({
        terrain: generateInitialTerrain(),
        selectedUnit: null,
        turn: 1,
        cities: [],
        units: [
          { id: 1, type: 'SETTLER', x: 6, y: 7, movement: 1, player: 1 },
          { id: 2, type: 'SETTLER', x: 2, y: 3, movement: 1, player: 1 },
          { id: 3, type: 'WARRIOR', x: 7, y: 3, movement: 1, player: 1 }
        ],
        resources: { food: 10, production: 10, gold: 50 },
        viewport: { x: 0, y: 0 }
      });
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

  return (
    <div className="w-full h-screen bg-gray-900 text-white p-4 flex flex-col">
      <div className="bg-gray-800 rounded-lg p-4 mb-4 flex justify-between items-center">
        <div className="flex gap-6">
          <div>Tour: <span className="font-bold text-yellow-400">{gameState.turn}</span></div>
          <div>🏛️ Villes: <span className="font-bold">{gameState.cities.length}</span></div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={endTurn}
            className="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded font-bold cursor-pointer"
          >
            Fin du tour
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
          <div className="overflow-hidden">
            {visibleMap.map((row, y) => (
              <div key={y + gameState.viewport.y} className="flex">
                {row.map((tile, x) => {
                  const actualX = x + gameState.viewport.x;
                  const actualY = y + gameState.viewport.y;
                  const terrainInfo = TERRAIN_TYPES[tile.terrain];
                  const isSelected = tile.unit && tile.unit.id === gameState.selectedUnit;

                  return (
                    <div
                      key={`${actualX}-${actualY}`}
                      onClick={() => handleTileClick(actualX, actualY)}
                      className={`relative cursor-pointer ${isTileOnBorder(actualX, actualY) ? 'border-2' : 'border'} border-gray-700 ${isSelected ? 'ring-2 ring-yellow-400' : ''}`}
                      style={{
                        width: TILE_SIZE,
                        height: TILE_SIZE,
                        backgroundColor: terrainInfo.color,
                        ...(isTileOnBorder(actualX, actualY) && { borderColor: CIV_COLOR })
                      }}
                    >
                      {/* Terrain resources overlay */}
                      <div className="absolute top-1 left-1 text-xs font-semibold opacity-60 pointer-events-none leading-tight">
                        <div>{renderIcons(terrainInfo.food, 'fas fa-apple-alt', '#22c55e')}</div>
                        <div>{renderIcons(terrainInfo.production, 'fas fa-hammer', '#9ca3af')}</div>
                      </div>

                      {/* Utilized tile indicator */}
                      {getTileUtilizedBy(actualX, actualY) && (
                        <div className="absolute top-1 right-1 text-lg pointer-events-none">
                          <i className="fas fa-check-circle text-white" style={{ textShadow: '0 0 3px black' }}></i>
                        </div>
                      )}

                      {/* Territory expansion tile overlay */}
                      {getTerritoryTileBy(actualX, actualY) && !getTileUtilizedBy(actualX, actualY) && (
                        <div
                          className="absolute inset-0"
                          style={{ backgroundColor: CIV_COLOR, opacity: 0.15 }}
                        />
                      )}

                      {tile.city && (
                        <div
                          className="absolute inset-0 flex flex-col items-center justify-between"
                          style={{ backgroundColor: CIV_COLOR }}
                        >
                          <div className="flex-1 flex items-center justify-center w-full">
                            <div className="text-white text-lg font-bold">
                              {tile.city.population}
                            </div>
                          </div>
                          <div className="bg-white text-black text-xs px-1 rounded font-bold whitespace-nowrap overflow-hidden text-ellipsis w-full text-center">
                            {tile.city.name}
                          </div>
                        </div>
                      )}
                      {tile.unit && (
                        <div
                          className="absolute inset-0 flex items-center justify-center text-2xl"
                          style={{ backgroundColor: CIV_COLOR }}
                        >
                          {UNIT_TYPES[tile.unit.type].icon}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>

        <div className="w-64 bg-gray-800 rounded-lg p-4 space-y-4">
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

          <div>
            <h3 className="text-lg font-bold mb-2">Villes ({gameState.cities.length})</h3>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {gameState.cities.map(city => {
                const perTurn = city.getProductionPerTurn(gameState.terrain);
                return (
                  <div key={city.id} className="bg-gray-700 p-2 rounded text-sm">
                    <div className="font-bold">{city.name}</div>
                    <div>Population: {city.population}</div>
                    <div className="text-xs"><i className="fas fa-apple-alt" style={{marginRight: '4px', color: '#22c55e'}}></i>Nourriture: {Math.floor(city.food)}/{city.foodNeeded} (+{perTurn.food}/tour)</div>
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
  );
};

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<CivGame />);
