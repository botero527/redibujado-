  # -*- coding: utf-8 -*-

import rhinoscriptsyntax as rs

def offset_and_unroll_surfaces():
    # Seleccionar la superficie original
    srf = rs.GetObject("Selecciona una superficie", rs.filter.surface)
    if not srf:
        return

    # Crear lista de capas P1 a P50
    target_layers = ["P" + str(i) for i in range(1, 51)]
    available_layers = rs.LayerNames()

    # Verificar que existan todas las capas P1 a P50
    for layer in target_layers:
        if layer not in available_layers:
            print("Falta la capa: " + layer)
            return

    # Parámetros
    num_offsets = 50
    offset_step = 1.0  # distancia de cada offset
    fixed_dir = (0,0,-1)  # dirección fija

    for i in range(num_offsets):
        offset_distance = offset_step * (i + 1)
        result = rs.OffsetSurface(srf, offset_distance, create_solid=False)
        if not result:
            print("Error en offset #" + str(i + 1))
            break

        # --- Forzar dirección fija ---
        normal = rs.SurfaceNormal(result, (0.5,0.5))
        if rs.VectorDotProduct(normal, fixed_dir) < 0:
            rs.FlipSurface(result)

        # Asignar a capa Pn
        layer_name = target_layers[i]
        rs.ObjectLayer(result, layer_name)
        print("Offset #" + str(i+1) + " creado en capa: " + layer_name)

        # Intentar desplegar (UnrollSrf)
        unrolled = rs.UnrollSurface(result)
        if unrolled:
            # Crear capa UNROLL si no existe
            unroll_layer = layer_name + "_CAPA"
            if not rs.IsLayer(unroll_layer):
                rs.AddLayer(unroll_layer)

            for obj in unrolled:
                rs.ObjectLayer(obj, unroll_layer)

                # ---- SUAVIZAR CURVAS ----
                if rs.IsCurve(obj):
                    pts = rs.CurvePoints(obj)
                    if pts and len(pts) > 10:  # muchas subdivisiones = posible esquina facetada
                        # Intentar crear un arco con los puntos
                        arco = rs.ArcFitPoints(pts)
                        if arco:
                            rs.DeleteObject(obj)
                            rs.ObjectLayer(arco, unroll_layer)
                            print("Curva reemplazada por ARCO en capa: " + unroll_layer)
                        else:
                            # Si no se puede arco → suavizar como spline
                            target_points = max(10, int(len(pts) * 0.3))
                            smooth = rs.RebuildCurve(obj, degree=3, point_count=target_points)
                            if smooth:
                                rs.DeleteObject(obj)
                                rs.ObjectLayer(smooth, unroll_layer)
                                print("Curva suavizada como SPLINE en capa: " + unroll_layer)
        else:
            print("No se pudo desarrollar (unroll) la superficie en capa: " + layer_name)

offset_and_unroll_surfaces()
