"""
PyGSN - Core Geodesy Module
===========================
Funciones de geodesia computacional de alta precision (np.float64):
- Parametros elipsoidales (GRS80, WGS84)
- Radios de curvatura del elipsoide (Rm, Rn)
- Conversion Geodesicas (phi, lambda, h) <-> Cartesianas ECEF (X, Y, Z)
- Proyeccion cartografica Transversa de Mercator / UTM (Huso 30 Norte)
- Conversion altitud elipsoidal <-> ortometrica mediante ondulacion geoidal N
"""

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Ellipsoid:
    """Parametros geometricos y fisicos de un elipsoide de revolucion."""
    name: str
    a: np.float64          # Semieje mayor [m]
    inv_f: np.float64      # Aplanamiento inverso 1/f

    @property
    def f(self) -> np.float64:
        """Aplanamiento geometrico f = 1 / inv_f."""
        return np.float64(1.0) / self.inv_f

    @property
    def b(self) -> np.float64:
        """Semieje menor b = a * (1 - f) [m]."""
        return self.a * (np.float64(1.0) - self.f)

    @property
    def e2(self) -> np.float64:
        """Primera excentricidad al cuadrado: e^2 = 2f - f^2 = (a^2 - b^2) / a^2."""
        f = self.f
        return np.float64(2.0) * f - f * f

    @property
    def ep2(self) -> np.float64:
        """Segunda excentricidad al cuadrado: e'^2 = (a^2 - b^2) / b^2 = e^2 / (1 - e^2)."""
        e2 = self.e2
        return e2 / (np.float64(1.0) - e2)


# Elipsoides estandar del curso
GRS80 = Ellipsoid(name="GRS80", a=np.float64(6378137.0), inv_f=np.float64(298.257222100883))
WGS84 = Ellipsoid(name="WGS84", a=np.float64(6378137.0), inv_f=np.float64(298.257223563))


def radii_of_curvature(lat_rad: np.float64, ell: Ellipsoid = GRS80) -> tuple[np.float64, np.float64]:
    """
    Calcula los radios de curvatura del elipsoide para una latitud dada.

    Parametros:
        lat_rad: Latitud geodesica en radianes.
        ell: Instancia de Ellipsoid (por defecto GRS80).

    Retorna:
        (Rm, Rn):
            Rm: Radio de curvatura del meridiano (Rho) [m]
            Rn: Radio de curvatura del primer vertical o Gran Normal (Nu) [m]
    """
    sin_phi = np.sin(lat_rad)
    w2 = np.float64(1.0) - ell.e2 * (sin_phi ** 2)
    w = np.sqrt(np.clip(w2, 1e-15, None))

    rn = ell.a / w
    rm = ell.a * (np.float64(1.0) - ell.e2) / (w ** 3)
    return rm, rn


def geodetic_to_ecef(
    lat_rad: np.float64,
    lon_rad: np.float64,
    h_m: np.float64,
    ell: Ellipsoid = GRS80
) -> np.ndarray:
    """
    Convierte coordenadas geodesicas (latitud, longitud, altitud elipsoidal)
    a coordenadas cartesianas geocentricas ECEF (X, Y, Z).

    Parametros:
        lat_rad: Latitud geodesica [rad]
        lon_rad: Longitud geodesica [rad]
        h_m: Altitud sobre el elipsoide [m]
        ell: Elipsoide de referencia

    Retorna:
        np.ndarray de shape (3,) con [X, Y, Z] en metros.
    """
    _, rn = radii_of_curvature(lat_rad, ell)
    cos_phi = np.cos(lat_rad)
    sin_phi = np.sin(lat_rad)
    cos_lam = np.cos(lon_rad)
    sin_lam = np.sin(lon_rad)

    x = (rn + h_m) * cos_phi * cos_lam
    y = (rn + h_m) * cos_phi * sin_lam
    z = (rn * (np.float64(1.0) - ell.e2) + h_m) * sin_phi

    return np.array([x, y, z], dtype=np.float64)


def ecef_to_geodetic(
    xyz: np.ndarray,
    ell: Ellipsoid = GRS80,
    tol: np.float64 = np.float64(1e-12),
    max_iter: int = 20
) -> tuple[np.float64, np.float64, np.float64]:
    """
    Convierte coordenadas cartesianas ECEF (X, Y, Z) a geodesicas (lat, lon, h).
    Metodo iterativo riguroso de Bowring con convergencia a nivel sub-nanometrico.

    Parametros:
        xyz: Array (3,) con [X, Y, Z] en metros.
        ell: Elipsoide de referencia.
        tol: Tolerancia en latitud [rad].
        max_iter: Numero maximo de iteraciones.

    Retorna:
        (lat_rad, lon_rad, h_m):
            lat_rad: Latitud geodesica [rad]
            lon_rad: Longitud geodesica [rad]
            h_m: Altitud elipsoidal [m]
    """
    x, y, z = np.float64(xyz[0]), np.float64(xyz[1]), np.float64(xyz[2])
    p = np.hypot(x, y)

    # Singularidad en los polos
    if p < 1e-10:
        lat = np.sign(z) * (np.pi / 2.0) if z != 0 else np.float64(0.0)
        lon = np.float64(0.0)
        h = np.abs(z) - ell.b
        return lat, lon, h

    lon = np.arctan2(y, x)

    # Bowring initial closed-form approximation
    theta = np.arctan2(z * ell.a, p * ell.b)
    sin_th = np.sin(theta)
    cos_th = np.cos(theta)

    lat = np.arctan2(
        z + ell.ep2 * ell.b * (sin_th ** 3),
        p - ell.e2 * ell.a * (cos_th ** 3)
    )

    # Refinamiento iterativo para precision absoluta
    for _ in range(max_iter):
        sin_lat = np.sin(lat)
        rn = ell.a / np.sqrt(np.float64(1.0) - ell.e2 * (sin_lat ** 2))
        h = p / np.cos(lat) - rn
        new_lat = np.arctan2(z, p * (np.float64(1.0) - ell.e2 * (rn / (rn + h))))
        if np.abs(new_lat - lat) < tol:
            lat = new_lat
            break
        lat = new_lat

    sin_lat = np.sin(lat)
    rn = ell.a / np.sqrt(np.float64(1.0) - ell.e2 * (sin_lat ** 2))
    h = p / np.cos(lat) - rn

    return lat, lon, h


def dms_to_rad(deg: int | float, minutes: int | float, seconds: float, sign: int = 1) -> np.float64:
    """Convierte grados, minutos y segundos a radianes con signo."""
    total_deg = (abs(deg) + abs(minutes) / 60.0 + abs(seconds) / 3600.0) * (1 if sign >= 0 else -1)
    return np.radians(np.float64(total_deg))


def rad_to_dms(rad: np.float64) -> tuple[int, int, float, str]:
    """
    Convierte radianes a formato (grados, minutos, segundos, string formateado).
    Ejemplo: 39º28'53.133637"
    """
    deg_total = np.degrees(rad)
    sign = "-" if deg_total < 0 else " "
    deg_abs = abs(deg_total)
    d = int(deg_abs)
    m_float = (deg_abs - d) * 60.0
    m = int(m_float)
    s = (m_float - m) * 60.0
    # Proteccion contra redondeo a 60.0
    if s >= 59.999999999:
        s = 0.0
        m += 1
        if m == 60:
            m = 0
            d += 1
    formatted = f"{sign}{d:02d}º{m:02d}'{s:09.6f}\""
    return d if sign == " " else -d, m, s, formatted


def utm_projection_huso30(
    lat_rad: np.float64,
    lon_rad: np.float64,
    ell: Ellipsoid = GRS80
) -> tuple[np.float64, np.float64, int]:
    """
    Proyecta coordenadas geodesicas a UTM Huso 30 Norte (meridiano central -3 deg).
    Formulacion de Gauss-Kruger / Transversa de Mercator estandar.

    Retorna:
        (Easting, Northing, Zone)
    """
    zone = 30
    lon0_deg = np.float64(-3.0)  # Meridiano central huso 30
    lon0_rad = np.radians(lon0_deg)

    k0 = np.float64(0.9996)
    e2 = ell.e2
    ep2 = ell.ep2
    a = ell.a

    phi = lat_rad
    delta_lam = lon_rad - lon0_rad

    sin_phi = np.sin(phi)
    cos_phi = np.cos(phi)
    tan_phi = np.tan(phi)

    nu = a / np.sqrt(np.float64(1.0) - e2 * (sin_phi ** 2))
    eta2 = ep2 * (cos_phi ** 2)

    # Arco meridiano meridional S(phi)
    # Coeficientes de la serie del arco meridiano
    A0 = 1.0 - (e2 / 4.0) - (3.0 * e2**2 / 64.0) - (5.0 * e2**3 / 256.0)
    A2 = (3.0 / 8.0) * (e2 + (e2**2 / 4.0) + (15.0 * e2**3 / 128.0))
    A4 = (15.0 / 256.0) * (e2**2 + (3.0 * e2**3 / 4.0))
    A6 = (35.0 / 3072.0) * (e2**3)

    S = a * (A0 * phi - A2 * np.sin(2.0 * phi) + A4 * np.sin(4.0 * phi) - A6 * np.sin(6.0 * phi))

    # Desarrollo en serie de potencias de delta_lam
    t = tan_phi
    t2 = t * t
    c = eta2
    dl = delta_lam
    cos_p = cos_phi

    # Easting
    e_term1 = dl * cos_p
    e_term3 = (dl**3 * cos_p**3 / 6.0) * (1.0 - t2 + c)
    e_term5 = (dl**5 * cos_p**5 / 120.0) * (5.0 - 18.0 * t2 + t2**2 + 72.0 * c - 58.0 * ep2)
    easting = 500000.0 + k0 * nu * (e_term1 + e_term3 + e_term5)

    # Northing
    n_term2 = (dl**2 / 2.0) * sin_phi * cos_p
    n_term4 = (dl**4 / 24.0) * sin_phi * (cos_p**3) * (5.0 - t2 + 9.0 * c + 4.0 * c**2)
    n_term6 = (dl**6 / 720.0) * sin_phi * (cos_p**5) * (61.0 - 58.0 * t2 + t2**2 + 600.0 * c - 330.0 * ep2)
    northing = k0 * (S + nu * (n_term2 + n_term4 + n_term6))

    return easting, northing, zone
