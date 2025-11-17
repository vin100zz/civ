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
  }

  // Calculate resources generated based on population and terrain
  calculateProduction(terrainType) {
    const terrain = TERRAIN_TYPES[terrainType];
    return {
      food: terrain.food,
      production: terrain.production
    };
  }

  // Update city - accumulate resources and grow population
  update(terrainType) {
    const { food, production } = this.calculateProduction(terrainType);

    this.food += food;
    this.production += production;

    // Check if population can grow
    if (this.food >= this.foodNeeded) {
      this.population += 1;
      this.food = 0;
      this.foodNeeded += 10; // Increase food needed for next growth
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

  // Static method to create a new city from a plain object
  static fromObject(obj) {
    const city = new City(obj.id, obj.name, obj.x, obj.y, obj.population, obj.player);
    city.food = obj.food || 0;
    city.production = obj.production || 0;
    city.foodNeeded = obj.foodNeeded || 2;
    return city;
  }
}

// Expose the class to the global scope
window.City = City;

