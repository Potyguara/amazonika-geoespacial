const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const ts=require("typescript");
const src=fs.readFileSync("lib/ps4-normal-altitude-preview.ts","utf8");
const mod={exports:{}};
new Function("module","exports",ts.transpileModule(src,{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}
}).outputText)(mod,mod.exports);
const {estimatePs4NormalAltitudes}=mod.exports;
test("V interpolado usa HN de marcos nos dois extremos",()=>{
 const result=estimatePs4NormalAltitudes(
  {longitude:-51,latitude:0,normal_height_m:6},
  [{longitude:-50.999,latitude:0}],
  {longitude:-50.998,latitude:0,normal_height_m:2},
 );
 assert.equal(result.length,1);
 assert.ok(Math.abs(result[0]-4)<0.01);
});
test("HN dos V não é fabricada quando não há HN de um marco",()=>{
 const result=estimatePs4NormalAltitudes(
  {longitude:-51,latitude:0,normal_height_m:null},
  [{longitude:-50.999,latitude:0}],
  {longitude:-50.998,latitude:0,normal_height_m:2},
 );
 assert.deepEqual(result,[null]);
});
