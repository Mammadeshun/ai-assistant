#!/usr/bin/env python3
"""Two exam kits: everything needed to reach 18/30, and nothing else.

    python build_examkit.py

One self-contained A4 document per course, designed to be printed and worked
through, not read. Content comes from the course's own archive - past papers,
the lecturer's published solutions, the lecture notes - and every claim names
the file it came from. Nothing is invented; where the archive is silent the
document says so.

  EXAM-KIT_509486_Machine-Learning-Part-2.pdf
  EXAM-KIT_509487_Fuzzy-Systems.pdf
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from build_pack import esc, ruled  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA, OUT = ROOT / "data", ROOT / "output"


def preamble(title: str, subtitle: str) -> str:
    """A4, 2cm margins, black on white. The visual system is four labelled
    block styles and grey shading only - this gets printed, and a colour fill
    is a cartridge of ink."""
    return f"""#set page(paper: "a4", margin: (x: 1.9cm, y: 1.8cm), numbering: "1 / 1",
  header: context {{ if counter(page).get().first() > 1 {{
    set text(7.5pt, fill: luma(35%))
    emph[{esc(subtitle)}]; h(1fr); emph[{esc(title)}]
    v(-0.5em); line(length: 100%, stroke: 0.3pt + luma(70%)) }} }})
#set text(font: ("DejaVu Serif", "Liberation Serif"), size: 10.5pt,
          fill: black, lang: "en", hyphenate: true)
#set par(justify: false, leading: 0.62em)
#show heading.where(level: 1): it => {{
  block(above: 1.2em, below: 0.55em, width: 100%)[
    #text(15pt, weight: "bold")[#it.body]
    #v(-0.45em) #line(length: 100%, stroke: 1.1pt)
  ]}}
#show heading.where(level: 2): it => {{ set text(12pt, weight: "bold")
  block(above: 0.85em, below: 0.35em, it) }}
#show heading.where(level: 3): it => {{ set text(10.5pt, weight: "bold")
  block(above: 0.6em, below: 0.25em, it) }}
#show table: set block(breakable: true)
#set table(stroke: 0.4pt + luma(45%), inset: 5pt)
#show table.cell.where(y: 0): set text(weight: "bold")

// --- the four block styles -------------------------------------------------
#let tag(label, body, fill: white, accent: black) = block(
  width: 100%, above: 0.7em, below: 0.7em,
  stroke: (left: 2.5pt + accent, rest: 0.4pt + luma(60%)),
  fill: fill, inset: (left: 8pt, rest: 7pt))[
  #text(7.5pt, weight: "bold", tracking: 0.6pt)[#upper(label)]
  #v(-0.35em) #body]

#let recipe(body) = tag("recipe", body, fill: luma(97%))
#let worked(body) = tag("worked example — official solution", body, fill: luma(93%))
#let trap(body)   = tag("where marks are lost", body)
#let onthday(body) = tag("on the day", body, fill: luma(96%))
#let brief(body)  = block(width: 100%, inset: 8pt, stroke: 0.9pt, body)

#align(center)[
  #text(19pt, weight: "bold")[{esc(title)}]
  #v(0.2em) #text(9.5pt, fill: luma(30%))[{esc(subtitle)}]
]
#v(0.4em) #line(length: 100%, stroke: 1.4pt) #v(0.7em)
"""


def unique_questions(code: str) -> list[dict]:
    rows = []
    for line in (DATA / "questions.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["course"] == code:
            rows.append(row)
    seen, out = set(), []
    for row in rows:
        key = re.sub(r"\s+", " ", row["text"]).strip().lower()[:110]
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def practice_block(rows: list[dict], heading: str, note: str,
                   space: float = 7.0, limit: int = 40) -> str:
    doc = f"\n= {esc(heading)}\n\n{esc(note)}\n\n"
    for index, row in enumerate(rows[:limit], start=1):
        src = Path(row["source_file"]).name
        when = row.get("exam_date") or "undated"
        marks = f"{row['points']} marks" if row.get("points") else ""
        doc += (f"\n#block(above: 1.1em, below: 0.3em)[#grid(columns: (1fr, auto),"
                f"[#text(11pt, weight: \"bold\")[Q{index}]"
                f"#h(0.6em)#text(7.5pt, fill: luma(35%))"
                f"[\\[PAST PAPER — {esc(src)}, {esc(when)}\\]]],"
                f"[#text(8.5pt, weight: \"bold\")[{esc(marks)}]])]\n\n"
                f"{esc(' '.join(row['text'].split())[:1500])}\n\n")
        doc += ruled(space)
    return doc


def compile_to(source: str, name: str) -> None:
    import typst

    OUT.mkdir(parents=True, exist_ok=True)
    src = OUT / f"{name}.typ"
    src.write_text(source)
    typst.compile(str(src), output=str(OUT / f"{name}.pdf"), root=str(ROOT))
    print(f"  ok  {name}.pdf")


ML_TITLE = "MACHINE LEARNING, ANN & DEEP LEARNING — PART 2"
ML_SUB = "509486 · exam kit · the minimum to reach 18/30"


def machine_learning() -> str:
    doc = preamble(ML_TITLE, ML_SUB)

    doc += """
= How this exam works — read this first

#brief[
*This is the same exam every single time.* Twelve archived sittings from June
2023 to June 2026 were compared. Every one of them is: a page describing a
dataset, then the *same numbered questions*, asking you to design a deep
network for that dataset. Only the dataset changes.

You are not being asked to remember a syllabus. You are being asked to make
seven design decisions and justify them. Learn the seven answers and the
mapping from dataset type to decision, and you can answer any sitting.
]

== The questions, verbatim, that appear every time

#table(columns: (auto, 1fr),
  [*1. MODEL*], [Which architecture do you consider the most appropriate for this task, and WHY],
  [*2. INPUT*], [(a) how to (if) preprocess input data; (b) which is, after preprocessing, the input of the model, and how is it represented (shape, value domain)],
  [*3. OUTPUT*], [How would you design the output layer and why; what is its shape],
  [*4. LOSS*], [Which loss function would you use to train your model and why],
  [*5. CONFIGURATION*], [(a) composition of layers; (b) which activation functions; (c) how would you regularise/initialise; (d) which hyperparameters would you tune],
  [*6. EVALUATION*], [How would you assess (in which setting) the generalisation capabilities of the model on unseen data],
  [*7. INTERPRETATION*], [How would you explain the prediction on a given input — which part of the input most affects the output. #emph[Appears from Jan 2025 onward; not in the 2023 papers.]],
)

#v(0.4em)
#trap[
*Instructions repeated verbatim on every paper.* Keep the same numbering and
sub-items. Motivate your choices. Leave SPACE between answers. And, from the
January 2025 paper: *"Writing more is not a proxy for a higher evaluation."*
Answer in the order asked, keep it short, justify every choice in one sentence.
]

== The second half: the notebook

Every paper ends with the same clause: you have roughly 8–9 days after the
sitting to upload a Colab/Jupyter notebook implementing *the solution you just
wrote*. The notebook must *totally adhere to the written answers*.

#brief[
*If no file is uploaded, the exam is considered rejected.* Requirements taken
from the September 2026 assignment page: one PDF named `Surname_Number.pdf`
containing a link to a Colab notebook shared as *anyone with the link can
Edit*; self-contained (do not mount your Drive); must run start-to-finish in
*under 5 minutes*; text cells identifying each numbered point. If you must
deviate from your written answer, mark it in a text cell with *CHANGE* in bold
uppercase and justify it — unmotivated changes are penalised.

*The final model performance is explicitly NOT graded.* You are marked on the
pipeline matching your design, not on accuracy. Subsample the data if RAM is
tight; the paper says so itself.
]

= The only table you really need

Every sitting is one of five dataset shapes. Identify which, and questions
1, 3 and 4 answer themselves.

#table(columns: (auto, auto, auto, auto),
  [*Dataset shape*], [*Architecture (Q1)*], [*Output layer (Q3)*], [*Loss (Q4)*],
  [Raw text, one label of K],
  [Embedding → LSTM/GRU or Transformer encoder → dense],
  [`K` units, softmax],
  [Categorical cross-entropy],
  [Raw text, several labels at once],
  [Embedding → LSTM/BiLSTM → dense],
  [`K` units, *sigmoid*],
  [*Binary* cross-entropy, summed over the K outputs],
  [Bag-of-Words vector (dimension d)],
  [Fully-connected MLP; no recurrence needed],
  [as above by task],
  [as above by task],
  [Text + BoW + metadata together],
  [*Multi-input*: one branch per input type, concatenate, then dense],
  [as above by task],
  [as above by task],
  [RGB images, one class of K],
  [CNN (Conv+Pool blocks) or a pretrained backbone fine-tuned],
  [`K` units, softmax],
  [Categorical cross-entropy],
  [Images, classes unknown],
  [Autoencoder for representation, then cluster the latent space],
  [reconstruction, same shape as input],
  [MSE (reconstruction)],
  [Tabular, 2 classes],
  [Small MLP],
  [1 unit, sigmoid],
  [Binary cross-entropy],
  [Ordinal rating 1–5],
  [Text branch → dense],
  [either 5 units softmax (as classification) or 1 unit linear (as regression) — *state which framing you chose and why*],
  [cross-entropy, or MSE if regression],
  [Graph / interaction network],
  [Graph neural network (GCN); node features + adjacency],
  [by task],
  [by task],
)

== What the twelve archived sittings actually asked

#table(columns: (auto, 1fr),
  [June 2023], [42,656 amusement-park reviews → predict the 1–5 rating],
  [July 2023], [RGB images of three animals → classify],
  [Sept 2023 (a)], [1,435 students' free-text answers to one examiner question],
  [Sept 2023 (b)], [510 images categorised by two properties C1 and C2 (multi-label)],
  [Jan 2024], [700 user reviews of shows],
  [Feb 2024], [19,717 scientific articles across three sub-topics],
  [June 2024], [186 images in three classes],
  [July 2024], [1,305 images, classes *unknown* — unsupervised],
  [Sept 2024 (a)], [303 samples, two classes, numeric 0/1 — tabular],
  [Jan 2025], [2,700 samples across 7 string-named classes],
  [Feb 2025], [Protein–protein interaction graph: 4,644 proteins, 17,236 weighted edges],
  [June 2026], [11,000 news items: text + 10,000-dim BoW + year/month → 18 labels, 2–3 active],
)

#v(0.3em)
#emph[Sources: the thirteen exam PDFs under
raw/509486-.../\_text/. Five shapes, twelve sittings — the pattern repeats.]

#pagebreak()

= The answer template

Adapt these to the dataset in front of you. Each answer is 3–6 sentences. The
mark is for the justification, not the length.

== 1. MODEL
State the architecture, then one sentence of why tied to a property of *this*
dataset.

#recipe[
"I use #underline[architecture]. The input is #underline[property of the data],
so #underline[architecture] is appropriate because #underline[it handles that
property]. #underline[Alternative] would also work but #underline[reason it is
worse here]."
]

Reasons that earn the mark: sequential text of variable length → recurrent or
attention; local spatial structure → convolution; fixed-length vector with no
structure → fully connected; several heterogeneous inputs → multi-input with
concatenation; no labels → autoencoder then clustering; relational data →
graph network.

== 2. INPUT
*(a) Preprocessing.* Text: tokenise, lowercase, remove stopwords, truncate or
pad to a fixed length, then an embedding layer. BoW: it is already numeric —
normalise (TF-IDF or L2) and say why. Images: resize to a fixed resolution,
scale pixels to `[0,1]`, augment (flip/crop) if the set is small. Metadata:
normalise numeric ranges; one-hot small categoricals. Say explicitly if a
field needs *no* preprocessing.

*(b) Representation.* Always give a shape and a domain. "After padding to
`L = 100` tokens, the text branch input is `(batch, 100)` of integer indices
in `[0, |V|)`; the BoW branch is `(batch, 10000)` of non-negative counts; the
metadata branch is `(batch, 2)` scaled to `[0,1]`."

== 3. OUTPUT
Give the *number of units* and the *activation*, then why.
- One label out of K → `K` units, softmax (they compete; they sum to 1).
- Several labels at once → `K` units, *sigmoid* (independent per label).
- Binary → 1 unit, sigmoid.
- Regression → 1 unit, linear.

#trap[
*The single most common trap in this exam.* Multi-label is not multi-class.
If a sample can carry 2–3 labels at once, softmax is wrong: it forces the
outputs to compete. Use sigmoid per label with binary cross-entropy.
]

== 4. LOSS
Name it, and tie it to the output layer you just chose. Softmax → categorical
cross-entropy. Sigmoid multi-label → binary cross-entropy averaged over
labels. Linear → MSE (or MAE if outliers matter). Autoencoder → reconstruction
MSE. If classes are imbalanced, say you would weight the loss.

== 5. MODEL CONFIGURATION
*(a) Composition* — name the blocks in order, not the exact sizes: e.g.
"Embedding(|V|, 128) → BiLSTM(128) → Dropout(0.3) → Dense(64) → Dense(K)".
The papers say dimensions "can be object of tuning", so you are not expected
to fix them.

*(b) Activations* — ReLU in hidden layers (cheap, no vanishing gradient);
output activation as in Q3. Mention tanh/sigmoid inside recurrent cells if you
used them.

*(c) Regularisation and initialisation* — dropout between dense layers, L2
weight decay, early stopping on validation loss, batch normalisation. He
(ReLU) or Glorot/Xavier (tanh) initialisation.

*(d) Hyperparameters to tune* — learning rate, batch size, number and width of
layers, dropout rate, embedding dimension, sequence length. Say *how*: grid or
random search over a validation split.

== 6. MODEL EVALUATION
Say the *setting* first, then the *metrics*.
- Setting: split into train/validation/test, or k-fold cross-validation for a
  small dataset. Stratify the split when classes are imbalanced. The test set
  is touched once.
- Metrics: accuracy only if balanced; otherwise precision, recall and F1
  (macro-averaged over classes). Multi-label: per-label F1, plus subset
  accuracy or Hamming loss. Regression: RMSE / MAE. Clustering: silhouette, or
  an external index if any labels exist.
- Mention the learning curve to diagnose over- versus under-fitting.

== 7. MODEL INTERPRETATION #emph[(papers from Jan 2025 on)]
Name a method and what it gives you: attention weights over tokens; gradient
saliency (∂output/∂input); Integrated Gradients; SHAP or LIME for a
model-agnostic local explanation; occlusion — mask part of the input and
measure the change in prediction. One method, one sentence on what it shows,
one on its limitation.

= Worked answer — June 2026 sitting

#emph[Dataset: 11,000 news items. Inputs: raw text (1–100 words, mean 27.8),
a 10,000-dimensional bag-of-words, and publication year (2012–2022) and month.
Targets: binary matrix over K = 18 labels, 2–3 active per item. Source:
raw/509486-.../ML-amp-DL-2025/exam\\_test.pdf]

*1. MODEL.* A multi-input network: an embedding plus BiLSTM branch for the raw
text, a fully-connected branch for the bag-of-words, and a small dense branch
for the two metadata fields, concatenated into shared dense layers. The three
inputs are heterogeneous — a variable-length sequence, a fixed sparse vector,
and two scalars — so a single branch cannot represent all three. The text
branch captures word order that the BoW discards; the BoW branch captures
overall term frequency cheaply.

*2. INPUT.* (a) Text: lowercase, tokenise, remove stopwords, pad/truncate to
L = 100 (the stated maximum), map to indices, learn an embedding. BoW: apply
TF-IDF weighting and L2-normalise, since raw counts are dominated by frequent
words. Metadata: scale year to [0,1] over [2012, 2022]; encode month either
one-hot (12) or cyclically as (sin, cos) to preserve December→January
adjacency. (b) Shapes: text `(batch, 100)` integers in `[0, |V|)`; BoW
`(batch, 10000)` non-negative reals; metadata `(batch, 13)` or `(batch, 3)`
in `[0,1]`.

*3. OUTPUT.* 18 units with a *sigmoid* activation, shape `(batch, 18)`, each
in `[0,1]` and read as the probability that label k applies. Sigmoid, not
softmax: each item carries 2–3 labels simultaneously, so the labels must be
independent rather than competing for a probability that sums to one.

*4. LOSS.* Binary cross-entropy averaged over the 18 outputs — the correct
partner to a per-label sigmoid. Each label is an independent binary decision.
Since labels appear between 1,000 and 4,000 times, I would weight the positive
term per label to stop the frequent labels dominating.

*5. CONFIGURATION.* (a) Text: Embedding(|V|, 128) → BiLSTM(128) → Dropout(0.3).
BoW: Dense(256, ReLU) → Dropout(0.3). Metadata: Dense(16, ReLU). Concatenate →
Dense(128, ReLU) → Dropout(0.3) → Dense(18, sigmoid). (b) ReLU in hidden dense
layers, sigmoid at the output, tanh/sigmoid internal to the LSTM cells.
(c) Dropout, L2 weight decay, early stopping on validation loss, He
initialisation for ReLU layers. (d) Tune learning rate, batch size, embedding
dimension, LSTM width, dropout rate, and the decision threshold on the sigmoid
outputs — by random search on a validation split.

*6. EVALUATION.* Split 70/15/15 train/validation/test with an
iterative-stratification scheme suitable for multi-label data, so rare labels
appear in every split. Tune on validation; touch test once. Report per-label
precision, recall and F1, macro-averaged so rare labels count equally, plus
micro-F1 and Hamming loss. Since 2–3 labels are active on average, also report
precision-at-3. Inspect learning curves for over-fitting.

*7. INTERPRETATION.* Integrated Gradients over the embedded tokens gives a
signed relevance per input word for a chosen label, showing which words drove
that label. For the BoW branch the input is already interpretable, so gradient
magnitude maps directly onto vocabulary terms. Limitation: attributions are
local to one sample and do not establish a causal effect.

= On the day

#onthday[
+ *The dataset page is the only thing you have not seen.* Read it first and
  classify it: text / image / tabular / graph / unlabelled. Everything else
  follows from the table on page 2.
+ *Count the labels per sample.* One label → softmax + categorical
  cross-entropy. Two or more at once → sigmoid + binary cross-entropy. This
  single distinction carries questions 3 and 4.
+ *Always give a shape and a value domain* in question 2(b). It is asked for
  explicitly and is cheap to state.
+ *Motivate every choice in one sentence*, tied to a property of this dataset.
  Unjustified answers lose the marks; long answers do not gain them.
+ *Leave physical space between answers*, and keep the numbering and
  sub-items exactly as printed.
+ *Diarise the notebook deadline the moment you leave the room* — roughly 8–9
  days. No upload means the exam is rejected regardless of what you wrote.
+ In the notebook, *label any deviation from your written answer* with
  *CHANGE* in bold uppercase and a reason.
]

= Formula and vocabulary sheet

#table(columns: (auto, 1fr),
  [Softmax], [$"softmax"(z)_i = e^(z_i) / (sum_j e^(z_j))$ — one label of K],
  [Sigmoid], [$sigma(z) = 1 / (1 + e^(-z))$ — independent labels, or binary],
  [Categorical CE], [$L = - sum_(k=1)^K y_k log hat(y)_k$],
  [Binary CE (multi-label)], [$L = - 1/K sum_(k=1)^K [y_k log hat(y)_k + (1 - y_k) log (1 - hat(y)_k)]$],
  [MSE], [$L = 1/n sum_i (y_i - hat(y)_i)^2$ — regression, reconstruction],
  [Precision / Recall], [$P = "TP"/("TP"+"FP")$, $R = "TP"/("TP"+"FN")$],
  [F1], [$F_1 = 2 P R / (P + R)$; macro-F1 averages it over classes equally],
  [Hamming loss], [fraction of wrong label-slots, for multi-label],
  [ReLU], [$max(0, z)$ — hidden layers, no vanishing gradient],
  [Conv output size], [$(W - F + 2P) / S + 1$ for width W, filter F, padding P, stride S],
  [Dropout], [zero a fraction p of activations at training time only],
  [Early stopping], [halt when validation loss stops improving],
  [He init], [variance $2 / n_"in"$ — for ReLU],
  [Glorot init], [variance $2 / (n_"in" + n_"out")$ — for tanh/sigmoid],
)
"""
    rows = unique_questions("509486")
    doc += "\n#pagebreak()\n"
    doc += practice_block(
        rows,
        "Practice — every distinct question in the archive",
        "Real questions from the thirteen archived sittings, de-duplicated. "
        "Work them against a dataset of your choosing; the phrasing is what "
        "you will meet.",
        space=5.0, limit=30)
    return doc


FZ_TITLE = "FUZZY SYSTEMS AND EVOLUTIONARY COMPUTING"
FZ_SUB = "509487 · exam kit · the minimum to reach 18/30"


def fuzzy_systems() -> str:
    doc = preamble(FZ_TITLE, FZ_SUB)

    doc += """
= Start here: what this paper is

#brief[
*6 to 8 questions, each printing its own marks* (seen: 3, 4, 5, 7 and 8),
summing to about 30. Papers are *bilingual* — the question is given in English
and Italian, so answer in whichever is faster for you.

Every paper is the same two halves, and the same shapes recur:

#table(columns: (auto, auto, 1fr),
  [*Type*], [*Typical marks*], [*What it is*],
  [Definition], [3–4 each], [Recall. Four or five of them per paper. Free marks.],
  [Settings table], [4], [Fill a 5-row table for GP or PSO. Pure recall.],
  [Set exercise], [7–8], [Triangular or discrete fuzzy sets, or a relation composition.],
  [EA by hand], [7], [Run a genetic algorithm or genetic programming for one generation.],
)

*Where the marks actually are:* roughly half the paper is recall you can
memorise in an evening. The other half is two big exercises that follow fixed
recipes. Learn the definitions and the six recipes and you are at 18 without
understanding a single proof.
]

== Every question asked across the seven archived sittings

#table(columns: (auto, 1fr),
  [*22 Jun 2023*], [fuzzification/defuzzification + frame of cognition (5) · cardinality (3) · crossover with permutations (4) · general EA scheme (5) · triangular sets f,g (8)],
  [*11 Jul 2023*], [same shapes, different numbers],
  [*07 Sep 2023*], [same shapes, different numbers],
  [*21 Jun 2024*], [k-means vs fuzzy c-means (4) · t-norm definition + example (4) · *GP settings table* (4) · exploration vs exploitation (4) · relation composition (3) · discrete set: core, α-cut, centre of gravity (4) · *run a GA by hand* (7)],
  [*09 Jul 2024*], [linguistic variable (4) · reflexive/symmetric/transitive relation (4) · *PSO settings table* (4) · mutation with permutations (4) · triangular sets + strong α-cut (7) · *run GP by hand* (7)],
  [*2025 example*], [published sample paper, same shapes],
  [*29 Jan 2026*], [Gaussian fuzzy set (4) · Mamdani vs Takagi–Sugeno (4) · EA pseudo-code (4) · selection pressure (4) · relation composition (3) · discrete set: complement, α-cut, cardinality (4)],
)

= Part A — Fuzzy sets

A fuzzy set on universe $X$ is a function $f: X -> [0,1]$; $f(x)$ is the
*membership degree* of $x$.

#table(columns: (auto, 1fr),
  [*Support*], [$"supp"(f) = {x : f(x) > 0}$],
  [*Core*], [$"core"(f) = {x : f(x) = 1}$],
  [*Height*], [$sup_x f(x)$; the set is #emph[normal] if the height is 1],
  [*α-cut*], [$f_alpha = {x : f(x) >= alpha}$],
  [*Strong α-cut*], [$f_alpha^+ = {x : f(x) > alpha}$ — strictly greater. Asked in July 2024.],
  [*Cardinality*], [$|f| = sum_x f(x)$],
  [*Complement*], [$not f(x) = 1 - f(x)$],
  [*Entropy*], [$H(f) = - sum_x f(x) log f(x)$],
  [*Fuzziness*], [$1/n sum_x |f(x) - not f(x)|$ (Hamming)],
  [*Centre of gravity*], [$(sum_x x dot f(x)) / (sum_x f(x))$ — same formula as centroid defuzzification],
)

== t-norms and t-conorms — asked verbatim, June 2024

A *t-norm* $T: [0,1]^2 -> [0,1]$ models fuzzy *intersection*. It is
commutative, associative, monotone (non-decreasing in each argument), and has
*1 as neutral element*: $T(x, 1) = x$.

#table(columns: (auto, auto, auto),
  [*Name*], [*t-norm (AND)*], [*t-conorm (OR)*],
  [Gödel / minimum], [$min(x, y)$], [$max(x, y)$],
  [Product], [$x dot y$], [$x + y - x y$],
  [Łukasiewicz], [$max(0, x + y - 1)$], [$min(1, x + y)$],
)

A *t-conorm* is the dual: neutral element *0*, models *union*. Quoting one
named pair with its formula is what earns the 4 marks.

== Membership functions to be able to write from memory

*Triangular*, corners $A < B < C$ — by far the most asked:
$ f(x) = cases((x - A)/(B - A) "if" x in [A,B], (C - x)/(C - B) "if" x in [B,C], 0 "otherwise") $

*Trapezoidal*, $A<B<C<D$: rises on $[A,B]$, is 1 on $[B,C]$, falls on $[C,D]$.

*Gaussian* — asked January 2026: $ f(x) = e^(-((x - m)^2) / (2 sigma^2)) $
$m$ is the centre (membership 1), $sigma$ the width.

== Linguistic variable — asked July 2024

#worked[
From the lecturer's own answer sheet
(#emph[Final Exercises - update.pdf]): a linguistic variable is a variable
*taking words as values*, whose meaning is given by a fuzzy set. Formally a
tuple $(L, T(L), U, G, M)$ — $L$ the name, $T(L)$ the linguistic terms it can
take, $U$ the universe, $G$ the grammar of modifiers, $M$ the mapping from
each term to a fuzzy set.

*Example:* $L$ = Temperature, $T(L) = {"cold", "warm", "hot"}$,
$U = [-20, 50]$, $G = {"very", "not"}$, and $M$ assigns a fuzzy set to each
term. The modifier *very* is $"very"(f)(x) = f(x)^2$.
*Draw at least one of the sets* — the answer sheet says so explicitly.
]

== Fuzzy relations

A fuzzy relation is $R: X × Y -> [0,1]$. Asked July 2024, the three properties
(for $R$ on $X × X$):

#table(columns: (auto, 1fr),
  [*Reflexive*], [$R(x, x) = 1$ for every $x$],
  [*Symmetric*], [$R(x, y) = R(y, x)$ for every $x, y$],
  [*Transitive*], [$R(x, z) >= max_y min(R(x,y), R(y,z))$ (max–min transitivity)],
)

All three together make it a *fuzzy equivalence* relation.

== Rule-based systems

*Fuzzification* maps a crisp input onto membership degrees over the linguistic
terms. *Defuzzification* maps the fuzzy output back to one crisp value, usually
the *centroid* $x^* = (sum_i x_i mu(x_i)) / (sum_i mu(x_i))$.

A *frame of cognition* (a *fuzzy partition*) is the family of linguistic terms
covering the universe — "very small, small, medium, large, very large" over
$[l, r]$. Fuzzification is precisely the step that maps a crisp value onto that
frame: that is the connection the June 2023 paper asks for.
#emph[Source: FuzzyRules.pdf, Ciucci.]

*Mamdani*: `IF (X1 is LT1) and ... THEN Y is LT0` — the consequent is a *fuzzy
set*, so the output *must* be defuzzified.
*Takagi–Sugeno*: the consequent is a *function of the inputs*, typically linear
`THEN y = a0 + a1 x1 + ...` — output already crisp, *no defuzzification*.

== k-means vs fuzzy c-means — asked June 2024

k-means assigns each point to *exactly one* cluster (hard membership, 0 or 1).
Fuzzy c-means gives each point a *degree of membership in every* cluster, with
memberships summing to 1 across clusters, controlled by a fuzzifier $m > 1$.
Centres are then membership-weighted means:
$ c_j = (sum_i u_(i j)^m x_i) / (sum_i u_(i j)^m) $
Larger $m$ means fuzzier boundaries; as $m -> 1$ it degenerates to k-means.

= Part B — Evolutionary computing

== The general scheme — free marks, appears on nearly every paper

#recipe[
```
INITIALISE population with random candidate solutions
EVALUATE each candidate
REPEAT until (termination condition satisfied):
    SELECT parents
    RECOMBINE pairs of parents          (crossover)
    MUTATE the resulting offspring
    EVALUATE new candidates
    SELECT individuals for the next generation
```
Asked as prose or as pseudo-code. Learn the pseudo-code and you can answer
either.
]

== Operators, and the exploration/exploitation split — asked June 2024

*Exploration* searches new regions of the space; *exploitation* refines what
is already good. *Mutation* provides exploration, *crossover (recombination)*
provides exploitation, and *selection* pushes towards exploitation. Too much
exploitation converges prematurely; too much exploration never converges.

*Crossover* recombines two parents. With *permutation* representations
one-point crossover breaks validity (it duplicates and drops elements), so
order-preserving operators are used: *PMX*, *order crossover (OX)*, *cycle
crossover*. *n-point crossover* cuts the parents at $n$ points and alternates
the segments.

*Mutation* is a small random change to one individual — bit-flip for binary,
*swap / insert / inversion* for permutations, creep for integers.

*Selection pressure* is how strongly fitter individuals are favoured. High:
fast convergence, risk of a local optimum. Low: more exploration, slow.

== The settings table — 4 marks, pure recall

Asked for *genetic programming* (June 2024) and *particle swarm optimisation*
(July 2024). Same five rows every time.

#table(columns: (auto, 1fr, 1fr),
  [ ], [*Genetic Programming*], [*Particle Swarm Optimisation*],
  [Representation], [Tree structures (expressions)], [Real-valued vector, plus a velocity vector],
  [Recombination], [Exchange of subtrees], [None],
  [Mutation], [Random change in the tree (replace a subtree)], [None — movement is by velocity update],
  [Parent selection], [Fitness proportional], [None — every particle is a parent],
  [Survivor selection], [Generational replacement], [Replaces the particle itself],
)

#emph[Source: Eiben & Smith, Introduction to Evolutionary Computing, the
course textbook; chapter decks ch06-Popular\_EA\_Variants are in the archive.]

= The exercise recipes — where the big marks are

== Recipe 1 — Triangular sets (7–8 marks)
+ *Equations*: apply the triangular formula to each set's corners.
+ *Intersection* ($min$): find where the two lines cross; the intersection is
  the lower of the two on each side of that point.
+ *Union* ($max$): the upper envelope.
+ *Complement*: $1 - f(x)$ piecewise; it equals *1 outside the support*.
+ *Support / core*: $[A, C]$ and $\{B\}$.

#worked[
$A=1, B=3, C=5$; $D=4, E=6, F=8$.
$f(x) = (x-1)/2$ on $[1,3]$, $(5-x)/2$ on $[3,5]$, else 0.
$g(x) = (x-4)/2$ on $[4,6]$, $(8-x)/2$ on $[6,8]$, else 0.
They cross at $x = 4.5$, so
$f and g = (x-4)/0.5$ on $[4, 4.5]$, $(5-x)/0.5$ on $[4.5, 5]$, else 0.
$"supp"(f) = [1,5]$, $"core"(f) = \{3\}$; $"supp"(g) = [4,8]$, $"core"(g) = \{6\}$.
]

== Recipe 2 — Discrete set: core, support, complement, cardinality, α-cut
Read values off the list and apply the definitions. Cardinality is the plain
sum. The α-cut takes everything at or above α — the *strong* α-cut takes
strictly above.

#worked[
$g(10)=0.3, g(15)=0.5, g(20)=1, g(25)=1, g(30)=0.5, g(35)=0.3$, else 0.
core $= \{20, 25\}$; supp $= \{10,...,35\}$.
$not g$: $0.7, 0.5, 0, 0, 0.5, 0.7$ — and *1 at every other point*.
$|g| = 3.6$. α-cut at $0.4$: $\{15, 20, 25, 30\}$.
]

== Recipe 3 — Entropy and fuzziness
#worked[
Same set. $H(g) = -(0.3 log 0.3 + 0.5 log 0.5 + 0.5 log 0.5 + 0.3 log 0.3) = 0.6148$
(terms at 0 and 1 contribute nothing).
Fuzziness: $(0.4 + 0 + 1 + 1 + 0 + 0.4)/6 = 2.4/6 = 0.4$.
]

== Recipe 4 — Centre of gravity
$(sum x dot g(x)) / (sum g(x))$. Multiply each point by its membership, sum,
divide by the cardinality.

== Recipe 5 — Composition of fuzzy relations (3 marks)
$ (R compose S)(x, z) = max_y min(R(x,y), S(y,z)) $
A matrix product with $min$ for multiply and $max$ for add.

#worked[
June 2024. $R$ row $x_1 = (0.4, 0, 0.8)$, $S$ column $z_1 = (1, 0, 0.8)$.
Pairwise minima: $min(0.4,1)=0.4$, $min(0,0)=0$, $min(0.8,0.8)=0.8$.
Maximum $= 0.8$. So $(R compose S)(x_1,z_1) = 0.8$. Repeat per cell.
]

== Recipe 6 — Run a Genetic Algorithm by hand (7 marks)
Asked June 2024 on 6 binary digits with $f(x) = x_1 + x_2 + 2x_3 + 3x_4 + x_5 + 2x_6$.

#recipe[
+ *Initial population*: invent 4 random bitstrings and *write them down*, e.g.
  `101010`, `110011`, `001101`, `111000`.
+ *Fitness*: evaluate $f$ on each. For `101010`: $1+0+2+0+1+0 = 4$.
+ *Fitness-proportionate selection*: compute $p_i = f_i / sum_j f_j$; show the
  proportions, then say which parents you drew.
+ *2-point crossover*: pick two cut points, swap the middle segment between
  the two parents. Show both children.
+ *Bit-wise mutation, $p = 1/6$*: with 6 bits that is one expected flip per
  individual — flip one bit and say which, and that others were left.
+ *Generational replacement*: the 4 children replace the 4 parents entirely.
]

#trap[
Marks here are for *showing the mechanism*, not for finding the optimum. Write
the population at every step, show the fitness arithmetic for at least one
individual, and name each operator as you apply it. Inventing the random draws
is expected — say "suppose the roulette selects ...".
]

== Recipe 7 — Genetic Programming by hand (7 marks)
Asked July 2024 on arithmetic expressions over $\{+,-,*,/\}$ and $\{0,1,-1,x\}$,
fitness $sum_i |g(i) - e(i)|$ with $g(x) = 2x^2 + 2x + 1$ — *lower is better*.

#recipe[
+ *Initial population, grow method, max depth 4*: draw 4 expression *trees*.
  Grow means each node is randomly an operator or a terminal, so branches end
  at different depths. Write them both as trees and in infix, e.g.
  $(x * x) - (1 + x)$.
+ *Fitness*: evaluate each expression at the required points, take
  $sum |g(i) - e(i)|$. Show the arithmetic for one.
+ *Selection and recombination*: subtree crossover — pick a node in each
  parent, swap the subtrees. Draw the result.
+ *Mutation*: replace a randomly chosen subtree with a new random one.
]

#trap[
Draw the trees. A GP answer written only in infix loses the marks for
representation, and subtree crossover cannot be shown without them.
]

= On the day

#onthday[
+ *Read the marks on every question first* and budget time in proportion. A
  7-mark GA-by-hand is worth nearly two definitions plus a relation composition.
+ *Do the definitions first* — they are recall, they are on every paper, and
  they are the cheapest marks on it.
+ *State the formula before using it.* Partial credit attaches to method.
+ *Sketch the triangular sets.* The crossing point is where the answer lives.
+ *Never omit "0 otherwise" and "1 everywhere else"* in piecewise membership
  functions and complements — the official solutions always write them.
+ *Write the EA pseudo-code from memory.* Free marks, nearly every sitting.
+ For the by-hand EA questions, *show every generation and name every
  operator*. The mark is for mechanism, not for the optimum.
+ Answer in *English or Italian*, whichever is faster.
]

= Formula sheet

#table(columns: (auto, 1fr),
  [Fuzzy set], [$f: X -> [0,1]$],
  [Support / core], [$\{x: f(x)>0\}$ / $\{x: f(x)=1\}$],
  [α-cut / strong], [$\{x: f(x) >= alpha\}$ / $\{x: f(x) > alpha\}$],
  [Cardinality], [$|f| = sum_x f(x)$],
  [Complement], [$not f(x) = 1 - f(x)$],
  [t-norms (AND)], [$min(x,y)$; $x y$; $max(0, x+y-1)$],
  [t-conorms (OR)], [$max(x,y)$; $x+y-x y$; $min(1, x+y)$],
  [Triangular], [$(x-A)/(B-A)$ on $[A,B]$; $(C-x)/(C-B)$ on $[B,C]$; 0 otherwise],
  [Gaussian], [$e^(-(x-m)^2 / (2 sigma^2))$], 
  [Entropy], [$H(f) = -sum_x f(x) log f(x)$],
  [Fuzziness], [$1/n sum_x |f(x) - (1-f(x))|$],
  [Centre of gravity], [$(sum_x x f(x)) / (sum_x f(x))$],
  [Max–min composition], [$(R compose S)(x,z) = max_y min(R(x,y), S(y,z))$],
  [Relation properties], [reflexive $R(x,x)=1$; symmetric $R(x,y)=R(y,x)$; transitive $R(x,z) >= max_y min(R(x,y),R(y,z))$],
  [c-means centre], [$c_j = (sum_i u_(i j)^m x_i) / (sum_i u_(i j)^m)$],
  [Very (modifier)], [$"very"(f)(x) = f(x)^2$],
  [Sudoku fitness], [$1/(1 + "duplicates")$],
  [Knapsack fitness], [$sum "values"$ minus penalty for excess weight],
)
"""
    rows = unique_questions("509487")
    doc += "\n#pagebreak()\n"
    doc += practice_block(
        rows,
        "Practice — every distinct question in the archive",
        "Real questions from the archived sittings, de-duplicated, with the "
        "marks the paper printed. The computational types are solved by the "
        "recipes above, which come from the lecturer's own published answers.",
        space=6.0, limit=40)
    return doc


def main() -> int:
    compile_to(machine_learning(), "EXAM-KIT_509486_Machine-Learning-Part-2")
    compile_to(fuzzy_systems(), "EXAM-KIT_509487_Fuzzy-Systems")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
