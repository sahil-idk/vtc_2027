"""
Run this BEFORE anything else. Confirms, in order:
  1. Mitsuba/Dr.Jit can initialize the CUDA backend at all.
  2. Sionna RT imports cleanly on top of it.
  3. Autodiff actually works end-to-end (a differentiable variable, a trivial
     computation, backward pass, gradient retrieved) -- the exact mechanism
     Script 2's gradient descent depends on, tested in isolation first.

If this fails, the error will be much easier to diagnose here than buried
inside the full optimization loop.
"""
import drjit as dr
import mitsuba as mi

print("Setting CUDA variant...")
mi.set_variant('cuda_ad_rgb')
print("Mitsuba variant set OK:", mi.variant())

from importlib.metadata import version, PackageNotFoundError
print("drjit version:", version('drjit'))
print("mitsuba version:", version('mitsuba'))
for candidate in ('sionna', 'sionna-rt', 'sionna_rt'):
    try:
        print(f"{candidate} version:", version(candidate))
        break
    except PackageNotFoundError:
        continue
else:
    print("(sionna package metadata not found under common names -- not blocking, continuing)")

print("\nImporting sionna.rt ...")
import sionna.rt as rt
print("sionna.rt imported OK")

print("\nTesting autodiff end-to-end (trivial example, no scene needed)...")
x = mi.Float(3.0)
dr.enable_grad(x)
y = x * x + 2.0 * x          # y = x^2 + 2x, dy/dx = 2x + 2 = 8 at x=3
dr.backward(y)
grad = dr.grad(x)
expected = 8.0
print(f"x=3.0, y={float(y[0])}, dy/dx computed={float(grad[0])}, expected={expected}")
assert abs(float(grad[0]) - expected) < 1e-4, "AUTODIFF SANITY CHECK FAILED -- gradients are not correct"
print("\n*** ALL CHECKS PASSED -- CUDA + autodiff working correctly ***")
