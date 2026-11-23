// node frontend/src/gridgeom.test.mjs — checks the map tools' maths
import assert from "node:assert/strict";
import { areaCells, distanceFt } from "./gridgeom.js";

assert.equal(distanceFt({ x: 0, y: 0 }, { x: 3, y: 4 }), 20); // 5e: diagonals are 5 ft
assert.equal(distanceFt({ x: 0, y: 0 }, { x: 4, y: 4 }, "variant"), 30); // 5-10-5: 4 + 2
assert.equal(distanceFt({ x: 2, y: 2 }, { x: 2, y: 2 }), 0);
const me = { x: 5, y: 5 };
const ball = areaCells({ shape: "sphere", size: 20, origin: "point" }, me, { x: 10, y: 10 }, 30, 30);
assert.ok(ball.has("10,10") && ball.has("14,10") && ball.has("6,10") && !ball.has("15,10") && !ball.has("14,14")); // 20 ft = 4 squares
const cone = areaCells({ shape: "cone", size: 15, origin: "self" }, me, { x: 8, y: 5 }, 30, 30);
assert.ok(cone.has("6,5") && cone.has("8,5") && cone.has("8,6") && !cone.has("9,5") && !cone.has("5,5") && !cone.has("4,5"));
const line = areaCells({ shape: "line", size: 30, width: 5, origin: "self" }, me, { x: 5, y: 0 }, 30, 30);
assert.equal(line.size, 5); // 5,4 .. 5,0 (the map ends)
assert.ok(line.has("5,0") && !line.has("6,4"));
const cube = areaCells({ shape: "cube", size: 15, origin: "self" }, me, { x: 9, y: 5 }, 30, 30);
assert.equal(cube.size, 9);
assert.ok(cube.has("6,4") && cube.has("8,6") && !cube.has("5,5"));
const box = areaCells({ shape: "cube", size: 10, origin: "point" }, me, { x: 2, y: 2 }, 30, 30);
assert.deepEqual([...box].sort(), ["1,1", "1,2", "2,1", "2,2"]);
console.log("gridgeom: all good");
