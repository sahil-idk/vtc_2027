"""
Ground-truth exploration of Sionna RT 2.0.1's actual Paths/PathSolver API on
YOUR installed version and YOUR real scene -- before writing the full
gradient-descent script against possibly-wrong guessed method names.

No gradients, no optimization, no loop -- just: load scene, add one
transmitter at a WCL tower position, add a couple receivers nearby, run
PathSolver once, print everything useful about the returned object so we
know exactly what to call in the real Script 2.

Usage: python 00b_explore_paths_api.py <scene_path> <op1_towers_wcl_init.csv>
"""
import sys
import pandas as pd
import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
import sionna.rt as rt
from sionna.rt import load_scene, Transmitter, Receiver, PlanarArray, PathSolver


def main(scene_path, towers_csv):
    print(f"Loading scene: {scene_path}")
    scene = load_scene(scene_path)
    print("Scene loaded OK. Scene attributes (first pass):")
    print([a for a in dir(scene) if not a.startswith('_')][:30])

    towers = pd.read_csv(towers_csv).sort_values('n_obs', ascending=False)
    top = towers.iloc[0]
    print(f"\nUsing top tower by n_obs: cell_id={top.cell_id}, "
          f"wcl_lat={top.wcl_lat}, wcl_lon={top.wcl_lon}")

    # Sionna RT needs explicit antenna arrays set on the scene before adding tx/rx
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")

    # Place transmitter at local origin (0,0,30) -- we'll wire real lat/lon
    # projection into Script 2 once this confirms the API works at all.
    tx = Transmitter(name="tx_probe", position=[0, 0, 30])
    scene.add(tx)

    # A few receivers at varying distances/heights, in the local frame
    rx_positions = [[10, 0, 1.5], [50, 0, 1.5], [100, 0, 1.5], [50, 50, 1.5]]
    for i, pos in enumerate(rx_positions):
        scene.add(Receiver(name=f"rx_probe_{i}", position=pos))

    print("\nRunning PathSolver...")
    solver = PathSolver()
    paths = solver(scene=scene, max_depth=5)
    print("PathSolver ran OK. Return type:", type(paths))

    print("\n--- Available attributes/methods on the returned paths object ---")
    attrs = [a for a in dir(paths) if not a.startswith('_')]
    print(attrs)

    print("\n--- Trying known-plausible power/gain accessors, one at a time ---")
    for attr_name in ['a', 'tau', 'cfr', 'received_power_dbm', 'power', 'cir']:
        try:
            val = getattr(paths, attr_name)
            if callable(val):
                print(f"'{attr_name}' is a METHOD, signature/help below:")
                help(val)
            else:
                print(f"'{attr_name}' is a PROPERTY, type={type(val)}, "
                      f"shape={getattr(val, 'shape', 'n/a')}")
        except AttributeError:
            print(f"'{attr_name}': NOT FOUND on this object")
        except Exception as e:
            print(f"'{attr_name}': exists but errored on access -- {e}")

    print("\n--- Scene cleanup ---")
    scene.remove("tx_probe")
    for i in range(len(rx_positions)):
        scene.remove(f"rx_probe_{i}")
    print("Done. Paste this entire output back for Script 2 to be written correctly.")


if __name__ == '__main__':
    scene_path = sys.argv[1] if len(sys.argv) > 1 else 'scene_operator1/scene.xml'
    towers_csv = sys.argv[2] if len(sys.argv) > 2 else 'op1_towers_wcl_init.csv'
    main(scene_path, towers_csv)
