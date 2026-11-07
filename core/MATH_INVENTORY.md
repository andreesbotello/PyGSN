# PyGSN - Inventario Maestro de Operaciones Matemáticas

Este catálogo documenta todas las funciones de la **Batería Matemática Pura** de PyGSN. Define el archivo fuente donde reside cada operación, sus entradas, salidas, formulación analítica y referencias bibliográficas de navegación y geodesia.

---

## 1. Módulo de Validación y Blindaje Numérico (`core/validation.py`)

| Función | Entradas | Salidas (Producto) | Ecuación / Proceso | Referencia Bibliográfica |
|---|---|---|---|---|
| `validate_finite(val_or_arr, name)` | `val_or_arr: Any`, `name: str` | `arr: np.ndarray (float64)` | Comprueba ausencia de NaN y $\pm\infty$. | Estándar IEEE-754 |
| `normalize_angle_pi(angle_rad)` | `angle_rad: float \| np.ndarray` [rad] | `norm: np.float64 \| np.ndarray` [rad] | $\theta_{\text{norm}} = \text{atan2}(\sin\theta, \cos\theta) \in [-\pi, \pi]$ | Jekeli Sec. 1.4 |
| `normalize_angle_2pi(angle_rad)` | `angle_rad: float \| np.ndarray` [rad] | `norm: np.float64 \| np.ndarray` [rad] | $\theta_{\text{norm}} = (\theta \pmod{2\pi}) \in [0, 2\pi)$ | Groves Sec. 2.1 |
| `normalize_angle_deg_180(angle_deg)` | `angle_deg: float \| np.ndarray` [deg] | `norm: float \| np.ndarray` [deg] | $(\theta + 180^\circ \pmod{360^\circ}) - 180^\circ$ | Estándar angular |
| `normalize_angle_deg_360(angle_deg)` | `angle_deg: float \| np.ndarray` [deg] | `norm: float \| np.ndarray` [deg] | $\theta \pmod{360^\circ}$ | Estándar angular |
| `validate_attitude_angles(r, p, y, strict_pitch)` | `r, p, y: float` [rad], `strict_pitch: bool` | `(r_n, p_n, y_n): tuple[np.float64, np.float64, np.float64]` | Guarda Pitch $[-\pi/2, \pi/2]$, alerta Gimbal Lock ($\lvert\cos p\rvert < 10^{-10}$), normaliza Roll $[-\pi, \pi]$ y Yaw $[0, 2\pi)$. | Groves Sec. 5.3 / Jekeli Sec. 1.4 |
| `validate_lat_lon(lat_rad, lon_rad, allow_polar)` | `lat_rad, lon_rad: float` [rad], `allow_polar: bool` | `(lat_c, lon_c): tuple[np.float64, np.float64]` | Guarda Latitud $[-\pi/2, \pi/2]$, normaliza Longitud $[-\pi, \pi]$. | Hofmann Cap. 2 |
| `validate_utm_params(zone, hemisphere)` | `zone: int`, `hemisphere: str` | `(zone_i, hem_s): tuple[int, str]` | Verifica $1 \le \text{zone} \le 60$ y $\text{hem} \in \{'N', 'S'\}$. | DMA / NGA UTM Spec |
| `validate_antenna_geometry(points, min_points, collinear_tol)` | `points: np.ndarray (3, N)`, `min_points: int`, `collinear_tol: float` | `pts_c: np.ndarray (3, N)` | Comprobación SVD de rango espacial: $\sigma_2 / \sigma_1 \ge \text{collinear\_tol}$ (evita indeterminación azimutal). | Kabsch (1976) |
| `validate_safe_division(num, den, eps, default)` | `num, den: float \| np.ndarray`, `eps: float`, `default: float` | `res: np.float64 \| np.ndarray` | Retorna $\text{num} / \text{den}$ si $\lvert\text{den}\rvert \ge \epsilon$, o `default` si $\lvert\text{den}\rvert < \epsilon$. | Blindaje Numérico |

---

## 2. Módulo de Álgebra de Rotaciones (`core/rotations.py`)

| Función | Entradas | Salidas (Producto) | Ecuación / Proceso | Referencia Bibliográfica |
|---|---|---|---|---|
| `R1(angle_rad)` | `angle_rad: np.float64` [rad] | `R: np.ndarray (3,3)` | Rotación pasiva sobre eje X (1). | Jekeli Ec. 1.34 |
| `R2(angle_rad)` | `angle_rad: np.float64` [rad] | `R: np.ndarray (3,3)` | Rotación pasiva sobre eje Y (2). | Jekeli Ec. 1.35 |
| `R3(angle_rad)` | `angle_rad: np.float64` [rad] | `R: np.ndarray (3,3)` | Rotación pasiva sobre eje Z (3). | Jekeli Ec. 1.36 |
| `e_to_n_matrix(lat_rad, lon_rad)` | `lat_rad, lon_rad: np.float64` [rad] | `Ce2n: np.ndarray (3,3)` | $C_e^n = R_2(-(\pi/2+\phi)) R_3(\lambda)$ | Jekeli Ec. 1.80 |
| `n_to_e_matrix(lat_rad, lon_rad)` | `lat_rad, lon_rad: np.float64` [rad] | `Cn2e: np.ndarray (3,3)` | $C_n^e = (C_e^n)^T$ | Jekeli Ec. 1.82 |
| `euler_to_dcm(a1, a2, a3)` | `a1, a2, a3: np.float64` [rad] | `C: np.ndarray (3,3)` | $C = R_3(a_3) R_2(a_2) R_1(a_1)$ ($R_i$ pasivas). **No es $C_b^n$** si se le pasan $(r, p, y)$: usar `attitude_to_dcm`. | Jekeli Ec. 1.48 |
| `attitude_to_dcm(roll_rad, pitch_rad, yaw_rad)` | `roll_rad, pitch_rad, yaw_rad: np.float64` [rad] | `Cb2n: np.ndarray (3,3)` | $C_b^n = R_3(-y) R_2(-p) R_1(-r)$ | Jekeli Ec. 1.90 |
| `dcm_to_euler(C)` | `C: np.ndarray (3,3)` | `(a1, a2, a3): tuple[np.float64, np.float64, np.float64]` [rad] | Extracción analítica Euler ZYX: $a_2 = \text{atan2}(C_{20}, \text{hypot}(C_{21}, C_{22}))$ (exacta cerca de $\pm 90^\circ$), guarda Gimbal Lock $\cos a_2 < 10^{-10}$. | Hofmann Cap. 5 |
| `dcm_to_attitude(Cb2n)` | `Cb2n: np.ndarray (3,3)` | `(r, p, y): tuple[np.float64, np.float64, np.float64]` [rad] | $r = -a_1$, $p = -a_2$, $y = -a_3 \pmod{2\pi}$ | Jekeli Cap. 1 |
| `sensor_to_body_matrix(alpha, beta, gamma)` | `alpha, beta, gamma: np.float64` [rad] | `Cs2b: np.ndarray (3,3)` | $C_s^b = R_3(\gamma) R_2(\beta) R_1(\alpha)$ | Boresight Monografía |
| `body_to_sensor_matrix(alpha, beta, gamma)` | `alpha, beta, gamma: np.float64` [rad] | `Cb2s: np.ndarray (3,3)` | $C_b^s = (C_s^b)^T$ | Boresight Monografía |
| `magnetic_to_geodetic_north_matrix(declination_rad)` | `declination_rad: np.float64` [rad], D IGRF/WMM (Este +) | `Cmn2gn: np.ndarray (3,3)` | $C_{mn}^{gn} = R_3(-D)$, $\psi = \psi_m + D$. Datos con convención $C_{mn}^{gn} = R_3(\delta)$: $D = -\delta$ | Groves Sec. 6.1.1 |
| `chain_ins_attitude_matrix(roll, pitch, yaw, decl, a, b, g)` | `roll, pitch, yaw, decl, a, b, g: np.float64` [rad] | `Cb2n: np.ndarray (3,3)` | $C_b^n = C_{mn}^{gn}(D) \cdot C_s^{n,mn}(r,p,y) \cdot (C_s^b(\alpha,\beta,\gamma))^T$ | Groves Cap. 5 |
| `reorthonormalize_dcm(C)` | `C: np.ndarray (3,3)` | `C_ortho: np.ndarray (3,3)` | SVD / Descomposición Polar: $C = U V^T$, garantizando $\det(C) = +1$. | Groves Sec. 5.3 |
| `audit_dcm_condition(C)` | `C: np.ndarray (3,3)` | `(det_val, ortho_err): tuple[float, float]` | $\lvert\det(C) - 1.0\rvert$ y $\|C C^T - I_3\|_F$ | Metrología DCM |

---

## 3. Módulo de Geodesia y Proyecciones (`core/geodesy.py`)

| Función | Entradas | Salidas (Producto) | Ecuación / Proceso | Referencia Bibliográfica |
|---|---|---|---|---|
| `radii_of_curvature(lat_rad, ell)` | `lat_rad: np.float64` [rad], `ell: Ellipsoid` | `(Rm, Rn): tuple[np.float64, np.float64]` [m] | $R_m = \frac{a(1-e^2)}{(1-e^2\sin^2\phi)^{3/2}}$, $R_n = \frac{a}{\sqrt{1-e^2\sin^2\phi}}$ | Groves Ec. 2.67-68 |
| `geodetic_to_ecef(lat_rad, lon_rad, h_m, ell)` | `lat_rad, lon_rad: np.float64` [rad], `h_m: np.float64` [m], `ell: Ellipsoid` | `xyz: np.ndarray (3,)` [m] | $X=(R_n+h)\cos\phi\cos\lambda$, $Y=(R_n+h)\cos\phi\sin\lambda$, $Z=(R_n(1-e^2)+h)\sin\phi$ | Hofmann Ec. 2.37 |
| `ecef_to_geodetic(xyz, ell, tol, max_iter)` | `xyz: np.ndarray (3,)` [m], `ell: Ellipsoid`, `tol: np.float64`, `max_iter: int` | `(lat, lon, h): tuple[np.float64, np.float64, np.float64]` [rad, rad, m] | Algoritmo iterativo cerrado de Bowring para precisión sub-nanométrica. | Bowring (1985) |
| `dms_to_rad(deg, minutes, seconds, sign)` | `deg, min, sec: float`, `sign: int` | `rad: np.float64` [rad] | $\theta_{\text{rad}} = \text{radians}((\lvert d\rvert + m/60 + s/3600)\cdot \text{sign})$ | Conversor Sexagesimal |
| `rad_to_dms(rad)` | `rad: np.float64` [rad] | `(d, m, s, str): tuple[int, int, float, str]` | Descomposición en grados, minutos, segundos con formato $DD^\circ MM' SS.SSSSSS''$. Redondeo de segundos antes del acarreo (nunca 60.000000); signo en el primer componente no nulo. | Conversor Sexagesimal |
| `parse_coordinate_string(s)` | `s: str` | `deg: float` [deg] | Gramática explícita: decimal, símbolos (º ' "), marcadores d/m/s, hemisferio N/E/S/W/O aislado; valida minutos y segundos en $[0, 60)$ y rechaza signo + hemisferio. | Parser Geodésico |
| `ellipsoidal_to_orthometric(h_m, N_m)` | `h_m: float`, `N_m: float` [m] | `H: float` [m] | $H = h - N$ | Geodesia Física |
| `orthometric_to_ellipsoidal(H_m, N_m)` | `H_m: float`, `N_m: float` [m] | `h: float` [m] | $h = H + N$ | Geodesia Física |
| `utm_projection(lat_rad, lon_rad, zone, hemisphere, ell)` | `lat_rad, lon_rad: np.float64`, `zone: int`, `hemisphere: str`, `ell: Ellipsoid` | `(E, N, zone): tuple[np.float64, np.float64, int]` [m, m, int] | Proyección Gauss-Krüger directa (serie de 5o orden) para husos 1..60 (N/S). $\Delta\lambda$ normalizado en $\pm 180^\circ$. Error frente a PROJ: 0.13 mm a $\Delta\lambda = 2.7^\circ$; aviso de log si $\lvert\Delta\lambda\rvert > 3.5^\circ$ (1.6 mm a $4.5^\circ$, 11 mm a $6^\circ$). | Gauss-Krüger Directa |
| `utm_projection_huso30(lat_rad, lon_rad, ell)` | `lat_rad, lon_rad: np.float64`, `ell: Ellipsoid` | `(E, N, 30): tuple[np.float64, np.float64, int]` [m, m, int] | Proyección UTM forzada al meridiano central $-3^\circ$ (Huso 30N). | Gauss-Krüger Directa |
| `utm_inverse(easting, northing, zone, hemisphere, ell)` | `easting, northing: float` [m], `zone: int`, `hemisphere: str`, `ell: Ellipsoid` | `(lat, lon): tuple[np.float64, np.float64]` [rad, rad] | Inversión analítica de Gauss-Krüger: 0.2–0.4 mm frente a PROJ dentro del huso (ida-vuelta 0.8 mm); aviso de log si $\lvert\Delta\lambda\rvert > 3.5^\circ$. | Gauss-Krüger Inversa |
| `utm_meridian_convergence(lat_rad, lon_rad, zone, ell)` | `lat_rad, lon_rad: float` [rad], `zone: int`, `ell: Ellipsoid` | `gamma: np.float64` [rad] | Convergencia de meridianos $\gamma$ Gauss-Krüger. | Gauss-Krüger |
| `grid_bearing(yaw_rad, gamma_rad)` | `yaw_rad, gamma_rad: float` [rad] | `psi_grid: np.float64` [rad] | $\psi_{\text{grid}} = \text{yaw} - \gamma$ (rumbo respecto a cuadrícula UTM). | Cartografía UTM |

---

## 4. Módulo de Procrustes y Alineamiento Ortogonal (`core/alignment.py`)

| Función | Entradas | Salidas (Producto) | Ecuación / Proceso | Referencia Bibliográfica |
|---|---|---|---|---|
| `compute_centroid_3d(points)` | `points: np.ndarray (3, N)` [m] | `centroid: np.ndarray (3,)` [m] | $\bar{x} = \frac{1}{N}\sum_{i=1}^N x_i$ | Álgebra Lineal |
| `reduce_to_centroid_3d(points)` | `points: np.ndarray (3, N)` [m] | `(pts_c, centroid): tuple[np.ndarray (3, N), np.ndarray (3,)]` | $x_i' = x_i - \bar{x}$ | Álgebra Lineal |
| `kabsch_orthogonal_procrustes(points_from, points_to)` | `points_from, points_to: np.ndarray (3, N)` [m] | `(R, c_from, c_to, res): tuple[np.ndarray (3,3), np.ndarray (3,), np.ndarray (3,), np.ndarray (3, N)]` | $H = P_{to} P_{from}^T$, SVD: $H = U S V^T$, $R = U V^T$, con corrección de reflexión si $\det(R)<0$. | Kabsch (1976) |

---

## 5. Módulo de Cinemática y Geometría de Chasis (`core/kinematics.py`)

| Función | Entradas | Salidas (Producto) | Ecuación / Proceso | Referencia Bibliográfica |
|---|---|---|---|---|
| `propagate_lever_arm_ecef(r_origin_e, Cb2e, lever_arm_b)` | `r_origin_e: np.ndarray (3,)` [m], `Cb2e: np.ndarray (3,3)`, `lever_arm_b: np.ndarray (3,)` [m] | `r_sensor_e: np.ndarray (3,)` [m] | $\vec{r}_{\text{sens}}^e = \vec{r}_{\text{origin}}^e + C_b^e \cdot \vec{l}^b$ | Groves Ec. 2.115 |
| `solve_origin_from_centroid_ecef(centroid_e, cent_b, Cb2e)` | `centroid_e, cent_b: np.ndarray (3,)` [m], `Cb2e: np.ndarray (3,3)` | `r_pla_e: np.ndarray (3,)` [m] | $\vec{r}_{\text{pla}}^e = \vec{r}_{\text{cent}}^e - C_b^e \cdot \bar{x}^b$ | Mecánica Rígida |
| `geodetic_navigation_rates(v_n, lat_rad, h_m, ell)` | `v_n: np.ndarray (3,)` [m/s], `lat_rad: float` [rad], `h_m: float` [m], `ell: Ellipsoid` | `(dlat, dlon, dh): tuple[float, float, float]` [rad/s, rad/s, m/s] | $\dot{\phi} = \frac{v_N}{R_m+h}$, $\dot{\lambda} = \frac{v_E}{(R_n+h)\cos\phi}$, $\dot{h} = -v_D$ | Groves Ec. 5.44 |
| `rotate_polygon_2d(points_2d, angle_deg, center_2d)` | `points_2d: np.ndarray (N, 2)` [m], `angle_deg: float` [deg], `center_2d: np.ndarray (2,)` [m] | `pts_rot: np.ndarray (N, 2)` [m] | Rotación 2D sobre plano ortogonal respecto al centroide (precisión completa, sin redondeo intermedio). | Geometría CAD |
| `scale_polygon_2d(points_2d, factor_x, factor_y, center_2d)` | `points_2d: np.ndarray (N, 2)` [m], `factor_x, factor_y: float`, `center_2d: np.ndarray (2,)` [m] | `pts_scaled: np.ndarray (N, 2)` [m] | $(P - C) \cdot \text{diag}(f_x, f_y) + C$ (precisión completa) | Geometría CAD |
| `Platform.rotate_plane(angle_deg, plane)` (`core/models.py`) | `angle_deg` múltiplo de 90 [deg], `plane: 'S' \| 'F' \| 'L'` | `A: np.ndarray (3,3)` (permutación con signo) | Reorientación exacta del b-frame FRD: chasis, $l' = A\,l$, $C_s^{b'} = A\,C_s^b$, $C_b^{n\prime} = C_b^n A^T$. Rechaza ángulos no múltiplos de 90. | Curso p. 37 / Jekeli (FRD) |
| `compute_polygon_2d_bounds(points_2d)` | `points_2d: np.ndarray (N, 2)` [m] | `bounds: dict[str, float]` [m] | Mínimos y máximos en X/Y, longitud y anchura envolvente. | Geometría CAD |
| `compute_utm_bounding_box_points(origin_utm, heading_grid_rad, b_points_2d)` | `origin_utm: tuple[float, float]` [m], `heading_grid_rad: float` [rad], `b_points_2d: np.ndarray (N, 2)` [m] | `utm_box: dict[str, float]` [m] | Bounding box orientada al Norte cuadrícula en coordenadas UTM (Easting/Northing). | Cartografía CAD |

---

## 6. Módulo Funcional de Georreferenciación (`core/georeferencing.py`)

| Función | Entradas | Salidas (Producto) | Ecuación / Proceso | Referencia Bibliográfica |
|---|---|---|---|---|
| `gnss_observations_to_ecef(obs, ell)` | `obs: dict[str, tuple[float, float, float]]`, `ell: Ellipsoid` | `ecef_dict: dict[str, np.ndarray]` [m] | Convierte todas las observaciones $(\phi, \lambda, h)$ GNSS a ECEF. | Pipeline Paso 1 |
| `compute_navigation_centroid(ecef_pts, ell)` | `ecef_pts: dict[str, np.ndarray]`, `ell: Ellipsoid` | `(c_e, lat, lon, h, Ce2n): tuple` | Centroide de constelación, posición geodésica y $C_e^n(\text{centroide})$. | Pipeline Paso 2 |
| `project_ecef_to_nframe(ecef_pts, c_e, Ce2n)` | `ecef_pts: dict`, `c_e: np.ndarray`, `Ce2n: np.ndarray` | `dx_n: dict[str, np.ndarray]` [m] | $\Delta \vec{r}_i^n = C_e^n \cdot (\vec{r}_i^e - \vec{r}_{\text{cent}}^e)$ | Pipeline Paso 3 |
| `solve_attitude_kabsch(pts_b, vectors_n)` | `pts_b, vectors_n: dict[str, np.ndarray]` | `(Cb2n, cb, cn, eul, att, aud): tuple` | Procrustes Kabsch entre antenas en $b$-frame y $n$-frame. | Pipeline Paso 4 |
| `solve_pla_origin_ecef(c_e, cb, Cb2n, lat, lon, ell)` | `c_e, cb: np.ndarray`, `Cb2n: np.ndarray`, `lat, lon: float`, `ell: Ellipsoid` | `(r_pla_e, lat, lon, h, Cb2e): tuple` | $\vec{r}_{\text{pla}}^e = \vec{r}_{\text{cent}}^e - C_n^e \cdot C_b^n \cdot \bar{x}^b$ | Pipeline Paso 5 |
| `solve_attitude_ins_chain(rpy_ins, decl, boresight)` | `rpy_ins, decl, boresight: tuple/float` | `(Cb2n, Cb2s, Cs2b, eul, att): tuple` | $C_b^n = C_{mn}^{gn}(D) \cdot C_s^{n,mn}(rpy) \cdot (C_s^b)^T$, $D$ IGRF (Este +) | Pipeline Paso 6 |
| `propagate_sensor_network(r_pla, Cb2e, arms_b, ell, zone, hem, geoid_N)` | Coordenadas PLA, $C_b^e$, palancas, parámetros elipsoide y SRT | `results: dict[str, SensorResult]` | Propagación métrica completa a ECEF, Geodésicas, UTM y cota ortométrica. | Pipeline Paso 7 |
| `compute_georef_residuals(obs_ecef, calc_ecef)` | `obs_ecef, calc_ecef: dict[str, np.ndarray]` | `res_m: dict[str, float]` [m] | Error 3D $\|\vec{r}_{\text{obs}}^e - \vec{r}_{\text{calc}}^e\|$ por antena. | Pipeline Paso 8 |
| `compute_consistency_residuals(res_a, res_b)` | `res_a, res_b: dict[str, SensorResult]` | `diff_utm: dict[str, tuple[float, float, float]]` | Discrepancias métricas $(\Delta E, \Delta N, \Delta H)$ entre GNSS e INS. | Pipeline Paso 9 |
| `compute_attitude_uncertainty(arms_b, vectors_n, codes, Cb2n, att_ins, devices_b)` | Palancas y vectores $n$-frame de antenas, $C_b^n$ estimada, actitud INS opcional, sensores a propagar | `AttitudeUncertainty` | $\sigma_0^2 = \sum\lVert v_i\rVert^2/(3N-6)$; $\Sigma_\theta = \sigma_0^2 (\sum [q_i\times]^T[q_i\times])^{-1}$; $\Sigma_{rpy} = J \Sigma_\theta J^T$; $\Sigma_s = \sigma_0^2/N\,I + [q_s\times]\Sigma_\theta[q_s\times]^T$; test $\lvert\Delta\rvert/\sigma > 3$. Validado con Monte Carlo (10 %). | Pipeline Paso 10 |
| `solve_georeferencing_pipeline(...)` | Entradas numéricas puras (declinación $D$ IGRF y ondulación $N$; por defecto 0.0) | `GeoreferencingSolution` (incluye `Cb2e_gnss`, `Cb2e_ins`, `attitude_uncertainty`) | Pipeline matemático puro sin dependencias POO. | Pipeline Integrado |
