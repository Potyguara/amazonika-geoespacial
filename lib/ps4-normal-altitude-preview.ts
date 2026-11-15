/** Altitude normal indicativa por interpolação ao LONGO da polilinha M–V–M.
 * Não mede relevo, não usa elevação da imagem e NÃO produz h para a ODS SIGEF.
 * Saída é somente HN ESTIMADA para consulta no rascunho técnico.
 */
export type PlanPoint = {longitude:number;latitude:number};
function distanceMeters(a:PlanPoint,b:PlanPoint):number{
  const rad=Math.PI/180,R=6371008.8;
  const dLat=(b.latitude-a.latitude)*rad,dLon=(b.longitude-a.longitude)*rad;
  const s=Math.sin(dLat/2)**2+
    Math.cos(a.latitude*rad)*Math.cos(b.latitude*rad)*Math.sin(dLon/2)**2;
  return 2*R*Math.asin(Math.min(1,Math.sqrt(s)));
}
export function estimatePs4NormalAltitudes(
  start:PlanPoint & {normal_height_m:number|null},
  virtuals:PlanPoint[],
  end:PlanPoint & {normal_height_m:number|null},
): Array<number|null>{
  if(!Number.isFinite(start.normal_height_m)||
     !Number.isFinite(end.normal_height_m)||
     start.normal_height_m===null||end.normal_height_m===null)
    return virtuals.map(()=>null);
  const path=[start,...virtuals,end];
  const segments=path.slice(1).map((p,i)=>distanceMeters(path[i],p));
  const total=segments.reduce((a,b)=>a+b,0);
  if(!Number.isFinite(total)||total<0.01)return virtuals.map(()=>null);
  let cumulative=0;
  return virtuals.map((_,i)=>{
    cumulative+=segments[i];
    return (start.normal_height_m as number)+
      ((end.normal_height_m as number)-(start.normal_height_m as number))*(cumulative/total);
  });
}
