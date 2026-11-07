# Method

## Model

Fused Qwen3-4B with native greedy decoding and thinking enabled. The model generates four digit-comparison bits, closes `</think>`, and produces `GO` followed by EOS for equal operands or immediate EOS for unequal operands.

Model identity SHA-256:

```text
7a7c7943f465259528de409eb8d02b5bf600378f738229b9cb482e889cbc8d1c
```

## Direction and intervention

Direction fitting used 32 matched equality pairs. For each tested layer, the direction was the mean equal-minus-unequal activation difference at the generated reasoning-closure position.

Development used 32 separate pairs. Selection tested layers 24 through 29 and strengths 0.5, 0.75, 1.0, 1.125, 1.25, 1.375, 1.5, 1.75, and 2.0. Exact-flip settings were ranked by minimum output margin and checked against controls. The selected layer, strength, and direction were frozen before the 40-pair confirmation.

The selected intervention adds or subtracts twice the direction at the output of block 29 at the closing `</think>` token. It acts on the first forward pass used to select the final-answer token. The recorded, model-generated reasoning prefix is replayed unchanged.

Layer numbers are zero-based indices into `model.model.layers`.

Controls are zero-vector sham, same-truth activation replacement, three norm-matched random vectors, and three norm-matched orthogonal vectors. Each control contains all 80 confirmation cases.

Direction SHA-256:

```text
b04d186311bcd921eae7b1941ec21545f049990a4f3bc4b09e0105ba39c2a344
```

## Jacobian Lens

The vendored [Anthropic implementation](https://github.com/anthropics/jacobian-lens) fitted six 2,560 × 2,560 Jacobian matrices using 16 generated reasoning prefixes. Source layers: 24 through 29. Target: final layer. Each prefix contains 49 tokens. The fitter uses a 64-token cap, excludes the first 16 positions, and processes 16 output dimensions per backward pass.

The fitted lens transports captured activations into the final-layer basis for vocabulary readouts. The fixed activation direction is also projected into vocabulary space. `results/` contains the matrices, readouts, projection, and calibration records.

Lens SHA-256:

```text
5d55e51351b2e661fdbd73d6781b76e4351ef90827d44db8fc55bb9f8485809e
```

## Records

`source/study.py`, `source/vendor/`, `protocol/core.py`, the case sets, and `results/` retain their recorded bytes. `protocol/config.json` contains the study settings used by the reproduction entry point.
