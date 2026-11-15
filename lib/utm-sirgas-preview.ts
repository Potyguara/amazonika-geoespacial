/** Aproximação cartográfica UTM/SIRGAS2000 (GRS80) para PRÉVIA PS4.
 * Não converte WGS84 orbital em coordenadas certificadas nem valida acurácia. */
export function lonLatToSirgasUtm(lon: number, lat: number) {
  if (!Number.isFinite(lon) || !Number.isFinite(lat) || lat < -80 || lat > 84 ||
      lon < -180 || lon > 180) throw new Error("Latitude/longitude inválida para UTM.");
  const zone = Math.floor((lon + 180) / 6) + 1;
  const a = 6378137, f = 1 / 298.257222101, k = 0.9996;
  const e2 = f * (2 - f), ep2 = e2 / (1 - e2);
  const phi = lat * Math.PI / 180, lambda = lon * Math.PI / 180;
  const lambda0 = ((zone - 1) * 6 - 180 + 3) * Math.PI / 180;
  const sin = Math.sin(phi), cos = Math.cos(phi), tan = Math.tan(phi);
  const N = a / Math.sqrt(1 - e2 * sin * sin);
  const T = tan * tan, C = ep2 * cos * cos, A = cos * (lambda - lambda0);
  const e4 = e2 * e2, e6 = e4 * e2;
  const M = a * (
    (1 - e2/4 - 3*e4/64 - 5*e6/256) * phi
    - (3*e2/8 + 3*e4/32 + 45*e6/1024) * Math.sin(2*phi)
    + (15*e4/256 + 45*e6/1024) * Math.sin(4*phi)
    - (35*e6/3072) * Math.sin(6*phi)
  );
  const east = k * N * (A + (1 - T + C)*A**3/6 +
    (5 - 18*T + T*T + 72*C - 58*ep2)*A**5/120) + 500000;
  const north = k * (M + N*tan*(A*A/2 +
    (5 - T + 9*C + 4*C*C)*A**4/24 +
    (61 - 58*T + T*T + 600*C - 330*ep2)*A**6/720)) +
    (lat < 0 ? 10000000 : 0);
  return { easting_m:east, northing_m:north, zone,
    hemisphere: lat < 0 ? "S" : "N", crs: "SIRGAS2000/UTM" };
}
