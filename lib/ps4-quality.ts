/** Diagnóstico de exatidão externa de uma cena PS4 por pontos GNSS INDEPENDENTES.
 * Não equivale a certificação automática, nem utiliza o GSD como precisão. */
export type Ps4Control = {
  id: string; image_lon: number; image_lat: number;
  reference_lon: number; reference_lat: number;
};
export type Ps4Quality = {
  checkpoints: number; rmse_m: number; mean_bias_m: number;
  p90_m: number; max_m: number; quadrant_count: number;
  preliminary_criterion_met: boolean; status: "REVISAO_RT"|"INSUFICIENTE";
};
export function evaluatePs4Controls(rows: Ps4Control[]): Ps4Quality {
  if (!rows.length || rows.length > 1000) throw new Error("Informe de 1 a 1000 pontos independentes.");
  const unique = new Set(rows.map(r=>r.id.trim().toUpperCase()));
  if(unique.size !== rows.length || unique.has(""))throw new Error("IDs vazios ou duplicados.");
  const radians=Math.PI/180;
  const centerLat=rows.reduce((sum,p)=>sum+p.reference_lat,0)/rows.length;
  const centerLon=rows.reduce((sum,p)=>sum+p.reference_lon,0)/rows.length;
  const latmin=Math.min(...rows.map(p=>p.reference_lat));
  const latmax=Math.max(...rows.map(p=>p.reference_lat));
  const lonmin=Math.min(...rows.map(p=>p.reference_lon));
  const lonmax=Math.max(...rows.map(p=>p.reference_lon));
  const q=new Set<number>();
  const residuals=rows.map(p=>{
    for(const val of [p.image_lon,p.image_lat,p.reference_lon,p.reference_lat])
      if(!Number.isFinite(val))throw new Error("Coordenadas de controle inválidas.");
    if(Math.abs(p.image_lon-p.reference_lon) > .01 ||
       Math.abs(p.image_lat-p.reference_lat) > .01)
      throw new Error("Discrepância maior que 1 km em "+p.id+"; verifique graus e orientação.");
    const dx=(p.image_lon-p.reference_lon)*radians*6378137*Math.cos(centerLat*radians);
    const dy=(p.image_lat-p.reference_lat)*radians*6335439;
    q.add((p.reference_lon>=centerLon?1:0)+(p.reference_lat>=centerLat?2:0));
    return {dx,dy,d:Math.hypot(dx,dy)};
  });
  const dist=residuals.map(p=>p.d).sort((a,b)=>a-b);
  const rmse=Math.sqrt(residuals.reduce((s,p)=>s+p.d*p.d,0)/rows.length);
  const bias=Math.hypot(residuals.reduce((s,p)=>s+p.dx,0)/rows.length,
    residuals.reduce((s,p)=>s+p.dy,0)/rows.length);
  const p90=dist[Math.max(0,Math.ceil(.9*dist.length)-1)];
  const max=dist[dist.length-1];
  const geographicSpread=latmax-latmin>.0001 && lonmax-lonmin>.0001;
  // Critério de TRIAGEM interno deliberadamente conservador; não é regra oficial SIGEF.
  const sufficient=rows.length>=20 && q.size===4 && geographicSpread;
  const meets=sufficient && rmse<=3 && p90<=3;
  return {
    checkpoints:rows.length, rmse_m:rmse, mean_bias_m:bias,
    p90_m:p90, max_m:max, quadrant_count:q.size,
    preliminary_criterion_met:meets,
    status:sufficient?"REVISAO_RT":"INSUFICIENTE",
  };
}
