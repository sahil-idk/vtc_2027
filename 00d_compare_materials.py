"""
Compares radio material definitions between the working built-in scene and
the failing custom scene -- no PathSolver call, just inspecting loaded
material objects, so this runs fast and can't hit the earlier crash.
"""
import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
import sionna.rt as rt
from sionna.rt import load_scene

def describe_materials(scene, label):
    print(f"\n=== {label} ===")
    mats = scene.radio_materials
    print(f"Number of materials: {len(mats)}")
    for name, mat in mats.items():
        print(f"\n  Material: {name}")
        print(f"    Python type: {type(mat)}")
        print(f"    Class hierarchy: {[c.__name__ for c in type(mat).__mro__]}")
        for attr in ['eta_r', 'sigma', 'thickness', 'scattering_coefficient',
                     'xpd_coefficient', 'color']:
            if hasattr(mat, attr):
                try:
                    print(f"    {attr}: {getattr(mat, attr)}")
                except Exception as e:
                    print(f"    {attr}: <error reading: {e}>")

print("Loading built-in munich scene...")
scene_good = load_scene(rt.scene.munich)
describe_materials(scene_good, "BUILT-IN (working) scene")

print("\nLoading custom scene_operator1/scene.xml...")
scene_bad = load_scene("scene_operator1/scene.xml")
describe_materials(scene_bad, "CUSTOM (failing) scene")

print("\n\nCompare the 'Python type' and 'Class hierarchy' lines above --")
print("if the custom scene's materials are a different class than the")
print("built-in scene's, that's very likely the actual bug: an outdated")
print("material class from when the scene was generated.")
