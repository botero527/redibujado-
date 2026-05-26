
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
    offset_step = 1 # distancia de cada offset
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

        # -------------------------------
        # DupBorder → UntrimBorder → Squish
        # -------------------------------

        objs_to_squish = [result]  # empezamos con la superficie

        # Duplicar borde
        dup_borders = rs.DuplicateSurfaceBorder(result)
        if dup_borders:
            if isinstance(dup_borders, list):
                objs_to_squish.extend(dup_borders)
                for obj in dup_borders:
                    rs.ObjectLayer(obj, layer_name)
            else:
                objs_to_squish.append(dup_borders)
                rs.ObjectLayer(dup_borders, layer_name)
            print("DupBorder creado en capa: " + layer_name)

        # Ejecutar UntrimBorder
        rs.SelectObject(result)
        rs.Command("_UntrimBorder _Enter", True)
        rs.UnselectAllObjects()
        untrimmed = rs.LastCreatedObjects()
        if untrimmed:
            objs_to_squish.extend(untrimmed)
            for obj in untrimmed:
                rs.ObjectLayer(obj, layer_name)
            print("UntrimBorder generado en capa: " + layer_name)

        # Crear capa "_SQUISH"
        squish_layer = layer_name + "_SQUISH"
        if not rs.IsLayer(squish_layer):
            rs.AddLayer(squish_layer)

        # Seleccionar TODO (superficie + contornos) y hacer Squish
        rs.SelectObjects(objs_to_squish)
        rs.Command("_Squish _KeepProperties=Yes _Enter", True)
        rs.UnselectAllObjects()

        squished = rs.LastCreatedObjects()
        if squished:
            for obj in squished:
                rs.ObjectLayer(obj, squish_layer)

            # --- Centrar geometricamente usando el DupBorder del Squish ---
            rs.UnselectAllObjects()
            rs.SelectObjects(squished)
            before = rs.AllObjects() or []
            rs.Command("_-DupBorder _Enter", echo=False)
            after = rs.AllObjects() or []
            squish_borders = list(set(after) - set(before))

            if squish_borders:
                centroid = rs.CurveAreaCentroid(squish_borders[0])
                if centroid:
                    centroid_pt = centroid[0]
                    translation = rs.VectorCreate([0,0,0], centroid_pt)
                    rs.MoveObjects(squished + squish_borders, translation)
                print("Squish centrado en origen en capa: " + squish_layer)

offset_and_unroll_surfaces()


