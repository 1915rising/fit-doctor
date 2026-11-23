# Fit Doctor

A fit checkup for outfits in Blender — the numbers you want
*before* the graft reaches Unity or a headset, while the fix is
still a modelling decision instead of a re-export.

An outfit can look perfect in a still render and still be broken
in ways that only show up in motion: it doesn't follow the body's
shape keys, it drags the wrong arm when the left one moves, whole
patches never move at all because nothing is weighted, and skirts
poke through thighs on the first step. In the case that motivated
this tool, an AI-generated gown grafted onto a game body shipped
with a floating glove and clipping nobody caught — because nobody
had run the counts. The diagnosis existed as a $9.99 add-on.
This is the free one.

Fit Doctor is **diagnosis only**. It changes nothing on your
meshes; it tells you, with counts, where the fit is wrong.

## What it checks

| Check | Catches |
|---|---|
| Shape-key follow-through | Body shape keys (excluding the reference key) the outfit doesn't have. An outfit missing a key can't follow the body when that key is driven. |
| L/R weight contamination | Outfit vertices clearly on one side of the local X axis carrying weight for opposite-side groups (`.L`/`.R`, `_L`/`_R`, ` L`/` R`, `Left`/`Right` naming), with per-side and per-group counts. |
| Unweighted vertices | Vertices whose total vertex-group weight is zero — they will not follow the armature at all. |
| Clipping (approximate) | Outfit vertices estimated to be inside the body, via nearest body surface point + face normal, in world space, with max/mean penetration depth. |

All three thresholds are adjustable: **side margin** (how far
from the centre a vertex must be to count as "clearly on a
side"), **min weight** (opposite-side weight above this counts
as contamination), and **clip depth** (a vertex must be inside
by more than this to count as clipping — raise it to ignore
surface contact).

Reports go to the console and to a `FitCheck_Report` text block
in Blender.

## Requirements

- Blender **4.2 LTS** (developed and tested on 4.2.3).
- No pip installs, no external libraries.

## Usage

Install `fit-doctor-1.0.0.zip` (or a ZIP built with
`python3 build_zip.py`) via Preferences > Add-ons > Install,
enable **Fit Doctor**, and use the **Fit Doctor** tab in the
3D Viewport sidebar: pick the body mesh and the outfit mesh,
adjust thresholds if needed, run the check.

Everything is also drivable headless through the plain Python
API — that is how the test suite exercises it:

```python
import fit_doctor.core as fd

report = fd.analyze(body_obj, outfit_obj)          # all findings, as a dict
print(fd.format_report(body_obj, outfit_obj, report))
text = fd.write_report_text_block(body_obj, outfit_obj, report)

# Thresholds are keyword arguments:
report = fd.analyze(body_obj, outfit_obj,
                    side_margin=0.02, min_weight=0.1, clip_depth=0.005)
```

## Tests

All tests run inside Blender (background mode is fine):

```bash
# Synthetic body + outfit spheres with planted defects — missing
# keys, 5+3 contamination, 4 unweighted, 6 sunk vertices — plus
# threshold and clean-control assertions:
blender -b --factory-startup --python tests/run_tests.py

# The shipped ZIP, installed and driven like a user would:
blender -b --factory-startup --python tests/test_install.py -- fit-doctor-1.0.0.zip

# Real-case run against a female avatar with Christmas dress
# (pass a COPY of the .blend — the script refuses the original):
blender -b --factory-startup --python tests/verify_real_case.py -- <copy.blend> <report.txt>
```

## Known blind spots (v1, stated on purpose)

- **Clipping is an approximation.** The nearest-surface + normal
  test produces false positives where surfaces touch or cross at
  grazing angles, and it assumes the body's normals point
  outward. A tight, correct graft will still flag shallow counts
  where cloth hugs skin. Believe the deep vertices; treat the
  shallow count as triage, and confirm visually.
- **The side test assumes +X is left** in the outfit's local
  space. If your model's local axes disagree, the two
  contamination counts swap meaning. Models with origins or
  rotations far off rest pose will skew it.
- **Follow-through is name-exact and pairing-dependent.** It
  compares the two objects you give it. If your body is split
  across meshes (head / torso / legs), the counts only cover the
  parts you pair — an outfit checked against a torso mesh says
  nothing about the face keys on the head mesh.
- **A floating garment is invisible to these checks.** A glove
  hovering a centimetre off the hand has no inside-body vertices
  and full weights; it passes. Fit Doctor finds penetration and
  missing data, not gaps.

## Tested on

**Synthetic pair** (body sphere r=1.0, outfit sphere r=1.05)
with planted defects: the checker reproduced every plant with
exact counts — 2 missing keys, contamination 5 left / 3 right
with the correct per-group split, 4 unweighted, 6 clipping at
the planted depth — and reported all zeros on the clean control
outfit. Raising each threshold past its plant changed the
verdict as documented.

**Female avatar with Christmas dress** (real case): the AI-generated gown
(`GenGown`, 17,716 vertices) checked against the joined body
meshes it was grafted onto (2,323 vertices). Findings: **3,568
outfit vertices inside the body** (max depth 0.166 m, mean
0.021 m; 129 vertices deeper than 5 cm, the deepest cluster at
arm height on the +X side — the graft's known problem area),
contamination 0, unweighted 0, follow-through 0 missing on this
pairing (the body's face keys live on a separate head mesh the
gown doesn't cover, so they are not in this count). The full
report is in [`examples/`](examples/real-case-report.txt).
Much of the shallow clipping count is the close-fit/contact
class described above — the graft was known to clip, and the
deep vertices confirm real penetration — but read the caveat
before quoting the headline number.

Other rigs and outfits are **untested**. Issues and reports
from other models are welcome.

## License

MIT — see [LICENSE](LICENSE).
