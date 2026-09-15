"""
Isolates: is the crash caused by (a) something specific to the custom
scene.xml's material definitions, or (b) a broader environment problem?

Loads one of Sionna's OWN built-in reference scenes instead of the custom
one, and runs the exact same PathSolver call. If this succeeds where the
custom scene failed, the problem is conclusively in scene.xml's materials,
not the CUDA/Mitsuba/Sionna installation -- meaning the scene needs
rebuilding against the current sionna-rt material API, not a reinstall.
"""
import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')  # NOT cuda_ad_rgb -- Sionna's Jones-matrix/polarization math needs mono_polarized, per Sionna docs
import sionna.rt as rt
from sionna.rt import load_scene, Transmitter, Receiver, PlanarArray, PathSolver

print("Loading Sionna's built-in reference scene (munich)...")
scene = load_scene(rt.scene.munich)
print("Built-in scene loaded OK.")

scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")

tx = Transmitter(name="tx_probe", position=[0, 0, 30])
scene.add(tx)
scene.add(Receiver(name="rx_probe_0", position=[50, 0, 1.5]))

print("Running PathSolver on built-in scene...")
solver = PathSolver()
paths = solver(scene=scene, max_depth=5)
print("\n*** SUCCESS -- built-in scene works fine. ***")
print("This means the crash is specific to scene_operator1/scene.xml's material")
print("definitions, most likely a version mismatch between when that scene was")
print("built and the currently-installed sionna-rt 2.0.1 material API.")
print("Fix: scene_operator1/scene.xml needs rebuilding against the current API,")
print("not a Python/CUDA environment fix.")
