const assert=require("node:assert/strict");
const test=require("node:test");
const fs=require("node:fs");
const ts=require("typescript");
function loadTypeScript(path){
 const source=fs.readFileSync(path,"utf8");
 const code=ts.transpileModule(source,{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}
 }).outputText;
 const m={exports:{}};
 new Function("module","exports",code)(m,m.exports);
 return m.exports;
}
const {lonLatToSirgasUtm}=loadTypeScript("lib/utm-sirgas-preview.ts");
const {evaluatePs4Controls}=loadTypeScript("lib/ps4-quality.ts");
test("conversão SIRGAS2000 / UTM 22N reproduz o marco M578 do relatório",()=>{
 const p=lonLatToSirgasUtm(-50.87456336,0.40862148);
 assert.equal(p.zone,22);assert.equal(p.hemisphere,"N");
 assert.ok(Math.abs(p.easting_m-513957.616)<0.10,JSON.stringify(p));
 assert.ok(Math.abs(p.northing_m-45165.068)<0.10,JSON.stringify(p));
});
test("diagnóstico PS4 não transforma poucos checkpoints em laudo de acurácia",()=>{
 const controls=Array.from({length:4},(_,i)=>({
  id:"P"+i,image_lon:-50.9+i*.001,image_lat:.4+(i%2)*.001,
  reference_lon:-50.9+i*.001,reference_lat:.4+(i%2)*.001,
 }));
 const r=evaluatePs4Controls(controls);
 assert.equal(r.status,"INSUFICIENTE");
 assert.equal(r.preliminary_criterion_met,false);
 assert.equal(r.rmse_m,0);
});
test("diagnóstico PS4 com 20 pontos independentes ainda requer revisão RT",()=>{
 const controls=Array.from({length:20},(_,i)=>{
  const lon=-50.95+(i%5)*.002,lat=.39+Math.floor(i/5)*.002;
  return {id:"C"+i,image_lon:lon+0.000001,image_lat:lat,
   reference_lon:lon,reference_lat:lat};
 });
 const r=evaluatePs4Controls(controls);
 assert.equal(r.status,"REVISAO_RT");
 assert.equal(r.quadrant_count,4);
 assert.ok(r.rmse_m<3);
 assert.equal(r.preliminary_criterion_met,true);
});
test("IDs duplicados em checkpoints são rejeitados",()=>{
 assert.throws(()=>evaluatePs4Controls([
  {id:"C1",image_lon:-51,image_lat:0,reference_lon:-51,reference_lat:0},
  {id:"C1",image_lon:-51,image_lat:0,reference_lon:-51,reference_lat:0},
 ]),/duplicados/);
});
