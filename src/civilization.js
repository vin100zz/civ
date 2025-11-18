class Civilization {
  constructor(id, name, color, initialGold = 50) {
    this.id = id;
    this.name = name;
    this.color = color;
    this.gold = initialGold;
  }

  // Static method to create a civilization from a plain object
  static fromObject(obj) {
    const civ = new Civilization(obj.id, obj.name, obj.color, obj.gold);
    return civ;
  }
}

// Expose the class to the global scope
window.Civilization = Civilization;

