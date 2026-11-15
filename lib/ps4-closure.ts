/** GEO-93 - previsualização de fecho PS4. Nunca constitui limite certificável. */
export type SimpleVertex = { name: string; longitude: number | null; latitude: number | null };
export type Ps4Vertex = { name: string; longitude: number; latitude: number };

export type Ps4ClosurePreview = {
  valid: boolean;
  message: string;
  geometry: { type: "Polygon"; coordinates: number[][][] } | null;
  names: string[];
};

const near = (a: number[], b: number[]) =>
  Math.abs(a[0] - b[0]) < 1e-10 && Math.abs(a[1] - b[1]) < 1e-10;
const cross = (a: number[], b: number[], c: number[]) =>
  (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
const intersects = (a: number[], b: number[], c: number[], d: number[]) => {
  const eps = 1e-13;
  const ab1 = cross(a,b,c), ab2 = cross(a,b,d);
  const cd1 = cross(c,d,a), cd2 = cross(c,d,b);
  if (Math.abs(ab1)<eps || Math.abs(ab2)<eps || Math.abs(cd1)<eps || Math.abs(cd2)<eps) {
    const within=(p:number[],q:number[],r:number[]) =>
      Math.min(p[0],r[0])-eps<=q[0] && q[0]<=Math.max(p[0],r[0])+eps &&
      Math.min(p[1],r[1])-eps<=q[1] && q[1]<=Math.max(p[1],r[1])+eps;
    return (Math.abs(ab1)<eps && within(a,c,b)) ||
      (Math.abs(ab2)<eps && within(a,d,b)) ||
      (Math.abs(cd1)<eps && within(c,a,d)) ||
      (Math.abs(cd2)<eps && within(c,b,d));
  }
  return ab1*ab2<0 && cd1*cd2<0;
};

export function buildPs4Closure(
  boundary: SimpleVertex[], draft: Ps4Vertex[], startName: string, endName: string,
): Ps4ClosurePreview {
  const fail = (message:string): Ps4ClosurePreview =>
    ({ valid:false, message, geometry:null, names:[] });
  if (boundary.length < 3) return fail("Importe ao menos três marcos de divisa antes do fechamento.");
  if (draft.length < 2) return fail("Marque pelo menos dois vértices V na feição natural.");
  const i=boundary.findIndex(p=>p.name===startName);
  if (i<0 || boundary[(i+1)%boundary.length]?.name!==endName)
    return fail("Selecione dois marcos consecutivos na ordem do perímetro (marco inicial → marco final).");
  const seq=[...boundary.slice(0,i+1),...draft,...boundary.slice(i+1)];
  if (seq.some(p=>p.longitude===null || p.latitude===null ||
    !Number.isFinite(p.longitude) || !Number.isFinite(p.latitude)))
    return fail("Existem coordenadas inválidas nos marcos ou nos vértices PS4.");
  const names=seq.map(p=>p.name);
  if (new Set(names.map(n=>n.toUpperCase())).size!==names.length)
    return fail("Existem identificadores duplicados no perímetro.");
  const coords=seq.map(p=>[Number(p.longitude), Number(p.latitude)]);
  if (coords.some((v,k)=>near(v,coords[(k+1)%coords.length])))
    return fail("Existem vértices consecutivos coincidentes; revise os cliques.");
  const n=coords.length;
  for(let a=0;a<n;a++)for(let b=a+1;b<n;b++) {
    if(b===a+1 || (a===0 && b===n-1))continue;
    if(intersects(coords[a],coords[(a+1)%n],coords[b],coords[(b+1)%n]))
      return fail("O fechamento apresenta cruzamento de segmentos. Corrija a sequência.");
  }
  const area=coords.reduce((acc,p,k)=>{
    const q=coords[(k+1)%n];return acc+p[0]*q[1]-q[0]*p[1];
  },0)/2;
  if(Math.abs(area)<1e-12)return fail("O polígono possui área nula ou insuficiente.");
  return {
    valid:true,
    message:"Prévia fechada e geometricamente consistente. Pendente de acurácia PS4 e validação do RT.",
    geometry:{type:"Polygon",coordinates:[[...coords,coords[0]]]},
    names,
  };
}
