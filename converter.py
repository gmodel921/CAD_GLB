# converter.py
"""
Converter module: exposes convert_step_to_glb(src: Path, dst: Path, ...)
Uses pythonocc-core to tessellate STEP/STEP files and trimesh to export GLB.
This version supports an optional progress_callback(percent:int=None, state:str=None, message:str=None)
which is called periodically with status updates.
"""

from pathlib import Path
import traceback
import math
from typing import Callable, Optional

# defaults
DEFAULT_LINEAR_DEFLECTION = 0.1
DEFAULT_IS_RELATIVE = True
DEFAULT_ANGULAR_DEFLECTION = 0.5
DEFAULT_ROUND_DECIMALS = 6

ProgressCB = Optional[Callable[[Optional[int], Optional[str], Optional[str]], None]]

def _safe_call_progress(cb: ProgressCB, percent: int = None, state: str = None, message: str = None):
    if cb:
        try:
            cb(percent=percent, state=state, message=message)
        except Exception:
            # Never fail conversion because of progress callback errors
            pass

def convert_step_to_glb(src, dst,
                        linear_deflection=DEFAULT_LINEAR_DEFLECTION,
                        is_relative=DEFAULT_IS_RELATIVE,
                        angular_deflection=DEFAULT_ANGULAR_DEFLECTION,
                        round_decimals=DEFAULT_ROUND_DECIMALS,
                        progress_callback: ProgressCB = None):
    """
    Convert a STEP (.step/.stp) file to binary glTF (.glb).
    Optional progress_callback(percent:int=None, state:str=None, message:str=None).

    Returns (True, message) on success, (False, message) on failure.
    """
    src = Path(src)
    dst = Path(dst)

    if not src.exists():
        _safe_call_progress(progress_callback, percent=0, state="error", message=f"Input file not found: {src}")
        return False, f"Input file not found: {src}"

    # lazy-import heavy libs so app can start even if they're missing
    try:
        from OCC.Core.STEPControl import STEPControl_Reader
        from OCC.Core.IFSelect import IFSelect_RetDone
        from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
        from OCC.Core.TopExp import TopExp_Explorer
        from OCC.Core.TopAbs import TopAbs_FACE
        from OCC.Core.BRep import BRep_Tool
        from OCC.Core.TopLoc import TopLoc_Location
        import numpy as np
        import trimesh
    except Exception as e:
        _safe_call_progress(progress_callback, percent=0, state="error",
                            message=f"Required libraries missing or failed to import: {e}.")
        return False, f"Required libraries missing or failed to import: {e}. Install pythonocc-core and trimesh."

    try:
        _safe_call_progress(progress_callback, percent=1, state="starting", message="Starting conversion")

        reader = STEPControl_Reader()
        status = reader.ReadFile(str(src))
        if status != IFSelect_RetDone:
            _safe_call_progress(progress_callback, percent=0, state="error", message=f"STEP read failed (status={status})")
            return False, f"STEP read failed (status={status})"
        _safe_call_progress(progress_callback, percent=5, state="loaded", message="STEP file loaded")

        # Transfer roots and get combined shape
        reader.TransferRoots()
        shape = reader.OneShape()

        # Tessellate - inform progress
        _safe_call_progress(progress_callback, percent=8, state="meshing", message="Starting tessellation")
        try:
            # preferred signature: (shape, linear_deflection, is_relative, angular_deflection)
            BRepMesh_IncrementalMesh(shape, float(linear_deflection), bool(is_relative), float(angular_deflection))
        except TypeError:
            # fallback: older bindings accept only (shape, linear_deflection)
            BRepMesh_IncrementalMesh(shape, float(linear_deflection))
        _safe_call_progress(progress_callback, percent=12, state="meshed", message="Tessellation complete")

        # containers
        vertices = []
        faces = []
        vertex_map = {}

        # Count faces first so we can report percent progress reliably
        exp_counter = TopExp_Explorer(shape, TopAbs_FACE)
        total_faces = 0
        while exp_counter.More():
            total_faces += 1
            exp_counter.Next()
        if total_faces == 0:
            _safe_call_progress(progress_callback, percent=0, state="error", message="No faces found in STEP")
            return False, "No faces found in STEP file."

        # Now iterate faces and build triangles
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        face_processed = 0
        tri_count = 0

        # Decide how often to update progress (at least every ~1% or every N faces)
        update_every = max(1, math.ceil(total_faces / 100))  # ~percent granularity

        while exp.More():
            face = exp.Current()
            face_processed += 1

            loc = TopLoc_Location()
            triangulation = BRep_Tool.Triangulation(face, loc)
            if triangulation is None:
                exp.Next()
                # update progress even if no triangulation present
                if face_processed % update_every == 0:
                    pct = 12 + int( (~0) )  # placeholder, overwriten below
                exp.Next()
                continue

            trsf = loc.Transformation()
            n_nodes = triangulation.NbNodes()
            n_tris = triangulation.NbTriangles()

            # insert all nodes, deduplicating by rounded coordinate
            for i in range(1, n_nodes + 1):
                p = triangulation.Node(i)
                try:
                    p_t = p.Transformed(trsf)
                except Exception:
                    p_t = p
                coord = (
                    round(float(p_t.X()), round_decimals),
                    round(float(p_t.Y()), round_decimals),
                    round(float(p_t.Z()), round_decimals)
                )
                if coord in vertex_map:
                    continue
                idx = len(vertices)
                vertex_map[coord] = idx
                vertices.append([float(coord[0]), float(coord[1]), float(coord[2])])

            # now triangles
            for t_idx in range(1, n_tris + 1):
                tri = triangulation.Triangle(t_idx)
                a = triangulation.Node(tri.Value(1))
                b = triangulation.Node(tri.Value(2))
                c = triangulation.Node(tri.Value(3))
                try:
                    a_t = a.Transformed(trsf)
                    b_t = b.Transformed(trsf)
                    c_t = c.Transformed(trsf)
                except Exception:
                    a_t, b_t, c_t = a, b, c

                ca = (round(float(a_t.X()), round_decimals),
                      round(float(a_t.Y()), round_decimals),
                      round(float(a_t.Z()), round_decimals))
                cb = (round(float(b_t.X()), round_decimals),
                      round(float(b_t.Y()), round_decimals),
                      round(float(b_t.Z()), round_decimals))
                cc = (round(float(c_t.X()), round_decimals),
                      round(float(c_t.Y()), round_decimals),
                      round(float(c_t.Z()), round_decimals))

                ia = vertex_map.get(ca)
                ib = vertex_map.get(cb)
                ic = vertex_map.get(cc)

                # if any missing (unexpected), insert them
                if ia is None:
                    ia = len(vertices); vertex_map[ca] = ia; vertices.append([float(ca[0]), float(ca[1]), float(ca[2])])
                if ib is None:
                    ib = len(vertices); vertex_map[cb] = ib; vertices.append([float(cb[0]), float(cb[1]), float(cb[2])])
                if ic is None:
                    ic = len(vertices); vertex_map[cc] = ic; vertices.append([float(cc[0]), float(cc[1]), float(cc[2])])

                faces.append([ia, ib, ic])
                tri_count += 1

            # update progress based on faces processed
            if face_processed % update_every == 0 or face_processed == total_faces:
                # distribute percent between 12% (after tess) and 90% (before export)
                pct = 12 + int((face_processed / total_faces) * (90 - 12))
                _safe_call_progress(progress_callback, percent=pct, state="processing", message=f"Processed {face_processed}/{total_faces} faces")

            exp.Next()

        if not vertices or not faces:
            _safe_call_progress(progress_callback, percent=0, state="error", message="No mesh extracted from STEP file.")
            return False, "No mesh extracted from STEP file."

        _safe_call_progress(progress_callback, percent=90, state="exporting", message="Preparing to export GLB")

        # build trimesh and export glb
        v = np.array(vertices, dtype=np.float64)
        f = np.array(faces, dtype=np.int64)
        mesh = trimesh.Trimesh(vertices=v, faces=f, process=True)

        # ensure normals
        if mesh.vertex_normals is None or len(mesh.vertex_normals) == 0:
            mesh.rezero()
            mesh.fix_normals()

        glb_bytes = mesh.export(file_type='glb')
        dst.write_bytes(glb_bytes)

        _safe_call_progress(progress_callback, percent=100, state="finished", message=f"Converted: faces={total_faces}, triangles={tri_count}, verts={len(vertices)}")
        return True, f"Converted: faces={total_faces}, triangles={tri_count}, verts={len(vertices)}"
    except Exception as e:
        tb = traceback.format_exc()
        _safe_call_progress(progress_callback, percent=0, state="error", message=f"Conversion exception: {e}")
        return False, f"Conversion exception: {e}\n{tb}"
