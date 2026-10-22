"""
PyGSN - Test Georeferencing Workflow & Observables
=================================================
Batería de pruebas unitarias para la Fase A.N:
- Ciclo de vida y serialización de SensorObservation.
- Parseo robusto de coordenadas sexagesimales (DMS) y decimales.
- Carga de observaciones en Platform (import_observations_from_txt).
- Resolución desacoplada b-frame <-> e-frame mediante ReferenceSystem.
- Validación de ortonormalidad DCM, residuos métricos y propagación cinemática a cámaras.
"""

import unittest
from unittest.mock import patch
import numpy as np

from PySide6.QtWidgets import QApplication

from core.models import (
    Platform, Sensor, SensorType, ReferenceSystem, SensorObservation,
    parse_dms_or_deg, SensorGeoref, PlatformPose
)
from core.project import Project
from core.georeferencing import solve_multisensor_georeferencing, GeoreferencingSolution
from gui.dialog_georeferencing import DialogGeoreferencingSolver
from gui.dialog_attribute_table import DialogAttributeTable
from gui.canvas_map import CartoMapWidget, CartoMapCanvas
from gui.app import PyGSNMainWindow


class TestGeoreferencingWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_parse_dms_or_deg(self):
        """Valida la conversión de coordenadas sexagesimales y decimales."""
        # Decimal
        self.assertAlmostEqual(parse_dms_or_deg("39.481426"), 39.481426, places=6)
        self.assertAlmostEqual(parse_dms_or_deg("-0.335458"), -0.335458, places=6)

        # DMS positivo: 39º28'53.133637"
        expected_lat = 39.0 + 28.0 / 60.0 + 53.133637 / 3600.0
        parsed_lat = parse_dms_or_deg("39º28'53.133637\"")
        self.assertAlmostEqual(parsed_lat, expected_lat, places=8)

        # DMS negativo: -0º20'7.650964"
        expected_lon = -(0.0 + 20.0 / 60.0 + 7.650964 / 3600.0)
        parsed_lon = parse_dms_or_deg("-0º20'7.650964\"")
        self.assertAlmostEqual(parsed_lon, expected_lon, places=8)

    def test_sensor_observation_model_and_serialization(self):
        """Valida el modelo SensorObservation y su serialización/deserialización."""
        obs = SensorObservation(
            ref_system_id="SRT_01",
            geodetic_deg=(39.481426, -0.335458, 55.867),
            attitude_rpy_deg=(1.2, -1.1, 111.3)
        )
        self.assertTrue(obs.has_geodetic)
        self.assertTrue(obs.has_attitude)

        lat_rad, lon_rad, h = obs.get_lat_lon_h_rad()
        self.assertAlmostEqual(np.degrees(lat_rad), 39.481426, places=6)
        self.assertAlmostEqual(h, 55.867, places=3)

        sens = Sensor(
            code="REC2",
            name="Antena 2",
            sensor_type=SensorType.GNSS,
            lever_arm_b=np.array([0.4, -0.4, -0.015]),
            observation=obs
        )

        d = sens.to_dict()
        self.assertIn("observation", d)
        self.assertEqual(d["observation"]["ref_system_id"], "SRT_01")

        restored = Sensor.from_dict(d)
        self.assertIsNotNone(restored.observation)
        self.assertEqual(restored.observation.ref_system_id, "SRT_01")
        self.assertAlmostEqual(restored.observation.geodetic_deg[0], 39.481426, places=6)

    def test_import_observations_from_txt(self):
        """Valida la importación masiva de observaciones de campo desde texto."""
        plat = Platform(name="Test Rover")
        plat.add_sensor(Sensor(code="REC2", name="Antena 2", sensor_type=SensorType.GNSS))
        plat.add_sensor(Sensor(code="REC3", name="Antena 3", sensor_type=SensorType.GNSS))
        plat.add_sensor(Sensor(code="INS", name="SBG IMU", sensor_type=SensorType.INS))

        txt_obs = (
            "# OBSERVACIONES GNSS\n"
            "REC2 39º28'53.133637\" -0º20'7.650964\" 55.867\n"
            "REC3 39º28'53.109885\" -0º20'7.663129\" 55.829\n"
            "# OBSERVACION INS\n"
            "INS 1.195278 -1.189671 111.269874\n"
        )

        counts = plat.import_observations_from_txt(txt_obs, ref_system_id="SRT_ETRS89")
        self.assertEqual(counts["gnss"], 2)
        self.assertEqual(counts["attitude"], 1)

        rec2 = plat.sensors["REC2"]
        self.assertIsNotNone(rec2.observation)
        self.assertEqual(rec2.observation.ref_system_id, "SRT_ETRS89")
        self.assertTrue(rec2.observation.has_geodetic)

        ins = plat.sensors["INS"]
        self.assertIsNotNone(ins.observation)
        self.assertTrue(ins.observation.has_attitude)
        self.assertAlmostEqual(ins.observation.attitude_rpy_deg[0], 1.195278, places=5)

        # Probar con formato estándar de 4 columnas con espacios/tabulaciones entre columnas
        txt_clean = (
            "Sensor             Latitud            Longitud    h elip.\n"
            "REC2      39º28'53.133637\"    -0º20'7.650964\"     55.867\n"
            "REC3      39º28'53.109885\"    -0º20'7.663129\"     55.829\n"
        )
        counts2 = plat.import_observations_from_txt(txt_clean, ref_system_id="SRT_ETRS89")
        self.assertEqual(counts2["gnss"], 2)

        # Probar coincidencia prioritaria por Nombre de usuario (code=GNSS_01, name="REC2 ")
        plat_gui = Platform(name="Plataforma GUI")
        plat_gui.add_sensor(Sensor(code="GNSS_01", name="REC2 ", sensor_type=SensorType.GNSS))
        plat_gui.add_sensor(Sensor(code="GNSS_02", name=" REC3", sensor_type=SensorType.GNSS))
        counts3 = plat_gui.import_observations_from_txt(txt_clean, ref_system_id="SRT_ETRS89")
        self.assertEqual(counts3["gnss"], 2)
        self.assertIsNotNone(plat_gui.sensors["GNSS_01"].observation)
        self.assertAlmostEqual(plat_gui.sensors["GNSS_01"].observation.geodetic_deg[2], 55.867, places=3)



    def test_decoupled_georeferencing_solution(self):
        """Valida la resolución analítica desacoplada mediante un ReferenceSystem."""
        # 1. Crear el Sistema de Referencia Terrestre desacoplado
        srt = ReferenceSystem(
            id="SRT_01",
            name="ETRS89 Campus",
            ellipsoid="GRS80",
            geoid_undulation_N=50.0166,
            magnetic_declination_deg=-0.700,
            utm_zone=30,
            utm_hemisphere="N"
        )

        # 2. Crear Plataforma y montar sensores
        plat = Platform(name="Rig de Navegacion")
        plat.add_sensor(Sensor(code="PLA", name="Centro Plataforma", sensor_type=SensorType.PLATFORM_ORIGIN,
                               lever_arm_b=np.array([0.0, 0.0, 0.0])))
        plat.add_sensor(Sensor(code="REC2", name="GNSS 2", sensor_type=SensorType.GNSS,
                               lever_arm_b=np.array([0.4, -0.4, -0.015])))
        plat.add_sensor(Sensor(code="REC3", name="GNSS 3", sensor_type=SensorType.GNSS,
                               lever_arm_b=np.array([0.4, 0.4, -0.015])))
        plat.add_sensor(Sensor(code="REC4", name="GNSS 4", sensor_type=SensorType.GNSS,
                               lever_arm_b=np.array([-0.4, -0.4, -0.015])))
        plat.add_sensor(Sensor(code="REC5", name="GNSS 5", sensor_type=SensorType.GNSS,
                               lever_arm_b=np.array([-0.4, 0.4, -0.015])))
        plat.add_sensor(Sensor(code="INS", name="SBG IMU", sensor_type=SensorType.INS,
                               lever_arm_b=np.array([0.0, 0.0, -0.025]),
                               boresight_deg=(0.263568, -0.437974, 2.869214)))
        plat.add_sensor(Sensor(code="CAM1", name="Cámara 1", sensor_type=SensorType.CAMERA,
                               lever_arm_b=np.array([0.7, -0.15, -0.080]),
                               boresight_deg=(0.196543, 0.541674, -1.355847)))

        # 3. Importar observaciones
        txt_obs = (
            "REC2 39º28'53.133637\" -0º20'7.650964\" 55.867\n"
            "REC3 39º28'53.109885\" -0º20'7.663129\" 55.829\n"
            "REC4 39º28'53.143535\" -0º20'7.680928\" 55.883\n"
            "REC5 39º28'53.119474\" -0º20'7.693816\" 55.866\n"
            "INS 1.195278 -1.189671 111.269874\n"
        )
        plat.import_observations_from_txt(txt_obs, ref_system_id=srt.id)

        # 4. Resolver mediante solve_multisensor_georeferencing usando el SRT
        sol = solve_multisensor_georeferencing(
            platform=plat,
            reference_system=srt,
            gnss_sensor_codes=["REC2", "REC3", "REC4", "REC5"],
            ins_sensor_code="INS"
        )

        # 5. Auditoría Matemática
        self.assertAlmostEqual(sol.det_dcm, 1.0, places=9)
        self.assertLess(sol.ortho_error_dcm, 1e-12)

        # Residuos de las 4 antenas deben ser consistentes con la precisión RTK (< 20 mm)
        for code, res_m in sol.residuals_gnss_m.items():
            self.assertLess(res_m, 0.020)

        # Verificar actitud GNSS estimada (Procrustes SVD)
        r, p, y = sol.attitude_gnss_deg
        self.assertAlmostEqual(r, 1.972285, places=4)
        self.assertAlmostEqual(p, -1.926075, places=4)
        self.assertAlmostEqual(y, 112.274661, places=4)

        # Verificar origen PLA en ECEF
        self.assertAlmostEqual(sol.pla_origin_ecef[0], 4929476.0865, delta=0.005)
        self.assertAlmostEqual(sol.pla_origin_ecef[1], -28862.2158, delta=0.005)
        self.assertAlmostEqual(sol.pla_origin_ecef[2], 4033747.4246, delta=0.005)

        # Verificar propagación a cámara CAM1
        self.assertIn("CAM1", sol.results_gnss)
        cam_res = sol.results_gnss["CAM1"]
        self.assertGreater(cam_res.ecef[0], 4900000.0)
        self.assertAlmostEqual(cam_res.h_orto, cam_res.h_ellip - srt.geoid_undulation_N, places=4)

    def test_dialog_georeferencing_solver_instantiation(self):
        """Valida que el diálogo interactivo se instancie limpiamente y soporte el nuevo flujo QGIS."""
        proj = Project(name="Proyecto Test")
        srt = ReferenceSystem(id="SRT_01", name="ETRS89")
        proj.add_reference_system(srt)

        plat = Platform(name="Plataforma Test")
        plat.add_sensor(Sensor(code="REC2", name="REC2", sensor_type=SensorType.GNSS))
        plat.add_sensor(Sensor(code="REC3", name="REC3", sensor_type=SensorType.GNSS))
        plat.add_sensor(Sensor(code="INS", name="INS", sensor_type=SensorType.INS))
        proj.add_platform(plat)

        dlg = DialogGeoreferencingSolver(project=proj)
        self.assertIsNotNone(dlg)
        self.assertEqual(dlg.combo_plat.count(), 1)
        self.assertEqual(dlg.combo_srt.count(), 1)

        # Verificar selector de métodos
        self.assertTrue(dlg.radio_source_gnss.isChecked())
        dlg.radio_source_ins.setChecked(True)
        self.assertTrue(dlg.radio_source_ins.isChecked())

        # Verificar convención de actitud y alternancia de signos
        dlg.spin_roll.setValue(1.5)
        dlg.spin_pitch.setValue(-2.0)
        dlg.spin_yaw.setValue(110.0)
        att_rpy = dlg._get_ins_attitude_deg()
        self.assertAlmostEqual(att_rpy[0], 1.5)
        self.assertAlmostEqual(att_rpy[1], -2.0)
        self.assertAlmostEqual(att_rpy[2], 110.0)

        # Alternar a convención de calibración (alpha, beta, gamma)
        dlg._on_toggle_ins_convention()
        self.assertEqual(dlg.ins_convention, "ABG")
        self.assertAlmostEqual(dlg.spin_roll.value(), -1.5)
        self.assertAlmostEqual(dlg.spin_pitch.value(), 2.0)
        self.assertAlmostEqual(dlg.spin_yaw.value(), -110.0)
        # _get_ins_attitude_deg debe seguir devolviendo Roll, Pitch, Yaw equivalente
        att_rpy2 = dlg._get_ins_attitude_deg()
        self.assertAlmostEqual(att_rpy2[0], 1.5)
        self.assertAlmostEqual(att_rpy2[1], -2.0)
        self.assertAlmostEqual(att_rpy2[2], 110.0)

        # Alternar de regreso a RPY
        dlg._on_toggle_ins_convention()
        self.assertEqual(dlg.ins_convention, "RPY")
        self.assertAlmostEqual(dlg.spin_roll.value(), 1.5)

    def test_sensor_georef_and_platform_pose_models(self):
        """Valida los modelos SensorGeoref y PlatformPose, sus propiedades y serialización."""
        georef = SensorGeoref(
            ref_system_id="SRT_01",
            ref_system_name="ETRS89 / UTM 30N",
            ecef=np.array([4929476.0, -28862.0, 4033747.0], dtype=np.float64),
            lat_deg=39.4814,
            lon_deg=-0.3354,
            h_ellip_m=55.8,
            utm_easting_m=728000.0,
            utm_northing_m=4373000.0,
            utm_zone=30,
            utm_hemisphere="N",
            h_ortho_m=5.8,
            computed_via="SVD"
        )
        self.assertEqual(georef.ref_system_id, "SRT_01")
        d_geo = georef.to_dict()
        restored_geo = SensorGeoref.from_dict(d_geo)
        self.assertEqual(restored_geo.ref_system_id, "SRT_01")
        self.assertAlmostEqual(restored_geo.ecef[0], 4929476.0)

        # Asignar a un Sensor
        s = Sensor(code="CAM1", name="Cámara Frontal", sensor_type=SensorType.CAMERA, georef=georef)
        self.assertTrue(s.is_georeferenced)
        attrs = s.get_attributes_dict()
        self.assertEqual(attrs["code"], "CAM1")
        self.assertEqual(attrs["is_georef"], True)
        self.assertEqual(attrs["srt_id"], "SRT_01")
        self.assertAlmostEqual(attrs["xe_m"], 4929476.0)

        # Serialización de Sensor con georef
        s_dict = s.to_dict()
        s_restored = Sensor.from_dict(s_dict)
        self.assertTrue(s_restored.is_georeferenced)
        self.assertAlmostEqual(s_restored.georef.lat_deg, 39.4814)

        # Plataforma con pose_e
        pose = PlatformPose(
            ref_system_id="SRT_01",
            ref_system_name="ETRS89",
            ecef=np.array([4929476.0, -28862.0, 4033747.0]),
            lat_deg=39.4814,
            lon_deg=-0.3354,
            h_ellip_m=55.8,
            utm_easting_m=728000.0,
            utm_northing_m=4373000.0,
            utm_zone=30,
            utm_hemisphere="N",
            h_ortho_m=5.8,
            attitude_rpy_deg=(1.2, -1.1, 111.3),
            method="SVD"
        )
        plat = Platform(name="Plataforma Pose Test", pose_e=pose)
        plat.add_sensor(s)
        p_dict = plat.to_dict()
        plat_restored = Platform.from_dict(p_dict)
        self.assertIsNotNone(plat_restored.pose_e)
        self.assertEqual(plat_restored.pose_e.method, "SVD")
        self.assertAlmostEqual(plat_restored.pose_e.attitude_rpy_deg[0], 1.2)
        self.assertTrue(plat_restored.sensors["CAM1"].is_georeferenced)

    def test_dialog_attribute_table_instantiation(self):
        """Valida que DialogAttributeTable se instancie, filtre y genere CSV correctamente."""
        plat = Platform(name="Rig Test Atributos")
        plat.add_sensor(Sensor(code="REC2", name="Antena 2", sensor_type=SensorType.GNSS,
                               lever_arm_b=np.array([0.4, -0.4, 0.0])))
        plat.add_sensor(Sensor(code="CAM1", name="Cámara", sensor_type=SensorType.CAMERA,
                               lever_arm_b=np.array([0.7, 0.0, 0.0])))

        dlg = DialogAttributeTable(platform=plat)
        self.assertEqual(dlg.table.rowCount(), 2)
        self.assertEqual(dlg.table.columnCount(), 21)

        # Filtro de búsqueda
        dlg._on_filter_changed("CAM")
        self.assertTrue(dlg.table.isRowHidden(0))
        self.assertFalse(dlg.table.isRowHidden(1))

        dlg._on_filter_changed("")
        self.assertFalse(dlg.table.isRowHidden(0))
        self.assertFalse(dlg.table.isRowHidden(1))

        # Generación de CSV
        csv_txt = dlg._generate_csv_text()
        self.assertIn("Código;Nombre;Tipo", csv_txt)
        self.assertIn("REC2", csv_txt)
        self.assertIn("CAM1", csv_txt)

    def test_dialog_georeferencing_apply_to_project(self):
        """Valida que resolver en DialogGeoreferencingSolver y aplicar enriquezca sensores y plataforma."""
        proj = Project(name="Proyecto Georef Apply Test")
        srt = ReferenceSystem(
            id="SRT_01",
            name="ETRS89 Campus",
            ellipsoid="GRS80",
            geoid_undulation_N=50.0,
            utm_zone=30,
            utm_hemisphere="N"
        )
        proj.add_reference_system(srt)

        plat = Platform(name="Rig Test")
        plat.add_sensor(Sensor(code="PLA", name="Centro Plataforma", sensor_type=SensorType.PLATFORM_ORIGIN,
                               lever_arm_b=np.array([0.0, 0.0, 0.0])))
        plat.add_sensor(Sensor(code="REC2", name="GNSS 2", sensor_type=SensorType.GNSS,
                               lever_arm_b=np.array([0.4, -0.4, -0.015])))
        plat.add_sensor(Sensor(code="REC3", name="GNSS 3", sensor_type=SensorType.GNSS,
                               lever_arm_b=np.array([0.4, 0.4, -0.015])))
        plat.add_sensor(Sensor(code="REC4", name="GNSS 4", sensor_type=SensorType.GNSS,
                               lever_arm_b=np.array([-0.4, -0.4, -0.015])))
        plat.add_sensor(Sensor(code="CAM1", name="Cámara", sensor_type=SensorType.CAMERA,
                               lever_arm_b=np.array([0.7, 0.0, 0.0])))
        proj.add_platform(plat)

        # Importar observaciones GNSS para antenas
        txt_obs = (
            "REC2 39º28'53.133637\" -0º20'7.650964\" 55.867\n"
            "REC3 39º28'53.109885\" -0º20'7.663129\" 55.829\n"
            "REC4 39º28'53.143535\" -0º20'7.680928\" 55.883\n"
        )
        plat.import_observations_from_txt(txt_obs, ref_system_id=srt.id)

        dlg = DialogGeoreferencingSolver(project=proj)
        self.assertFalse(dlg.btn_apply.isEnabled())

        # Ejecutar solución
        dlg.solve()
        self.assertTrue(dlg.btn_apply.isEnabled())
        self.assertIsNotNone(dlg.last_solution)
        self.assertEqual(dlg.main_tabs.currentIndex(), 1)  # Conmuta a pestaña 2 de resultados

        # Aplicar cambios al proyecto
        with patch("PySide6.QtWidgets.QMessageBox.information"):
            dlg._on_apply_to_project()

        # Verificar que la plataforma tiene pose_e
        self.assertIsNotNone(plat.pose_e)
        self.assertEqual(plat.pose_e.ref_system_id, "SRT_01")
        self.assertGreater(plat.pose_e.ecef[0], 4900000.0)
        self.assertAlmostEqual(plat.pose_e.h_ortho_m, plat.pose_e.h_ellip_m - 50.0, places=3)

        # Verificar que CAM1 quedó enriquecida con sus atributos georreferenciados
        cam1 = plat.sensors["CAM1"]
        self.assertTrue(cam1.is_georeferenced)
        self.assertEqual(cam1.georef.ref_system_id, "SRT_01")
        self.assertGreater(cam1.georef.utm_easting_m, 100000.0)
        self.assertGreater(cam1.georef.utm_northing_m, 1000000.0)
        self.assertAlmostEqual(cam1.georef.h_ortho_m, cam1.georef.h_ellip_m - 50.0, places=3)


    def test_import_sensors_from_table_excel(self):
        """Valida la importación completa desde tabla Excel (.xlsx) con geometría y observables."""
        from pathlib import Path
        table_path = Path(__file__).resolve().parent.parent / "data" / "calibracion_rig_multisensor.csv"
        if not table_path.exists():
            table_path = Path(r"c:\Users\bryan\Desktop\UPV\S3\2_Sensores\Practica1\plataforma.xlsx")
        if not table_path.exists():
            self.skipTest("Tabla de sensores no encontrada")

        plat = Platform(name="Plataforma Calibracion")
        imported = plat.import_sensors_from_table(table_path)

        self.assertEqual(len(imported), 7)
        self.assertIn("REC2", plat.sensors)
        self.assertIn("REC3", plat.sensors)
        self.assertIn("REC4", plat.sensors)
        self.assertIn("REC5", plat.sensors)
        self.assertIn("INS", plat.sensors)
        self.assertIn("CAM1", plat.sensors)
        self.assertIn("CAM2", plat.sensors)

        # Validar lever-arms 3D y observables de REC2
        rec2 = plat.sensors["REC2"]
        self.assertEqual(rec2.sensor_type, SensorType.GNSS)
        np.testing.assert_allclose(rec2.lever_arm_b, [0.4, -0.4, -0.015])
        self.assertIsNotNone(rec2.observation)
        self.assertTrue(rec2.observation.has_geodetic)
        self.assertAlmostEqual(rec2.observation.geodetic_deg[0], 39.48142601, places=6)
        self.assertAlmostEqual(rec2.observation.geodetic_deg[1], -0.33545860, places=6)
        self.assertAlmostEqual(rec2.observation.geodetic_deg[2], 55.867, places=3)

        # Validar lever-arm, boresight y observables de INS
        ins = plat.sensors["INS"]
        self.assertEqual(ins.sensor_type, SensorType.INS)
        np.testing.assert_allclose(ins.lever_arm_b, [0.0, 0.0, -0.025])
        np.testing.assert_allclose(ins.boresight_deg, [0.263568, -0.437974, 2.869214], atol=1e-5)
        self.assertIsNotNone(ins.observation)
        self.assertTrue(ins.observation.has_attitude)
        self.assertAlmostEqual(ins.observation.attitude_rpy_deg[0], 1.195278, places=6)
        self.assertAlmostEqual(ins.observation.attitude_rpy_deg[1], -1.189671, places=6)
        self.assertAlmostEqual(ins.observation.attitude_rpy_deg[2], 111.269874, places=6)

        # Validar CAM1 y CAM2
        cam1 = plat.sensors["CAM1"]
        self.assertEqual(cam1.sensor_type, SensorType.CAMERA)
        np.testing.assert_allclose(cam1.lever_arm_b, [0.7, -0.15, -0.08])
        np.testing.assert_allclose(cam1.boresight_deg, [0.196543, 0.541674, -1.355847], atol=1e-5)

        cam2 = plat.sensors["CAM2"]
        self.assertEqual(cam2.sensor_type, SensorType.CAMERA)
        np.testing.assert_allclose(cam2.lever_arm_b, [0.7, 0.15, -0.08])
        np.testing.assert_allclose(cam2.boresight_deg, [-0.287495, 0.426588, 1.128792], atol=1e-5)

        # Validar precarga automática en el solver
        proj = Project(name="Project Excel Auto")
        srt = ReferenceSystem(
            id="SRT_01",
            name="ETRS89",
            ellipsoid="GRS80",
            geoid_undulation_N=50.0166,
            magnetic_declination_deg=-0.7000,
            utm_zone=30,
            utm_hemisphere="N"
        )
        proj.add_reference_system(srt)
        proj.add_platform(plat)

        dlg = DialogGeoreferencingSolver(project=proj)
        # La tabla de antenas debe tener 4 antenas y estar activas
        self.assertEqual(dlg.table_antennas.rowCount(), 4)

        # El INS debe estar precargado en los spinboxes
        self.assertAlmostEqual(dlg.spin_roll.value(), 1.195278, places=5)
        self.assertAlmostEqual(dlg.spin_pitch.value(), -1.189671, places=5)
        self.assertAlmostEqual(dlg.spin_yaw.value(), 111.269874, places=5)

        # Resolver con ambos métodos
        dlg.combo_method.setCurrentIndex(2)  # Ambos (SVD + INS)
        dlg.solve()
        self.assertIsNotNone(dlg.last_solution)

        # Comprobar actitud SVD
        self.assertAlmostEqual(dlg.last_solution.attitude_gnss_deg[0], 1.972285, places=5)
        self.assertAlmostEqual(dlg.last_solution.attitude_gnss_deg[1], -1.926075, places=5)
        self.assertAlmostEqual(dlg.last_solution.attitude_gnss_deg[2], 112.274661, places=5)

        # Comprobar actitud INS con boresight y declinación -0.7
        self.assertAlmostEqual(dlg.last_solution.attitude_ins_total_deg[0], 1.375827, places=5)
        self.assertAlmostEqual(dlg.last_solution.attitude_ins_total_deg[1], -1.698494, places=5)
        self.assertAlmostEqual(dlg.last_solution.attitude_ins_total_deg[2], 114.828264, places=5)

    def test_utm_inverse_roundtrip(self):
        """Valida que utm_inverse sea la función inversa exacta de utm_projection a nivel sub-milimétrico."""
        from core.geodesy import utm_projection, utm_inverse, GRS80
        lat_orig = np.radians(np.float64(39.4814))
        lon_orig = np.radians(np.float64(-0.3354))

        # Ida: Geodésicas -> UTM Huso 30N
        easting, northing, zone = utm_projection(lat_orig, lon_orig, zone=30, hemisphere="N", ell=GRS80)
        self.assertEqual(zone, 30)
        self.assertTrue(720000.0 < easting < 740000.0)
        self.assertTrue(4370000.0 < northing < 4380000.0)

        # Vuelta: UTM -> Geodésicas
        lat_inv, lon_inv = utm_inverse(easting, northing, zone=30, hemisphere="N", ell=GRS80)

        # Diferencia métrica sobre el elipsoide GRS80
        d_lat_m = abs(lat_inv - lat_orig) * 6378137.0
        d_lon_m = abs(lon_inv - lon_orig) * np.cos(lat_orig) * 6378137.0

        self.assertLess(d_lat_m, 1e-3)  # Precisión sub-milimétrica (< 1 mm)
        self.assertLess(d_lon_m, 1e-3)

    def test_carto_map_widget_and_workspace(self):
        """Valida la creación del CartoMapWidget, la transformación de coordenadas y la apertura en el workspace."""
        from gui.canvas_map import CartoMapWidget, CartoMapCanvas
        from gui.app import PyGSNMainWindow

        proj = Project(name="Test Carto Map", platforms={})
        srt = ReferenceSystem(id="SRT_TEST", name="ETRS89 / UTM 30N", ellipsoid="GRS80", utm_zone=30, utm_hemisphere="N")
        proj.add_reference_system(srt)
        proj.set_active_reference_system("SRT_TEST")

        plat = Platform(id="PLAT_MAP", name="Vehículo Carto", length_m=4.0, width_m=2.0)
        plat.pose_e = PlatformPose(
            ref_system_id="SRT_TEST",
            ref_system_name="ETRS89 / UTM 30N",
            ecef=np.array([4929476.0, -28862.0, 4033747.0]),
            lat_deg=39.4814,
            lon_deg=-0.3354,
            h_ellip_m=55.8,
            utm_easting_m=725450.0,
            utm_northing_m=4372850.0,
            utm_zone=30,
            utm_hemisphere="N",
            h_ortho_m=5.8,
            attitude_rpy_deg=(1.2, -1.0, 110.0),
            dcm_b2e=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            method="SVD"
        )
        proj.add_platform(plat)

        # Crear widget de mapa (sin toolbar invasiva, limpio)
        map_widget = CartoMapWidget(get_project=lambda: proj, ref_system_id="SRT_TEST")
        self.assertIsNotNone(map_widget)
        self.assertEqual(map_widget.canvas.ref_system_id, "SRT_TEST")

        # Probar transformaciones directas e inversas de pantalla
        map_widget.canvas.resize(800, 600)
        e_init, n_init = 725450.0, 4372850.0
        sx, sy = map_widget.canvas.utm_to_screen(e_init, n_init)
        e_back, n_back = map_widget.canvas.screen_to_utm(sx, sy)
        self.assertAlmostEqual(e_init, e_back, places=3)
        self.assertAlmostEqual(n_init, n_back, places=3)

        # Probar conmutación de terna n-frame
        self.assertEqual(map_widget.canvas.n_frame_convention, "NED")
        map_widget.canvas.n_frame_convention = "ENU"
        self.assertEqual(map_widget.canvas.n_frame_convention, "ENU")

        # Probar apertura en PyGSNMainWindow
        win = PyGSNMainWindow()
        win.project = proj
        win.open_reference_system_map("SRT_TEST")
        self.assertIn("SRT_TEST", win.map_canvases)
        self.assertEqual(win.workspace.count(), 1)
        self.assertEqual(win.workspace.tabText(0), "Mapa: ETRS89 / UTM 30N")

        # Si se vuelve a solicitar, no duplica pestaña
        win.open_reference_system_map("SRT_TEST")
        self.assertEqual(win.workspace.count(), 1)

    def test_platform_utm_bounding_box(self):
        """Valida el cálculo riguroso de la Bounding Box orientada al Norte cartográfico."""
        plat = Platform(id="PLA_TEST", name="Vehículo Test", length_m=4.0, width_m=2.0)
        plat.pose_e = PlatformPose(
            ref_system_id="SRT_TEST",
            utm_easting_m=725450.0,
            utm_northing_m=4372850.0,
            utm_zone=30,
            utm_hemisphere="N",
            attitude_rpy_deg=(0.0, 0.0, 0.0), # Rumbo Norte exacto
        )
        plat.add_sensor(Sensor(code="S1", name="Sensor 1", lever_arm_b=np.array([2.5, 0.0, 0.0])))

        bbox = plat.get_utm_bounding_box()
        self.assertIsNotNone(bbox)
        # Con rumbo 0 (Norte), Xb apunta hacia Norte y Yb hacia Este
        # Chasis: Xb in [-2, 2], Yb in [-1, 1] -> N in [4372848, 4372852], E in [725449, 725451]
        # Sensor S1: Xb=2.5, Yb=0 -> N=4372852.5, E=725450
        self.assertAlmostEqual(bbox["min_e"], 725449.0, places=3)
        self.assertAlmostEqual(bbox["max_e"], 725451.0, places=3)
        self.assertAlmostEqual(bbox["min_n"], 4372848.0, places=3)
        self.assertAlmostEqual(bbox["max_n"], 4372852.5, places=3)
        self.assertAlmostEqual(bbox["span_e"], 2.0, places=3)
        self.assertAlmostEqual(bbox["span_n"], 4.5, places=3)

    def test_carto_map_context_menu_and_layer_visibility(self):
        """Valida el menú contextual del mapa y el control reactivo de visibilidad de capas."""
        proj = Project(name="Test Visibility", platforms={})
        srt = ReferenceSystem(id="SRT_1", name="ETRS89 / UTM 30N", show_basemap=True)
        proj.add_reference_system(srt)

        map_widget = CartoMapWidget(get_project=lambda: proj, ref_system_id="SRT_1")
        canvas = map_widget.canvas

        # Elementos auxiliares del lienzo por defecto visibles
        self.assertTrue(canvas.show_compass)
        self.assertTrue(canvas.show_grid)
        self.assertTrue(canvas.show_osm)
        self.assertTrue(canvas.show_scalebar)

        # Conmutación mediante métodos contextuales
        canvas._toggle_compass(False)
        self.assertFalse(canvas.show_compass)
        canvas._toggle_grid(False)
        self.assertFalse(canvas.show_grid)
        canvas._toggle_osm(False)
        self.assertFalse(canvas.show_osm)
        canvas._toggle_scalebar(False)
        self.assertFalse(canvas.show_scalebar)

        # Control de capas desde dock de jerarquía
        map_widget.set_layer_visibility("basemap", False)
        self.assertIn("basemap", canvas.hidden_layers)
        self.assertFalse(canvas.show_osm)

        map_widget.set_layer_visibility("basemap", True)
        self.assertNotIn("basemap", canvas.hidden_layers)
        self.assertTrue(canvas.show_osm)

    def test_hierarchy_dock_srt_layer_tree(self):
        """Valida la estructuración del árbol de capas en el e-frame (SRT) con subcapas checkables."""
        from gui.dock_hierarchy import HierarchyDock
        from PySide6.QtCore import Qt

        proj = Project(name="Test Dock", platforms={})
        srt = ReferenceSystem(id="SRT_TEST", name="ETRS89 / UTM 30N")
        proj.add_reference_system(srt)

        plat = Platform(id="PLA1", name="Rover 1", length_m=2.0, width_m=1.0)
        plat.pose_e = PlatformPose(ref_system_id="SRT_TEST", utm_easting_m=725000.0, utm_northing_m=4370000.0)
        plat.add_sensor(Sensor(code="REC2", name="Antena GNSS", sensor_type=SensorType.GNSS))
        proj.add_platform(plat)

        dock = HierarchyDock(get_project=lambda: proj, on_project_changed=lambda: None)
        dock.rebuild_tree()

        # Localizar el nodo de SRT_TEST en el árbol
        root = dock.tree.topLevelItem(0)
        srts_group = root.child(1) # Rama 2: Sistemas de Referencia
        srt_item = srts_group.child(0)

        # Debe tener 2 hijos: Mapa Base y Plataforma PLA1
        self.assertEqual(srt_item.childCount(), 2)
        basemap_node = srt_item.child(0)
        self.assertEqual(basemap_node.text(0), "Mapa Base (OpenStreetMap)")
        self.assertEqual(basemap_node.checkState(0), Qt.Checked)

        plat_node = srt_item.child(1)
        self.assertIn("Rover 1", plat_node.text(0))
        self.assertEqual(plat_node.checkState(0), Qt.Checked)

        # Subhijos de la plataforma: Chasis, Sensores, Terna n-frame
        self.assertEqual(plat_node.childCount(), 3)
        self.assertIn("Chasis", plat_node.child(0).text(0))
        self.assertIn("Sensores", plat_node.child(1).text(0))
        self.assertIn("Terna n-frame", plat_node.child(2).text(0))


    def test_utm_meridian_convergence_and_heading_grid(self):
        """Valida la formulación rigurosa de convergencia de meridianos UTM y rumbo de cuadrícula."""
        from core.geodesy import utm_meridian_convergence
        import math

        lat_rad = math.radians(39.481426)
        lon_rad = math.radians(-0.335458)
        gamma_rad = utm_meridian_convergence(lat_rad, lon_rad, zone=30)
        gamma_deg = math.degrees(gamma_rad)

        # Para Huso 30 (meridiano central -3°), en lon=-0.335°, delta_lon = +2.665°
        # gamma ≈ delta_lon * sin(phi) = 2.665° * sin(39.48°) ≈ 1.694°
        self.assertAlmostEqual(gamma_deg, 1.6949, places=3)

        pose = PlatformPose(
            ref_system_id="SRT_01",
            utm_easting_m=729171.0,
            utm_northing_m=4373592.0,
            lat_deg=39.481426,
            lon_deg=-0.335458,
            utm_zone=30,
            attitude_rpy_deg=(0.0, 0.0, 112.27466)
        )
        self.assertAlmostEqual(pose.convergence_deg, 1.6949, places=3)
        # El rumbo sobre la cuadrícula debe ser exactamente yaw_deg - gamma_deg ≈ 110.58°
        heading_grid = pose.yaw_deg - pose.convergence_deg
        self.assertAlmostEqual(heading_grid, 110.5797, places=3)

    def test_canvas_map_drawing_robustness(self):
        """Verifica que todas las rutinas vectoriales del mapa se ejecuten sin excepciones."""
        from PySide6.QtGui import QImage, QPainter

        proj = Project(name="Test Render", platforms={})
        plat = Platform(id="PLAT_01", name="PLA1", length_m=2.0, width_m=1.0)
        plat.pose_e = PlatformPose(
            ref_system_id="SRT_01",
            utm_easting_m=729171.0,
            utm_northing_m=4373592.0,
            attitude_rpy_deg=(0.0, 0.0, 110.0)
        )
        plat.add_sensor(Sensor(code="REC2", name="Antena", sensor_type=SensorType.GNSS))
        proj.add_platform(plat)

        canvas = CartoMapCanvas(get_project=lambda: proj, ref_system_id="SRT_01")
        canvas.resize(400, 300)

        img = QImage(400, 300, QImage.Format_ARGB32)
        p = QPainter(img)

        # Comprobar que ninguna rutina lanza errores ni interrumpe el ciclo
        canvas._draw_utm_grid(p)
        canvas._draw_platforms(p)
        canvas._draw_sensors(p)
        canvas._draw_n_frame_triad(p)
        canvas._draw_compass_rose(p)
        canvas._draw_scale_bar(p)
        p.end()

        # Comprobar convención ENU
        canvas.n_frame_convention = "ENU"
        p2 = QPainter(img)
        canvas._draw_n_frame_triad(p2)
        p2.end()

    def test_hierarchy_dock_basemap_sync_method(self):
        """Valida que set_basemap_checked actualice el árbol sin bucles infinitos."""
        from gui.dock_hierarchy import HierarchyDock
        from PySide6.QtCore import Qt

        proj = Project(name="Test Sync", platforms={})
        srt = ReferenceSystem(id="SRT_SYNC", name="ETRS89 / UTM 30N")
        proj.add_reference_system(srt)

        dock = HierarchyDock(get_project=lambda: proj, on_project_changed=lambda: None)
        dock.rebuild_tree()

        # Llamar a set_basemap_checked para False y True
        dock.set_basemap_checked("SRT_SYNC", False)
        root = dock.tree.topLevelItem(0)
        srts_group = root.child(1)
        srt_node = srts_group.child(0)
        basemap_node = srt_node.child(0)
        self.assertEqual(basemap_node.checkState(0), Qt.Unchecked)

        dock.set_basemap_checked("SRT_SYNC", True)
        self.assertEqual(basemap_node.checkState(0), Qt.Checked)


if __name__ == "__main__":
    unittest.main()



