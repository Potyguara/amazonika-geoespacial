export type LonLat = [number, number];

export type UTMInput = {
  easting: number;
  northing: number;
  zone: number;
  hemisphere: "N" | "S";
};

const WGS84_A = 6378137;
const WGS84_ECC_SQ = 0.00669437999014;
const K0 = 0.9996;

export function dmsToDecimal(
  degrees: number,
  minutes: number,
  seconds: number,
  hemisphere: "N" | "S" | "E" | "W",
): number {
  if (!Number.isFinite(degrees) || !Number.isFinite(minutes) || !Number.isFinite(seconds)) {
    throw new Error("Coordenada DMS inválida.");
  }
  if (minutes < 0 || minutes >= 60 || seconds < 0 || seconds >= 60) {
    throw new Error("Minutos e segundos devem estar entre 0 e 60.");
  }
  const absolute = Math.abs(degrees) + minutes / 60 + seconds / 3600;
  return hemisphere === "S" || hemisphere === "W" ? -absolute : absolute;
}

export function formatDms(value: number, axis: "lat" | "lon"): string {
  const absolute = Math.abs(value);
  const degrees = Math.floor(absolute);
  const minutesFloat = (absolute - degrees) * 60;
  const minutes = Math.floor(minutesFloat);
  const seconds = (minutesFloat - minutes) * 60;
  const hemisphere =
    axis === "lat"
      ? value < 0 ? "S" : "N"
      : value < 0 ? "W" : "E";
  return `${degrees}° ${String(minutes).padStart(2, "0")}' ${seconds
    .toFixed(3)
    .padStart(6, "0")}" ${hemisphere}`;
}

export function utmToLonLat(input: UTMInput): LonLat {
  const { easting, northing, zone, hemisphere } = input;
  if (zone < 1 || zone > 60) throw new Error("Fuso UTM deve estar entre 1 e 60.");
  if (!Number.isFinite(easting) || !Number.isFinite(northing)) {
    throw new Error("Coordenada UTM inválida.");
  }

  const x = easting - 500000;
  let y = northing;
  if (hemisphere === "S") y -= 10000000;

  const eccPrimeSq = WGS84_ECC_SQ / (1 - WGS84_ECC_SQ);
  const m = y / K0;
  const mu =
    m /
    (WGS84_A *
      (1 -
        WGS84_ECC_SQ / 4 -
        (3 * WGS84_ECC_SQ ** 2) / 64 -
        (5 * WGS84_ECC_SQ ** 3) / 256));

  const e1 =
    (1 - Math.sqrt(1 - WGS84_ECC_SQ)) /
    (1 + Math.sqrt(1 - WGS84_ECC_SQ));

  const j1 = (3 * e1) / 2 - (27 * e1 ** 3) / 32;
  const j2 = (21 * e1 ** 2) / 16 - (55 * e1 ** 4) / 32;
  const j3 = (151 * e1 ** 3) / 96;
  const j4 = (1097 * e1 ** 4) / 512;

  const fp =
    mu +
    j1 * Math.sin(2 * mu) +
    j2 * Math.sin(4 * mu) +
    j3 * Math.sin(6 * mu) +
    j4 * Math.sin(8 * mu);

  const sinFp = Math.sin(fp);
  const cosFp = Math.cos(fp);
  const tanFp = Math.tan(fp);

  const n1 = WGS84_A / Math.sqrt(1 - WGS84_ECC_SQ * sinFp ** 2);
  const t1 = tanFp ** 2;
  const c1 = eccPrimeSq * cosFp ** 2;
  const r1 =
    (WGS84_A * (1 - WGS84_ECC_SQ)) /
    (1 - WGS84_ECC_SQ * sinFp ** 2) ** 1.5;
  const d = x / (n1 * K0);

  const lat =
    fp -
    ((n1 * tanFp) / r1) *
      (d ** 2 / 2 -
        ((5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * eccPrimeSq) * d ** 4) / 24 +
        ((61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * eccPrimeSq - 3 * c1 ** 2) *
          d ** 6) /
          720);

  const lonOrigin = (zone - 1) * 6 - 180 + 3;
  const lon =
    (d -
      ((1 + 2 * t1 + c1) * d ** 3) / 6 +
      ((5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * eccPrimeSq + 24 * t1 ** 2) *
        d ** 5) /
        120) /
    cosFp;

  return [(lonOrigin + (lon * 180) / Math.PI), (lat * 180) / Math.PI];
}

export function coordinateLabel(index: number, prefix = "V"): string {
  return `${prefix}${String(index + 1).padStart(2, "0")}`;
}
