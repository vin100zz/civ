class City {
  constructor(id, name, x, y, population = 1, player = 1) {
    this.id = id;
    this.name = name;
    this.x = x;
    this.y = y;
    this.population = population;
    this.player = player;
    this.food = 0; // Current food stored in the city
    this.production = 0; // Current production stored in the city
    this.foodNeeded = 2; // Food needed to grow population (base)
    this.utilizedTiles = []; // Array of {x, y} coordinates of utilized tiles
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

    // Check if population can grow
    if (this.food >= this.foodNeeded) {
      this.population += 1;
      this.food = 0; // Reset food level to 0
      this.foodNeeded += 10; // Increase food needed by 10 for next growth

      // Add new utilized tile if available
      this.addUtilizedTile(gameTerrainMap, allCities);
    }
  }

  // Check if a given tile is within this city's territory (adjacent or city tile itself)
  isInTerritory(x, y) {
    const dx = Math.abs(x - this.x);
    const dy = Math.abs(y - this.y);
    return dx <= 1 && dy <= 1;
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
    const territoryTiles = [];

    // Get all tiles in territory
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        const tx = this.x + dx;
        const ty = this.y + dy;

        if (tx >= 0 && tx < 100 && ty >= 0 && ty < 100 && this.isInTerritory(tx, ty)) {
          // Only add if not already utilized
          if (!this.isTileUtilized(tx, ty)) {
            const terrainType = terrain[ty][tx];
            const terrainInfo = TERRAIN_TYPES[terrainType];
            const value = terrainInfo.food + terrainInfo.production;
            territoryTiles.push({ x: tx, y: ty, value, food: terrainInfo.food, production: terrainInfo.production });
          }
        }
      }
    }

    if (territoryTiles.length === 0) return null;

    // Sort by value descending, then by food descending (tiebreaker)
    territoryTiles.sort((a, b) => {
      if (b.value !== a.value) return b.value - a.value;
      return b.food - a.food;
    });

    return { x: territoryTiles[0].x, y: territoryTiles[0].y };
  }

  // Called when population grows - add new utilized tile if available
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
    const city = new City(obj.id, obj.name, obj.x, obj.y, obj.population, obj.player);
    city.food = obj.food || 0;
    city.production = obj.production || 0;
    city.foodNeeded = obj.foodNeeded || 2;
    city.utilizedTiles = obj.utilizedTiles || [];
    return city;
  }
}

// Expose the class to the global scope
window.City = City;

