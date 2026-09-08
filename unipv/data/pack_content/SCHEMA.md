# pack_content/<code>.json

Authored content for PASS-ESSENTIALS. Everything else in the pack is
mechanical; this is the one document that needs judgement, so it is written
separately and only rendered by build_pack.py.

```json
{
  "exam_brief": {
    "Format": "written, 2 hours, closed book",
    "Questions": "4 exercises, proportional score",
    "Pass mark": "18/30; no separate section minimum",
    "Allowed": "no calculator, no notes",
    "Date": "23/09/2026",
    "Source": "raw/<course>/.../_course_text.html"
  },
  "topics": [
    {
      "name": "Skolemization",
      "frequency": "appeared in 7 of 9 archived papers",
      "blocks": [
        {"kind": "text",  "text": "Plain prose. Escaped automatically."},
        {"kind": "math",  "text": "forall x exists y P(x,y) equiv forall x P(x, f(x))"},
        {"kind": "heading", "text": "Method"},
        {"kind": "steps", "items": ["Push negations inward", "Rename bound variables"]},
        {"kind": "figure", "png": "31-1-22A-p001-81e00199.png",
         "caption": "Resolution tree [31-1-22A.pdf, p1]", "width": "80%"}
      ]
    }
  ],
  "formula_sheet": ["e^(i pi) + 1 = 0"],
  "traps": ["Forgetting to rename bound variables before Skolemizing."],
  "six_hours": ["Skolemization", "Resolution", "Herbrand universes"]
}
```

Rules:
- `math` and `formula_sheet` are **Typst math syntax**, not LaTeX. `forall`,
  `exists`, `->`, `and`, `or`, `!=`, `<=`, `sum_(i=1)^n`, `frac(a, b)`,
  `x_1`, `x^2`, `alpha`. No `\\frac`, no `$...$` delimiters.
- `png` must name a file that exists in that course's `_figures/` directory,
  taken from its `index.json`. Place real figures; never describe one in prose
  as a substitute.
- Every factual claim about format, grading or content must be traceable to a
  file. Anything inferred is tagged `[NOT IN SOURCE — VERIFY]` in the text.
- Order topics by how often they appear in the archived papers, and say the
  count in `frequency`.
