# Vendored classifiers

`vendor/gpt35-gpt4-void-ab/run.py` is a byte-identical copy of `run.py` from
https://github.com/theonlypal/gpt35-gpt4-void-ab at commit
`b468b3e29d9f4152a99fc9e2597e376f84b74ea4`
(SHA-256 `a40a45c43416c459083c9ad680be355d646a05dfca96cfc78e048ca38547f860`).
Only `classify_response()` is used.

`vendor/opus45-opus46-matched-prereg-final/classifier.py` and `frozen.py` are
byte-identical copies from https://github.com/theonlypal/opus45-opus46-matched-prereg-final
at tag `v1.0.0` (SHA-256 `64d56b291bcdcd8ec4376d91933b1dd25299c62f335a406d9a989b687510dad8`
and `33c47248e123a2b2bf59f96bb858dc0874d65d2aba1f75aaa836a41e097630a6`).
Only `classify(experiment=2, ...)` is used. Their MIT License is included as
`vendor/opus45-opus46-matched-prereg-final/LICENSE`.
