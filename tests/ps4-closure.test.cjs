// Teste isolado do algoritmo PS4 — não envolve banco, API ou serviços de produção.
const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const ts = require("typescript");
const source = fs.readFileSync("lib/ps4-closure.ts", "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const moduleObject = { exports: {} };
new Function("module", "exports", compiled)(moduleObject, moduleObject.exports);
const { buildPs4Closure } = moduleObject.exports;

const M = [
  {name:"M1",longitude:-51,latitude:0},
  {name:"M2",longitude:-50.9,latitude:0},
  {name:"M3",longitude:-50.9,latitude:0.1},
  {name:"M4",longitude:-51,latitude:0.1},
];
const V = [
  {name:"A-V-0001",longitude:-50.97,latitude:-0.01},
  {name:"A-V-0002",longitude:-50.93,latitude:-0.01},
];

test("insere V entre marcos consecutivos e fecha um anel GeoJSON",()=>{
  const result=buildPs4Closure(M,V,"M1","M2");
  assert.equal(result.valid,true,result.message);
  assert.deepEqual(result.names,["M1","A-V-0001","A-V-0002","M2","M3","M4"]);
  assert.equal(result.geometry.coordinates[0].length,7);
  assert.deepEqual(result.geometry.coordinates[0][0],result.geometry.coordinates[0].at(-1));
});
test("recusa marcos não consecutivos",()=>{
  assert.equal(buildPs4Closure(M,V,"M1","M3").valid,false);
});
test("recusa menos de dois V",()=>{
  assert.equal(buildPs4Closure(M,V.slice(0,1),"M1","M2").valid,false);
});
test("recusa autointerseção",()=>{
  const crossed=[
    {name:"A-V-0001",longitude:-50.91,latitude:0.09},
    {name:"A-V-0002",longitude:-50.99,latitude:0.09},
  ];
  assert.equal(buildPs4Closure(M,crossed,"M1","M2").valid,false);
});
test("recusa códigos duplicados",()=>{
  assert.equal(buildPs4Closure(M,[{...V[0],name:"M3"},V[1]],"M1","M2").valid,false);
});
