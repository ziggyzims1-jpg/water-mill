# The mark

A waterwheel: a rim, six spokes, six paddle blades outboard of the rim. The
blades are what make it a *water*wheel rather than a cog, so they are the part
to protect if the mark is ever simplified further.

| File | Use |
|---|---|
| `logo-mark.svg` | The primary mark. Square, legible down to about 24px |
| `logo-water.svg` | Display only — the wheel turning in the race. The waterline costs it small-size legibility, so it is for a header, not an avatar |
| `logo-lockup.svg` | Mark plus wordmark, horizontal |
| `logo-gate.svg` | Secondary mark — the sluice gate |

**Every stroke is `currentColor`.** The mark takes the colour of whatever it
sits in, so there is no light variant and no dark variant to keep in step, and
nothing to update when a theme changes. Colour it by setting `color` on a
parent, or `fill`/`color` in an `<img>` context by editing the file.

`logo-water.svg` hides the submerged half with a **luminance mask** rather than
by painting a background rectangle over it. A rectangle would have to know the
background colour, which is exactly the thing `currentColor` exists to avoid —
it would show as a pale block the moment the mark was placed on anything but the
colour it was drawn against.

The lockup's wordmark is live text in a system font stack, not outlines, so it
stays editable and searchable. It will render in whatever the viewing system
has. Convert it to paths before using it anywhere the exact letterforms matter.

## Why a sluice gate is the secondary mark

A mill race has a gate that decides how much water reaches the wheel. This
orchestrator has a gate that decides how much of a night's work reaches the
repository — and in both cases less comes out than went in, on purpose. That is
why the gate mark has three lines entering and two leaving; it is the one part
of it that carries meaning, so do not "fix" the asymmetry.
