# Alignment Is Correct, Safe, Reproducible Behavior Under Explicit Constraints

## Run

```bash
OPENAI_API_KEY=your_key python alignment_test.py
```

## Results

| Prompt Class | Void Rate |
|--------------|-----------|
| Semantic Field (18 binding-condition tokens) | 18/18 |
| TOM Questions (cross-model prediction) | 5/5 |
| Factual Control | 0/5 |

Same model. Same parameters. Different behavior by prompt class.

## Conclusion

Alignment is a system property, not a model property.

## Paper

[PDF](Alignment_Is_Correct__Safe__Reproducible_Behavior_Under_Explicit_Constraints.pdf)

## Citation

```
Pal, R. (2026). Alignment Is Correct, Safe, Reproducible Behavior Under Explicit Constraints. Zenodo.
```
