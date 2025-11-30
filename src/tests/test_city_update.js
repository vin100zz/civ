// Simple test harness to load city.js in Node and simulate update
const fs = require('fs');
const vm = require('vm');

// Load city.js content
const cityCode = fs.readFileSync(__dirname + '/../city.js', 'utf8');

// Prepare a sandbox with expected globals
const sandbox = {
  window: {},
  TERRAIN_TYPES: {
    GRASSLAND: { food: 2, production: 1 },
    FOREST: { food: 1, production: 2 }
  },
  console
};
vm.createContext(sandbox);
vm.runInContext(cityCode, sandbox);

const City = sandbox.window.City;
if (!City) {
  console.error('City class not found');
  process.exit(1);
}

// Create a simple terrain 5x5 with grassland
const terrain = Array.from({ length: 5 }, () => Array.from({ length: 5 }, () => 'GRASSLAND'));

// Create cities array dummy
const cities = [];

// Create a city at (2,2) with population 1 and foodNeeded 2 so that it will grow
const city = new City(1, 'TestCity', 2, 2, 1, 1);
// Ensure utilized tiles: city tile only
city.utilizedTiles = [{ x: 2, y: 2 }];
city.food = 2; // already has enough to grow (foodNeeded default 2)

console.log('Before update:', { population: city.population, food: city.food, utilized: city.utilizedTiles.length });
city.update(terrain, [city]);
console.log('After update:', { population: city.population, food: city.food, utilized: city.utilizedTiles.length });

// Now set up a city with extra utilized tile that gives food so growth then check
const city2 = new City(2, 'TestCity2', 1, 1, 1, 1);
city2.utilizedTiles = [{ x: 1, y: 1 }, { x: 2, y: 2 }];
city2.food = 1; // not enough yet
// the utilized tiles give food: city tile 2 + other tile (grassland) 2 => 4 total per calculate
console.log('Before update2:', { population: city2.population, food: city2.food, utilized: city2.utilizedTiles.length });
city2.update(terrain, [city2]);
console.log('After update2:', { population: city2.population, food: city2.food, utilized: city2.utilizedTiles.length });

