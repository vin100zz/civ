class MapGenerator {
  static MAP_WIDTH = 10;
  static MAP_HEIGHT = 10;

  static generateInitialTerrain(width = MapGenerator.MAP_WIDTH, height = MapGenerator.MAP_HEIGHT) {
    const map = [];
    for (let y = 0; y < height; y++) {
      const row = [];
      for (let x = 0; x < width; x++) {
        const rand = Math.random();
        let terrainType;
        if (rand < 0.4) terrainType = 'GRASSLAND';
        else if (rand < 0.6) terrainType = 'FOREST';
        else if (rand < 0.75) terrainType = 'HILLS';
        else if (rand < 0.85) terrainType = 'MOUNTAINS';
        else if (rand < 0.92) terrainType = 'OCEAN';
        else terrainType = 'DESERT';

        row.push(terrainType);
      }
      map.push(row);
    }
    return map;
  }
}

// Expose the class to the global scope
window.mapGenerator = MapGenerator;
