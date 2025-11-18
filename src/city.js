class City {
  constructor(id, name, x, y, population = 1, civId = 1) {
    this.id = id;
    this.name = name;
    this.x = x;
    this.y = y;
    this.population = population;
    this.civId = civId;
    this.food = 0; // Current food stored in the city
    this.production = 0; // Current production stored in the city
    this.culture = 0; // Current culture accumulated in the city
    this.foodNeeded = 2; // Food needed to grow population (base)
    this.cultureNeeded = 10; // Culture needed for territory expansion (base)
    this.utilizedTiles = []; // Array of {x, y} coordinates of utilized tiles
    this.territoryTiles = []; // Array of {x, y} coordinates of additional territory tiles (from culture expansion)
  }

  // Calculate resources generated based on utilized tiles
  calculateFoodAndProduction(gameTerrainMap) {
    let totalFood = 0;
    let totalProduction = 0;

    // Sum resources from each utilized tile
    this.utilizedTiles.forEach(tile => {
      const terrainType = gameTerrainMap[tile.y][tile.x];
      const terrainInfo = TERRAIN_TYPES[terrainType];
      totalFood += terrainInfo.food;
      totalProduction += terrainInfo.production;
    });

    return {
      food: totalFood,
      production: totalProduction
    };
  }

  // Update city - accumulate resources and grow population
  update(gameTerrainMap, allCities) {
    const { food, production } = this.calculateFoodAndProduction(gameTerrainMap);

    this.food += food;
    this.production += production;
    this.culture += 2; // Produce 2 culture points per turn

    // Check if population can grow
    if (this.food >= this.foodNeeded) {
      this.population += 1;
      this.food = 0; // Reset food level to 0
      this.foodNeeded += 10; // Increase food needed by 10 for next growth

      // Add new utilized tile if available
      this.addUtilizedTile(gameTerrainMap, allCities);
    }

    // Check if culture reaches threshold for territory expansion
    if (this.culture >= this.cultureNeeded) {
      this.culture = 0; // Reset culture level to 0
      this.cultureNeeded += 10; // Increase culture needed by 10 for next expansion

      // Add new territory tile if available
      this.addTerritoryTile(gameTerrainMap, allCities);
    }
  }

  // Check if a given tile is within this city's territory (adjacent or city tile itself, or expanded territory)
  isInTerritory(x, y) {
    // Check base territory (1 square radius)
    const dx = Math.abs(x - this.x);
    const dy = Math.abs(y - this.y);
    if (dx <= 1 && dy <= 1) return true;

    // Check expanded territory tiles
    return this.territoryTiles.some(tile => tile.x === x && tile.y === y);
  }

  // Check if a given tile is on the border of this city's territory
  isOnBorder(x, y, allCities) {
    if (!this.isInTerritory(x, y)) return false;

    // Check all 4 adjacent tiles (not diagonals)
    const adjacentTiles = [
      { x: x - 1, y: y },
      { x: x + 1, y: y },
      { x: x, y: y - 1 },
      { x: x, y: y + 1 }
    ];

    // Check if any adjacent tile is outside this city's territory
    return adjacentTiles.some(tile => {
      // Check map bounds
      if (tile.x < 0 || tile.x >= 100 || tile.y < 0 || tile.y >= 100) {
        return true; // Map edge
      }
      // Check if not in any city's territory
      return !allCities.some(city => city.isInTerritory(tile.x, tile.y));
    });
  }

  // Check if a tile is utilized by this city
  isTileUtilized(x, y) {
    return this.utilizedTiles.some(tile => tile.x === x && tile.y === y);
  }

  // Check if a tile is part of expanded territory
  isTerritoryTile(x, y) {
    return this.territoryTiles.some(tile => tile.x === x && tile.y === y);
  }

  // Initialize utilized tiles when city is founded - city tile + best tile
  initializeUtilizedTiles(terrain, allCities) {
    this.utilizedTiles = [];
    // Always add the city tile itself
    this.utilizedTiles.push({ x: this.x, y: this.y });
    // Then add the best adjacent tile if available
    const bestTile = this.selectBestTile(terrain, allCities);
    if (bestTile) {
      this.utilizedTiles.push(bestTile);
    }
  }

  // Select the best unutilized tile in the territory
  selectBestTile(terrain, allCities) {
    const availableTiles = [];

    // Get all tiles in base territory (distance 1)
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        const tx = this.x + dx;
        const ty = this.y + dy;

        if (tx >= 0 && tx < 100 && ty >= 0 && ty < 100) {
          // Only add if not already utilized by any city
          const isUtilizedByOtherCity = allCities.some(city => city.isTileUtilized(tx, ty));
          if (!isUtilizedByOtherCity) {
            const terrainType = terrain[ty][tx];
            const terrainInfo = TERRAIN_TYPES[terrainType];
            const value = terrainInfo.food + terrainInfo.production;
            availableTiles.push({ x: tx, y: ty, value, food: terrainInfo.food, production: terrainInfo.production });
          }
        }
      }
    }

    // Add all expanded territory tiles that are not utilized by any city
    this.territoryTiles.forEach(tile => {
      const isUtilizedByOtherCity = allCities.some(city => city.isTileUtilized(tile.x, tile.y));
      if (!isUtilizedByOtherCity) {
        const terrainType = terrain[tile.y][tile.x];
        const terrainInfo = TERRAIN_TYPES[terrainType];
        const value = terrainInfo.food + terrainInfo.production;
        availableTiles.push({ x: tile.x, y: tile.y, value, food: terrainInfo.food, production: terrainInfo.production });
      }
    });

    if (availableTiles.length === 0) return null;

    // Sort by value descending, then by food descending (tiebreaker)
    availableTiles.sort((a, b) => {
      if (b.value !== a.value) return b.value - a.value;
      return b.food - a.food;
    });

    return { x: availableTiles[0].x, y: availableTiles[0].y };
  }

  // Select the best tile within distance 2 for territory expansion
  selectBestTerritoryTile(terrain, allCities) {
    const expandableTiles = [];

    // Get all tiles within distance 2 (Manhattan or Chebyshev distance)
    for (let dx = -2; dx <= 2; dx++) {
      for (let dy = -2; dy <= 2; dy++) {
        const tx = this.x + dx;
        const ty = this.y + dy;

        // Skip if out of bounds
        if (tx < 0 || tx >= 100 || ty < 0 || ty >= 100) continue;

        // Skip if already in base territory or already expanded territory
        const baseDx = Math.abs(tx - this.x);
        const baseDy = Math.abs(ty - this.y);
        if (baseDx <= 1 && baseDy <= 1) continue;
        if (this.territoryTiles.some(tile => tile.x === tx && tile.y === ty)) continue;

        // Check if tile belongs to another city's territory
        const belongsToOtherCity = allCities.some(city =>
          city.id !== this.id && city.isInTerritory(tx, ty)
        );
        if (belongsToOtherCity) continue;

        // Check if tile is already utilized by any city
        const isUtilizedByAnyCity = allCities.some(city => city.isTileUtilized(tx, ty));
        if (isUtilizedByAnyCity) continue;

        // Get tile value
        const terrainType = terrain[ty][tx];
        const terrainInfo = TERRAIN_TYPES[terrainType];
        const value = terrainInfo.food + terrainInfo.production;
        expandableTiles.push({ x: tx, y: ty, value, food: terrainInfo.food, production: terrainInfo.production });
      }
    }

    if (expandableTiles.length === 0) return null;

    // Sort by value descending, then by food descending (tiebreaker)
    expandableTiles.sort((a, b) => {
      if (b.value !== a.value) return b.value - a.value;
      return b.food - a.food;
    });

    return { x: expandableTiles[0].x, y: expandableTiles[0].y };
  }

  // Called when culture reaches threshold - add new territory tile if available
  addTerritoryTile(terrain, allCities) {
    const bestTile = this.selectBestTerritoryTile(terrain, allCities);
    if (bestTile) {
      this.territoryTiles.push(bestTile);
    }
  }

  // Called when culture reaches threshold - add new territory tile if available
  addUtilizedTile(terrain, allCities) {
    if (this.utilizedTiles.length < this.population) {
      const bestTile = this.selectBestTile(terrain, allCities);
      if (bestTile) {
        this.utilizedTiles.push(bestTile);
      }
    }
  }

  // Get food and production per turn based on utilized tiles
  getProductionPerTurn(gameTerrainMap) {
    let totalFood = 0;
    let totalProduction = 0;

    this.utilizedTiles.forEach(tile => {
      const terrainType = gameTerrainMap[tile.y][tile.x];
      const terrainInfo = TERRAIN_TYPES[terrainType];
      totalFood += terrainInfo.food;
      totalProduction += terrainInfo.production;
    });

    return { food: totalFood, production: totalProduction };
  }

  // Static method to create a new city from a plain object
  static fromObject(obj) {
    const city = new City(obj.id, obj.name, obj.x, obj.y, obj.population, obj.civId, obj.civId);
    city.food = obj.food || 0;
    city.production = obj.production || 0;
    city.culture = obj.culture || 0;
    city.foodNeeded = obj.foodNeeded || 2;
    city.cultureNeeded = obj.cultureNeeded || 10;
    city.utilizedTiles = obj.utilizedTiles || [];
    city.territoryTiles = obj.territoryTiles || [];
    return city;
  }
}

// Expose the class to the global scope
window.City = City;

