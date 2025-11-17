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
  calculateFoodProduction(terrainType) {
    const terrain = TERRAIN_TYPES[terrainType];
    return {
      food: terrain.food,
      production: terrain.production
    };
  }

  // Update city - accumulate resources and grow population
  endTurn(terrainType) {
    const { food, production } = this.calculateFoodProduction(terrainType);

    this.food += food;
    this.production += production;

    // Check if population can grow
    if (this.food >= this.foodNeeded) {
      this.population += 1;
      this.food = 0;
      this.foodNeeded += 10; // Increase food needed for next growth
    }
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
