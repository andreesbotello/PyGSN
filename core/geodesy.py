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
from functools import cached_property
import logging
import re
import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Ellipsoid:
    """Parametros geometricos y fisicos de un elipsoide de revolucion."""
    name: str
    a: np.float64          # Semieje mayor [m]
    inv_f: np.float64      # Aplanamiento inverso 1/f

    @cached_property
    def f(self) -> np.float64:
        """Aplanamiento geometrico f = 1 / inv_f."""
        return np.float64(1.0) / self.inv_f

    @cached_property
    def b(self) -> np.float64:
        """Semieje menor b = a * (1 - f) [m]."""
        return self.a * (np.float64(1.0) - self.f)

    @cached_property
    def e2(self) -> np.float64:
        """Primera excentricidad al cuadrado: e^2 = 2f - f^2 = (a^2 - b^2) / a^2."""
        f = self.f
        return np.float64(2.0) * f - f * f

    @cached_property
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
    from .validation import validate_lat_lon, validate_finite
    lat_rad, lon_rad = validate_lat_lon(lat_rad, lon_rad)
    h_m = np.float64(validate_finite(h_m, "h_m"))

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
    from .validation import validate_finite
    xyz_arr = validate_finite(xyz, "xyz")
    x, y, z = np.float64(xyz_arr[0]), np.float64(xyz_arr[1]), np.float64(xyz_arr[2])
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


def rad_to_dms(rad: np.float64, decimals: int = 6) -> tuple[int, int, float, str]:
    """
    Convierte radianes a (grados, minutos, segundos, string formateado). Ejemplo: 39º28'53.133637"

    Los segundos se redondean a `decimals` ANTES del acarreo, de modo que nunca se produce
    un valor 60.000000 en la salida. El signo se aplica al primer componente no nulo
    (ej. -0º20'00" -> (0, -20, 0.0)); el string lo incluye siempre.
    """
    deg_total = float(np.degrees(np.float64(rad)))
    negative = deg_total < 0.0
    total_s = round(abs(deg_total) * 3600.0, decimals)
    d = int(total_s // 3600.0)
    m = int((total_s - d * 3600.0) // 60.0)
    s = round(total_s - d * 3600.0 - m * 60.0, decimals)
    if s >= 60.0:
        s -= 60.0
        m += 1
    if m >= 60:
        m -= 60
        d += 1
    s = abs(s)  # evita -0.0

    sign_char = "-" if negative and total_s > 0.0 else " "
    width = 3 + decimals if decimals > 0 else 2
    formatted = f"{sign_char}{d:02d}º{m:02d}'{s:0{width}.{decimals}f}\""

    if sign_char == "-":
        if d != 0:
            d = -d
        elif m != 0:
            m = -m
        else:
            s = -s
    return d, m, s, formatted


# Limite de validez de la serie de Gauss-Kruger de 5o orden implementada: a |dlon| = 3.5 deg el
# error ya alcanza ~0.1 mm en Este; crece a ~1.6 mm a 4.5 deg, ~11 mm a 6 deg y ~0.2 m a 9 deg.
UTM_SERIES_DLON_LIMIT_RAD = np.radians(3.5)
_zones_warned: set[int] = set()


def _warn_if_outside_zone(delta_lam_rad: float, zone: int) -> None:
    """Aviso (una vez por huso y sesión) si se proyecta lejos del meridiano central."""
    if abs(float(delta_lam_rad)) > UTM_SERIES_DLON_LIMIT_RAD + 1e-9 and zone not in _zones_warned:
        _zones_warned.add(zone)
        logger.warning(
            "UTM huso %d: proyección a %.2f deg del meridiano central (> 3.5 deg). "
            "El error de la serie supera el milímetro y crece rápidamente; use el huso propio del punto.",
            zone, float(np.degrees(abs(delta_lam_rad)))
        )


def utm_projection(
    lat_rad: np.float64,
    lon_rad: np.float64,
    zone: int = 30,
    hemisphere: str = "N",
    ell: Ellipsoid = GRS80
) -> tuple[np.float64, np.float64, int]:
    """
    Proyecta coordenadas geodésicas a UTM para cualquier huso (1..60) y hemisferio ('N' o 'S').
    Formulación de Gauss-Krüger / Transversa de Mercator estándar.

    Retorna:
        (Easting, Northing, Zone)
    """
    from .validation import validate_lat_lon, validate_utm_params
    lat_rad, lon_rad = validate_lat_lon(lat_rad, lon_rad)
    zone, hemisphere = validate_utm_params(zone, hemisphere)

    lon0_deg = np.float64((zone - 1) * 6 - 180 + 3)  # Meridiano central del huso
    lon0_rad = np.radians(lon0_deg)

    k0 = np.float64(0.9996)
    e2 = ell.e2
    ep2 = ell.ep2
    a = ell.a

    phi = lat_rad
    # Diferencia de longitud normalizada a [-pi, pi] (continuidad en el antimeridiano +-180 deg)
    delta_lam = np.arctan2(np.sin(lon_rad - lon0_rad), np.cos(lon_rad - lon0_rad))
    _warn_if_outside_zone(delta_lam, zone)

    sin_phi = np.sin(phi)
    cos_phi = np.cos(phi)
    tan_phi = np.tan(phi)

    nu = a / np.sqrt(np.float64(1.0) - e2 * (sin_phi ** 2))
    eta2 = ep2 * (cos_phi ** 2)

    # Coeficientes de la serie del arco meridiano
    A0 = 1.0 - (e2 / 4.0) - (3.0 * e2**2 / 64.0) - (5.0 * e2**3 / 256.0)
    A2 = (3.0 / 8.0) * (e2 + (e2**2 / 4.0) + (15.0 * e2**3 / 128.0))
    A4 = (15.0 / 256.0) * (e2**2 + (3.0 * e2**3 / 4.0))
    A6 = (35.0 / 3072.0) * (e2**3)

    S = a * (A0 * phi - A2 * np.sin(2.0 * phi) + A4 * np.sin(4.0 * phi) - A6 * np.sin(6.0 * phi))

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

    if hemisphere.upper() == "S":
        northing += 10000000.0

    return easting, northing, zone


def utm_projection_huso30(
    lat_rad: np.float64,
    lon_rad: np.float64,
    ell: Ellipsoid = GRS80
) -> tuple[np.float64, np.float64, int]:
    """
    Proyecta coordenadas geodesicas a UTM Huso 30 Norte (meridiano central -3 deg).
    Retorna:
        (Easting, Northing, Zone)
    """
    return utm_projection(lat_rad, lon_rad, zone=30, hemisphere="N", ell=ell)


def utm_meridian_convergence(
    lat_rad: np.float64 | float,
    lon_rad: np.float64 | float,
    zone: int = 30,
    ell: Ellipsoid = GRS80
) -> np.float64:
    """
    Calcula la convergencia de meridianos gamma (ángulo entre el Norte geográfico y el Norte de cuadrícula UTM)
    en radianes. Formulación de Gauss-Krüger rigurosa.

    Relación de orientación:
        Azimut_cuadrícula (psi_grid) = Azimut_geodésico (psi) - gamma
    """
    lon0_deg = np.float64((zone - 1) * 6 - 180 + 3)
    lon0_rad = np.radians(lon0_deg)

    phi = np.float64(lat_rad)
    dl0 = np.float64(lon_rad) - lon0_rad
    dl = np.float64(np.arctan2(np.sin(dl0), np.cos(dl0)))   # continuidad en +-180 deg

    sin_p = np.sin(phi)
    cos_p = np.cos(phi)
    tan_p = np.tan(phi)
    t2 = tan_p ** 2
    eta2 = ell.ep2 * (cos_p ** 2)

    # Serie de convergencia de meridianos de Gauss-Krüger
    c1 = dl * sin_p
    c3 = (dl**3 / 3.0) * sin_p * (cos_p**2) * (1.0 + 3.0 * eta2 + 2.0 * (eta2**2))
    c5 = (dl**5 / 15.0) * sin_p * (cos_p**4) * (2.0 - t2)

    gamma = c1 + c3 + c5
    return np.float64(gamma)


def utm_inverse(
    easting: float | np.float64,
    northing: float | np.float64,
    zone: int = 30,
    hemisphere: str = "N",
    ell: Ellipsoid = GRS80
) -> tuple[np.float64, np.float64]:
    """
    Convierte coordenadas proyectadas UTM a coordenadas geodésicas (latitud, longitud en radianes).
    Formulación inversa de Gauss-Krüger / Transversa de Mercator de alta precisión.

    Parámetros:
        easting: Coordenada Este en metros.
        northing: Coordenada Norte en metros.
        zone: Huso UTM (1..60).
        hemisphere: 'N' o 'S'.
        ell: Elipsoide de referencia (por defecto GRS80).

    Retorna:
        (lat_rad, lon_rad): Latitud y longitud geodésicas en radianes.
    """
    from .validation import validate_finite, validate_utm_params
    validate_finite(easting, "easting")
    validate_finite(northing, "northing")
    zone, hemisphere = validate_utm_params(zone, hemisphere)

    k0 = np.float64(0.9996)
    a = ell.a
    e2 = ell.e2
    ep2 = ell.ep2

    x = np.float64(easting) - np.float64(500000.0)
    y = np.float64(northing)
    if hemisphere.upper() == "S":
        y -= np.float64(10000000.0)
    M = y / k0

    e1 = (np.float64(1.0) - np.sqrt(np.float64(1.0) - e2)) / (np.float64(1.0) + np.sqrt(np.float64(1.0) - e2))
    mu = M / (a * (np.float64(1.0) - e2 / 4.0 - 3.0 * (e2**2) / 64.0 - 5.0 * (e2**3) / 256.0))

    phi1 = mu + (1.5 * e1 - 27.0 * (e1**3) / 32.0) * np.sin(2.0 * mu) \
              + (21.0 * (e1**2) / 16.0 - 55.0 * (e1**4) / 32.0) * np.sin(4.0 * mu) \
              + (151.0 * (e1**3) / 96.0) * np.sin(6.0 * mu) \
              + (1097.0 * (e1**4) / 512.0) * np.sin(8.0 * mu)

    sin_p1 = np.sin(phi1)
    cos_p1 = np.cos(phi1)
    tan_p1 = np.tan(phi1)

    nu1 = a / np.sqrt(np.float64(1.0) - e2 * (sin_p1**2))
    rho1 = a * (np.float64(1.0) - e2) / ((np.float64(1.0) - e2 * (sin_p1**2))**1.5)
    eta1_2 = ep2 * (cos_p1**2)
    t1 = tan_p1**2
    D = x / (nu1 * k0)

    # Latitud
    term_lat2 = (D**2) / 2.0
    term_lat4 = ((D**4) / 24.0) * (5.0 + 3.0 * t1 + 10.0 * eta1_2 - 4.0 * (eta1_2**2) - 9.0 * ep2)
    term_lat6 = ((D**6) / 720.0) * (61.0 + 90.0 * t1 + 298.0 * eta1_2 + 45.0 * (t1**2) - 252.0 * ep2 - 3.0 * (eta1_2**2))
    lat = phi1 - (nu1 * tan_p1 / rho1) * (term_lat2 - term_lat4 + term_lat6)

    # Longitud
    lon0_deg = np.float64((zone - 1) * 6 - 180 + 3)
    lon0_rad = np.radians(lon0_deg)
    term_lon1 = D
    term_lon3 = ((D**3) / 6.0) * (1.0 + 2.0 * t1 + eta1_2)
    term_lon5 = ((D**5) / 120.0) * (5.0 - 2.0 * eta1_2 + 28.0 * t1 - 3.0 * (eta1_2**2) + 8.0 * ep2 + 24.0 * (t1**2))
    dlon = (term_lon1 - term_lon3 + term_lon5) / cos_p1
    _warn_if_outside_zone(dlon, zone)
    lon = lon0_rad + dlon

    return lat, lon


def ellipsoidal_to_orthometric(h_m: float | np.floating, N_m: float | np.floating) -> float:
    """
    Convierte altitud elipsoidal h a cota ortométrica H mediante la ondulación geoidal N:
    H = h - N [m]
    """
    return float(np.float64(h_m) - np.float64(N_m))


def orthometric_to_ellipsoidal(H_m: float | np.floating, N_m: float | np.floating) -> float:
    """
    Convierte cota ortométrica H a altitud elipsoidal h mediante la ondulación geoidal N:
    h = H + N [m]
    """
    return float(np.float64(H_m) + np.float64(N_m))


def grid_bearing(yaw_rad: float | np.floating, gamma_rad: float | np.floating) -> np.float64:
    """
    Calcula el rumbo respecto al Norte de cuadrícula de la proyección cartográfica (Grid Bearing):
    psi_grid = yaw - gamma (convergencia de meridianos).
    Retorna el ángulo normalizado en [0, 2pi) rad.
    """
    from .validation import normalize_angle_2pi
    psi = np.float64(yaw_rad) - np.float64(gamma_rad)
    return np.float64(normalize_angle_2pi(psi))


_COORD_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?|[A-Za-z]|[º°'\"�]|[-+]|\S")
_HEMI_NEGATIVE = frozenset("SWO")     # Sur, Oeste (W / O)
_HEMI_POSITIVE = frozenset("NE")


def parse_coordinate_string(s: str) -> float:
    """
    Parsea una coordenada angular en grados decimales o sexagesimales y retorna grados decimales
    con signo (float).

    Formatos admitidos:
      - Decimal:            39.481426 | -0.335458 | 39,481426
      - Símbolos:           39º28'53.133637" | -0º20'7.650964" | 39° 28' 53.13" N
      - Marcadores letra:   39d28m53.13s | 3d42m10.5sE
      - Separados por blancos con hemisferio: 39 28 53.13 S | W 0 20 7.65

    Reglas (gramática explícita):
      - Hasta 3 campos numéricos: grados, minutos [0, 60), segundos [0, 60).
      - En notación con letras (d, m), la 's' que sigue al tercer número es el marcador de
        segundos; un hemisferio, si existe, va además (ej. '10.5sS').
      - Hemisferio: N/E positivo, S/W/O negativo, como letra al principio o al final.
      - Signo '-' inicial: negativo. Es un error combinar '-' con un hemisferio.
    """
    if not isinstance(s, str):
        s = str(s)
    txt = s.strip()
    for a, b in (("“", '"'), ("”", '"'), ("″", '"'), ("′", "'"), ("''", '"')):
        txt = txt.replace(a, b)
    if not txt:
        raise ValueError("Coordenada vacía.")

    try:
        return float(txt.replace(",", "."))
    except ValueError:
        pass

    tokens = _COORD_TOKEN_RE.findall(txt)
    letter_markers = bool(re.search(r"\d\s*[dD]", txt))

    numbers: list[float] = []
    hemi: str | None = None
    minus = False
    prev_number = False
    for idx, tok in enumerate(tokens):
        if tok[0].isdigit():
            if len(numbers) == 3:
                raise ValueError(f"Coordenada con más de 3 campos numéricos: '{s}'.")
            numbers.append(float(tok.replace(",", ".")))
            prev_number = True
            continue
        if tok in ("-", "+"):
            if idx != 0:
                raise ValueError(f"Signo '{tok}' fuera de posición en la coordenada '{s}'.")
            minus = tok == "-"
        elif tok in ("º", "°", "'", '"', "�"):
            pass
        elif tok.isalpha():
            n = len(numbers)
            if prev_number and tok in ("d", "D") and n == 1:
                pass
            elif prev_number and tok in ("m", "M") and n == 2:
                pass
            elif prev_number and tok in ("s", "S") and n == 3 and letter_markers:
                pass
            elif tok.upper() in (_HEMI_NEGATIVE | _HEMI_POSITIVE):
                if hemi is not None and hemi != tok.upper():
                    raise ValueError(f"Hemisferios contradictorios en la coordenada '{s}'.")
                hemi = tok.upper()
            else:
                raise ValueError(f"Carácter '{tok}' no reconocido en la coordenada '{s}'.")
        else:
            raise ValueError(f"Carácter '{tok}' no reconocido en la coordenada '{s}'.")
        prev_number = False

    if not numbers:
        raise ValueError(f"No se pudo parsear la coordenada: '{s}'.")
    if minus and hemi is not None:
        raise ValueError(f"Coordenada ambigua (signo '-' y hemisferio '{hemi}'): '{s}'.")

    d = numbers[0]
    m = numbers[1] if len(numbers) > 1 else 0.0
    sec = numbers[2] if len(numbers) > 2 else 0.0
    if not (0.0 <= m < 60.0) or not (0.0 <= sec < 60.0):
        raise ValueError(f"Minutos y segundos deben estar en [0, 60): '{s}'.")

    deg = d + m / 60.0 + sec / 3600.0
    negative = minus or (hemi in _HEMI_NEGATIVE)
    return -deg if negative else deg


# Alias de compatibilidad
parse_dms_or_deg = parse_coordinate_string



