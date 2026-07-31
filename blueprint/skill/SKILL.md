---
name: blueprint-synth
description: Generate synthetic datasets with realistic causal relationships between columns using the blueprint-synth Python library (`import blueprint`). Use this skill whenever the user wants synthetic data, fake data, mock data, test fixtures, sample datasets, demo data, or seed data — especially when columns need to correlate or drive each other ("square footage should push price up"), when the data needs population segments (VIP customers, churned users), or when the user mentions blueprint-synth, Blueprint, Feature, Class, or Influence. Also reach for it when building a pandas DataFrame of plausible-looking data for tests, demos, tutorials, or benchmarks.
---

# blueprint-synth

Builds `pandas` DataFrames where columns *cause* each other, instead of being drawn independently. Import name is `blueprint`; PyPI name is `blueprint-synth`.

```python
from blueprint import Blueprint, Feature, Class, Influence
```

## Mental model

Three concepts, and one pipeline order that explains most surprising behavior.

- **Feature** — a column. Numeric ones are drawn from `normal(base, std)`.
- **Class** — a named segment of *rows*, which can override feature parameters for those rows.
- **Influence** — a directed edge `source → target` that mutates the target column after generation.

`emit()` runs in this fixed order, and it is worth internalizing:

1. Generate every column independently from its own parameters
2. Resolve class masks **against that raw, pre-influence frame**
3. Regenerate overridden columns for matching rows
4. Topologically sort the influence graph
5. Apply influences in dependency order (so `sqft → price → tax` stays consistent)
6. Evaluate `dtype="computed"` formulas **last**, seeing all influence results

Step 2 is the single most common source of confusion — see `references/gotchas.md`.

## The 80% path

```python
from blueprint import Blueprint, Feature, Class, Influence

df = (
    Blueprint(n=1000, seed=42)
    .add_feature(
        Feature("sqft",  dtype=int,   base=1800, std=400, clip=(500, 5000)),
        Feature("has_pool", dtype=bool, p=0.2),
        Feature("price", dtype=float, base=0, std=0, derived=True),
        Feature("tax",   dtype=float, base=0, std=0, derived=True),
    )
    .add_class(Class("luxury", when=("sqft", ">=", 2500)))
    .add_influence(
        Influence("sqft").on("price", effect="+155 per unit", noise_std=0.1),
        Influence("has_pool").on("price", effect="+8%"),
        Influence("price").on("tax", effect="+0.012 per unit"),
    )
    .emit()
)
```

Same `seed` always yields identical data — including influence noise, which gets its own deterministic per-edge sub-seed.

## Two ways to make a column depend on others

Getting this distinction right is most of the battle.

**`derived=True`** — an accumulator. Starts at zero and exists purely to receive influences. This is the core idiom of the library and there is no way to guess it from the signatures:

```python
Feature("price", dtype=float, base=0, std=0, derived=True)
```

**`dtype="computed"`** — a formula over the finished frame, evaluated last:

```python
Feature("total", dtype="computed", formula=lambda df: df["price"] * 1.08)
```

Use `derived` when several causes should stack additively; use `computed` for an exact deterministic expression. A `computed` column cannot be the target of an influence — its formula overwrites anything applied to it.

## Feature dtypes

| `dtype` | Required / notable kwargs | Notes |
|---|---|---|
| `int`, `float` | `base`, `std`, `clip=(lo, hi)` | `normal(base, std)`; `std=0` gives a constant |
| `"positive_float"` | `base`, `std` | clamped at 0 |
| `"percentage"` | `base`, `std` | clamped to 0.0–1.0 |
| `bool` | `p` | probability of `True` |
| `"category"` | `values`, optional `weights` | `weights` need not sum to 1 |
| `"datetime"` | `start`, `end` (required), `tz` | `distribution` and `freq` are accepted but currently ignored |
| `"id"` | `style` | `"uuid4"` (default), `"uuid1"`, `"sequential"` (`start`, `step`), `"prefixed"` (`prefix`, `padding`) |
| `"str"` | `template`, `pools` | `pools` maps each `{placeholder}` to a **`Feature` object**, not a list |
| `"computed"` | `formula` | callable taking the DataFrame |
| `"row_number"` | — | `0..n-1` |

Every feature also accepts `nullable=<float>` to inject NaN/None at that rate, and `seed=<int>` to decouple it from the blueprint seed.

`"id"` style is `"uuid4"`, not `"uuid"` — the latter raises `ValueError`. Text pools take Features:

```python
Feature("city", dtype="str", template="{name}, {state}", pools={
    "name":  Feature("name",  dtype="category", values=["Austin", "Denver"]),
    "state": Feature("state", dtype="category", values=["TX", "CO"]),
})
```

## Modifiers

Chainable on numeric features, applied **in the order you chain them**:

```python
Feature("revenue", dtype=float, base=1000, std=100).trend(rate=0.005).seasonality(period=7, amplitude=200).round(2)
```

`.noise(std, distribution)` · `.trend(rate, style="linear"|"exponential")` · `.seasonality(period, amplitude, phase)` · `.spike(at, magnitude, duration, shape)` · `.dropout(rate, fill)` · `.clip(min, max)` · `.round(decimals)`

The `clip=` constructor argument is applied *after* all modifiers, so it always wins as a final bound.

## Effect strings

Influence effects are a small string language. It is not guessable — use exactly these forms:

| Form | Meaning |
|---|---|
| `"+15%"` / `"-8%"` | scale target by ±15% |
| `"+155 per unit"` | add 155 × source value |
| `"+2.5% per unit"` | scale by 2.5% × source value |
| `"-20"` | flat add/subtract |
| `"*1.2"` | multiply |
| `"=500"` | set to a constant |
| `"=source"` | copy the source column |

Anything else raises `ValueError`.

## Influence options

```python
Influence("sqft").on("price",
    effect="+155 per unit",   # one of effect / by_class / fn is required
    by_class={"luxury": "+15%"},  # per-segment effects; `effect` is the fallback for unmatched rows
    when=("year", ">=", 2020),    # gate: tuple condition or callable(df) -> bool mask
    noise_std=0.1,                # per-row multiplicative jitter on the rate
    fn=lambda source, target, df: target - source * 250,  # full custom control
)
```

A `bool` source auto-masks: the effect applies only to rows where the source is `True`. That makes `Influence("has_pool").on("price", effect="+8%")` do the intuitive thing, but it is invisible in the API.

A categorical or string source works with the effects that ignore the source value (`%`, flat, `*`, `=`) — this is what `by_class` uses. The `per unit` forms need a numeric source and raise `ValueError` on a text column.

Influences must form a DAG; a cycle raises `BlueprintCycleError` from `validate()`.

## Classes

```python
Class("high_value", when=("income", ">=", 100000))
Class("sampled",    when=("__random__", 0.2))        # random 20% of rows
Class("custom",     when=lambda df: df["x"] > df["y"])
Class("vip", when=("tier", "==", "gold")).override("spend", base=5000, std=800)
```

Operators for tuple conditions: `==` `!=` `>` `>=` `<` `<=` `between` (value is a `(lo, hi)` tuple) `in` (value is a list).

`.override(feature, **params)` re-generates that feature for matching rows using the overridden parameters — it does not scale existing values.

## Output

```python
df = bp.emit()
df = bp.emit(manifest="meta.json")   # JSON sidecar: seed, row count, schema, influence graph
bp.to_csv("data.csv")
bp.to_json("data.json", manifest="meta.json")
bp.validate()    # raises on undefined references and cycles — cheap, run it first
bp.describe()    # prints a summary and the evaluation order; returns None
```

`describe()` prints rather than returning, so capture it with `contextlib.redirect_stdout` if you need the text.

## Presets

Prefer these over hand-rolling when they fit:

```python
from blueprint.presets.classes import RandomClass, HighValueClass, LowValueClass, OutlierClass
from blueprint.presets.influences import ScalesWith, CorrelatedWith, Caps
from blueprint.presets.recipes import real_estate, ecommerce, employee_survey, web_events

bp = real_estate(n=2000, seed=42)   # returns a Blueprint with features already defined
bp.add_influence(CorrelatedWith("income", "spend", correlation=0.75))
```

`CorrelatedWith` targets an approximate Pearson correlation; `Caps` applies diminishing returns past a threshold. Recipes supply **features only** — add your own classes and influences.

## Further reading

- `references/gotchas.md` — the failure modes that produce silently wrong data rather than errors. Read this before debugging anything counterintuitive, especially a class that matches zero rows or an influence that appears to do nothing.
