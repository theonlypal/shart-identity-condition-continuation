# Linguistic and Unicode Validation

Accessed 2026-08-04.

## Exact strings

`שָׁרְט` is, in logical code-point order, U+05E9 HEBREW LETTER SHIN, U+05B8 HEBREW POINT QAMATS, U+05C1 HEBREW POINT SHIN DOT, U+05E8 HEBREW LETTER RESH, U+05B0 HEBREW POINT SHEVA, and U+05D8 HEBREW LETTER TET. A transparent graphemic transliteration is *šā-rə-ṭ*; this notation reports the encoded consonants and points and is not a claim that the whole sequence is a standard dictionary form. `שָרְט` has the same sequence without U+05C1. Without U+05C1 or U+05C2, U+05E9 alone does not encode the shin-versus-sin dot distinction.

The exact SHIN-dotted sequence `שָׁרְט` was not found as an authoritative standard Hebrew lexical entry in the sources searched. The Academy of the Hebrew Language attests `שֵׂרֵט` and notes the older form `שָׂרֵט`, both with U+05C2 HEBREW POINT SIN DOT, glossed “to mark out; to trace.” This is a nearby root/lexical association, not an attestation or direct translation of the exact U+05C1 SHIN-dotted artifact. The paper must therefore call `שָׁרְט` a nonstandard pointed Hebrew identity string unless a stronger authoritative attestation is supplied.

The Arabic input `شَرْط` encodes sheen + fatha + reh + sukun + tah. A defensible transliteration is *šarṭ* (often rendered *sharṭ*). The Cairo Arabic Language Academy identifies the root شرط and defines the nominal condition sense as a requirement imposed in a sale or similar transaction; it also records grammatical and jurisprudential condition senses. Lane’s Lexicon likewise gives “condition,” “term,” and “stipulation.”

## Mixed artifacts

`شָׁרְט` begins with Arabic U+0634 and continues with Hebrew points and letters: U+05B8 U+05C1 U+05E8 U+05B0 U+05D8. `شָרְט` is identical except that U+05C1 is absent. Unicode states that U+05C1 normally follows Hebrew U+05E9 and that shin and sin dots are not used with other base characters. In T1, therefore, U+05C1 follows an Arabic base character. The sequence is a cross-script combining-mark artifact, not a standard orthographic unit with an established conventional linguistic reading.

Bidirectional rendering can visually reorder these strings. All scientific comparisons use logical code-point order and original UTF-8 bytes; rendered specimens are explanatory only.

## Authoritative sources

- Unicode Consortium, “Chapter 9: Middle East-I,” Unicode Standard 17.0.0, Hebrew section: https://unicode.org/versions/Unicode17.0.0/core-spec/chapter-9/
- Unicode Consortium, Hebrew Names List (U+0590–U+05FF): https://www.unicode.org/charts/nameslist/n_0590.html
- Academy of the Hebrew Language, `שֵׂרֵט`, including the original-form note `שָׂרֵט`: https://terms.hebrew-academy.org.il/munnah/111909_1/
- Cairo Arabic Language Academy, `الشَّرْطُ`, root شرط: https://www.arabicacademy.gov.eg/ar/محرك-البحث/الشَّرْطُ?exact_search=true
- Edward William Lane, *An Arabic-English Lexicon*, root شرط, searchable transcription: https://arabiclexicon.hawramani.com/شَرط/
