class City {
  constructor(id, name, x, y, population = 1, player = 1) {
    this.id = id;
    this.name = name;
    this.x = x;
    this.y = y;
    this.population = population;
    this.player = player;
  }

  // Calculate resources based on population and terrain
  calculateProduction(terrainType) {
    const terrain = TERRAIN_TYPES[terrainType];
    return {
      food: terrain.food * this.population,
      production: terrain.production * this.population
    };
  }

  // Update city population based on food surplus
  update(foodSurplus) {
    if (foodSurplus > 0) {
      this.population += Math.floor(foodSurplus / 2);
    }
  }

  // Static method to create a new city from a plain object
  static fromObject(obj) {
    return new City(obj.id, obj.name, obj.x, obj.y, obj.population, obj.player);
  }
}

// Expose the class to the global scope
window.City = City;
