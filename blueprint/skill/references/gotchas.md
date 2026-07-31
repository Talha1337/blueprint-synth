# Gotchas

Failure modes that produce **silently wrong data** rather than an exception. Every claim here was verified by running the library against the version in this repo (pandas 3.0.2, numpy 2.4.4).

## Contents

1. [Classes cannot see influence results](#1-classes-cannot-see-influence-results)
2. [Boolean sources silently auto-mask](#2-boolean-sources-silently-auto-mask)
3. [by_class leaves unmatched rows untouched](#3-by_class-leaves-unmatched-rows-untouched)
4. [Overrides regenerate, they don't adjust](#4-overrides-regenerate-they-dont-adjust)
5. [Smaller traps](#5-smaller-traps)

---

## 1. Classes cannot see influence results

**The trap.** Class masks are resolved against the raw generated frame, *before* any influence runs. A class whose condition tests a `derived=True` column sees zeros, matches nothing, and reports no error.

```python
bp = (Blueprint(n=200, seed=1)
    .add_feature(
        Feature("sqft",  dtype=int, base=1800, std=400),
        Feature("price", dtype=float, base=0, std=0, derived=True),
        Feature("flag",  dtype=float, base=1.0, std=0.0))
    .add_class(Class("expensive", when=("price", ">", 100000)).override("flag", base=99.0))
    .add_influence(Influence("sqft").on("price", effect="+155 per unit")))

df = bp.emit()
df.price.min()            # 110825.0  — every row exceeds the threshold
(df.flag == 99).sum()     # 0         — the class matched nothing
```

At mask time `price` is still all zeros, so `price > 100000` is uniformly `False`. The same applies to any column that only acquires its value from an influence.

**The fix.** Condition classes on *upstream* columns that are generated directly:

```python
.add_class(Class("expensive", when=("sqft", ">", 645)))   # sqft is real at mask time
```

If you genuinely need to segment on a post-influence value, emit once, then build a second blueprint — or use a `dtype="computed"` column, which is evaluated after influences.

**Rule of thumb.** A class condition is only trustworthy on a column with a real `base`/`std`, a category, a bool, or a datetime. Conditioning on `derived=True` is always a bug.

---

## 2. Boolean sources silently auto-mask

**The behavior.** When the source column is `bool`, the effect is applied only to rows where it is `True` — the source is ANDed into the row mask.

```python
Influence("has_pool").on("price", effect="+10%")
# 307 rows changed, exactly matching has_pool.sum() == 307
```

This is almost always what you want, which is why it rarely gets noticed. It matters in two cases:

- **Do not add a redundant gate.** `when=("has_pool", "==", True)` is already implied.
- **`"=source"` and `"=<constant>"` are also masked.** `Influence("is_refund").on("amount", effect="=0")` zeroes only the refund rows, not every row — usually correct, but worth being deliberate about.

There is no way to apply an effect to the `False` rows from a bool source. Invert the feature or use `fn=` instead.

---

## 3. by_class leaves unmatched rows untouched

`by_class` maps class names to effects. Rows in no listed class get the top-level `effect` — and if you omit it, they get nothing at all.

```python
Influence("score").on("price", by_class={"high": "+15%"})              # non-high rows unchanged
Influence("score").on("price", by_class={"high": "+15%"}, effect="+0%")  # explicit no-op fallback
```

The `"+0%"` idiom in the README exists solely to make the fallback explicit. Prefer writing it — it documents intent and costs nothing.

Class names in `by_class` that do not correspond to a registered `Class` are **silently ignored**. A typo produces no error and no effect, so check spelling against your `add_class` calls.

---

## 4. Overrides regenerate, they don't adjust

`.override("spend", base=5000)` **re-draws** the column for matching rows from the overridden parameters. It does not scale or shift the values already generated.

```python
Class("vip", when=("tier", "==", "gold")).override("spend", base=5000, std=800)
# matching rows are freshly drawn from normal(5000, 800)
```

Consequences worth knowing:

- Unspecified parameters are inherited from the original feature, not reset to defaults.
- Modifiers (`.trend()`, `.noise()`, …) are carried over and re-applied to the new draw.
- Overrides on a `dtype="computed"` feature are skipped entirely — the formula wins.
- Each override gets its own deterministic sub-seed, so results stay reproducible but will *not* match the pre-override values for those rows.

To scale existing values instead of redrawing, use an influence with a `when=` gate.

---

## 5. Smaller traps

**`describe()` returns `None`.** It prints. Capture with `contextlib.redirect_stdout(io.StringIO())` if you need the text programmatically.

**`"id"` style is `"uuid4"`, not `"uuid"`.** The shorter spelling raises `ValueError: Unknown id style: 'uuid'`. Valid: `"uuid4"`, `"uuid1"`, `"sequential"`, `"prefixed"`.

**Text-source influences need a recent version.** On blueprint-synth 0.1.0 as published to PyPI, any influence whose source is a category or string column raises `could not convert string to float` on pandas 3.x — including the `by_class` pattern. Fixed in this repo; if you hit it, the installed version predates the fix.

**Text `pools` take `Feature` objects, not lists.** `pools={"name": ["Ana", "Bob"]}` raises `AttributeError: 'list' object has no attribute 'generate'`. Pass `Feature("name", dtype="category", values=["Ana", "Bob"])`.

**`datetime` ignores `distribution` and `freq`.** Both are accepted as kwargs and silently discarded; output is always uniform across `[start, end]`. Do not rely on them for business-day or clustered timestamps.

**Constructor `clip` beats modifier `.clip()`.** The constructor bound is applied after all modifiers, so `Feature(..., clip=(0, 100)).trend(rate=0.5)` will flatten against the ceiling at 100.

**`percentage` is hard-clamped to 0–1** and `positive_float` to ≥ 0, both *before* influences run. An influence can still push either outside that range — re-clip with a `computed` column if the bound must hold in the output.

**`int` features round after modifiers.** Adding a `+0.5 per unit` influence to an int column produces floats in the final frame, because influences run after the dtype cast.

**`emit()` does not call `validate()`.** Cycles still surface either way — the topological sort raises `BlueprintCycleError` during `emit()`. Undefined references do not: an influence or class pointing at a non-existent column fails as a bare `KeyError: 'nope'` mid-generation. `validate()` turns that into a named error (`Influence: target 'nope' is not a defined feature`), so call it first when assembling a blueprint programmatically.
