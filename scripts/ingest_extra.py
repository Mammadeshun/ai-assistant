#!/usr/bin/env python3
"""Ingest the material the student collected from the course WhatsApp groups.

Everything lands in data/raw/user-supplied/ with a manifest entry, exactly like
a scraped page, so the drill bank and library pick it up with no special cases.

Provenance is recorded per file, because it varies and it matters:
  pdf-text     extracted from the PDF's own text layer
  ocr          tesseract, on a photograph or a scan - expect errors
  transcribed  read and typed out by hand, highest fidelity

Course assignment is by content, not filename: several files arrive as bare
UUIDs from WhatsApp.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gradplan.archive import RawArchive  # noqa: E402

SRC = Path(
    "/tmp/claude-0/-home-user-ai-assistant/"
    "722c79dc-5be6-56ca-bc93-f56b1ec9cc99/scratchpad/extra"
)
RAW = Path("data/raw")

# file -> (course, label, provenance)
PDFS = {
    "202501.pdf": ("509496", "IR past exam January 2025", "pdf-text"),
    "202601.pdf": ("509496", "IR past exam January 2026", "pdf-text"),
    "2fe5ef70-cb7f-4f4f-af75-4506ae73560d_260801_144248.pdf":
        ("509488", "TMNLP exam - linguistics part", "pdf-text"),
    "444c4d31-ddf0-422f-8dda-9fe9b41f1304_260801_144054.pdf":
        ("509488", "TMNLP written exam sample", "pdf-text"),
    "a3d73565-501d-4fb0-9662-886d00529784_260801_144042.pdf":
        ("509488", "TMNLP exam - co-occurrence and embeddings", "pdf-text"),
    "TM OPEN QUESTIONS_260801_143948.pdf":
        ("509488", "TEXT MINING OPEN QUESTIONS - ANSWERS 2022-2023", "pdf-text"),
    "[TMNLP 23_24] Exam questions sample_260801_144017.pdf":
        ("509488", "TMNLP 23_24 exam questions sample", "pdf-text"),
    "[TMNLP-2025_2026] Practice Written Exam copy_260801_144001.pdf":
        ("509488", "TMNLP 2025_2026 practice written exam PART 2 OF 3", "pdf-text"),
    "Cg psy.pdf": ("509485", "Cognitive Psychology - full Q&A revision notes", "pdf-text"),
    "Cog psy.pdf": ("509485", "Cognitive Psychology - Esercizi chapter exercises", "pdf-text"),
    "Cog.pdf": ("509485", "Cognitive Psychology - chapter quizzes with answers", "pdf-text"),
}

# The nested zip is one course's archive, by year.
NESTED_COURSE = "509486"

# Photographs. Transcriptions below are typed from the images; where a photo was
# too damaged or oblique to read reliably, the tesseract output is used instead
# and marked as such.
PHOTOS = {
    "photo_2026-08-01_14-41-42.jpg": ("509488", "TMNLP PART 3 OF 3 - 28/06/2024", "transcribed"),
    "photo_2026-08-01_14-41-51.jpg": ("509488", "TMNLP - TF-IDF exercise", "ocr"),
    "photo_2026-08-01_14-41-59.jpg": ("509488", "TMNLP PART 1 OF 3 - 28/06/2024", "ocr"),
    "photo_2026-08-01_14-42-10.jpg": ("509488", "TMNLP written exam 30/06/2023", "ocr"),
    "photo_2026-08-01_14-42-21.jpg": ("509488", "TMNLP - embeddings matching exercise", "ocr"),
    "photo_2026-08-01_14-51-16.jpg": ("509494", "BRAIN MODELLING EXAM 18 June 2026", "transcribed"),
    "photo_2026-08-01_14-51-17.jpg": ("509494", "BRAIN MODELLING - RC circuit and Poisson", "ocr"),
    "photo_2026-08-01_14-51-17 (2).jpg": ("509494", "BRAIN MODELLING - Hodgkin-Huxley", "ocr"),
    "photo_2026-08-01_14-51-18.jpg": ("509494", "BRAIN MODELLING - mean-field question", "ocr"),
    "photo_2026-08-01_14-51-20.jpg": ("509494", "BRAIN MODELLING EXAM 12 February 2024", "transcribed"),
    "photo_2026-08-01_14-51-21.jpg": ("509494", "BRAIN MODELLING EXAM 29 January 2025", "ocr"),
    "photo_2026-08-01_14-51-22.jpg": ("509488", "TMNLP - sentiment fragment", "ocr"),
    "photo_2026-08-01_14-51-23.jpg": ("509494", "BRAIN MODELLING EXAMS 1 March / 20 June / 10 July 2024", "transcribed"),
    "photo_2026-08-01_14-51-24.jpg": ("509494", "BRAIN MODELLING EXAM 11 Sept 2024", "transcribed"),
    "photo_2026-08-01_14-51-25.jpg": ("510638", "Web and Social Networks Search and Analysis - written exam 16 June 2025", "transcribed"),
    "photo_2026-08-01_14-51-28.jpg": ("510638", "Web and Social - graph question fragment", "ocr"),
}

TRANSCRIPTIONS: dict[str, str] = {
"photo_2026-08-01_14-41-42.jpg": """\
(Track 2.A) Name: Surname: ID:
PART 3 OF 3 - Written Exam of TM&NLP
28/06/2024

1) What is the attention mechanism and why it has been introduced? Describe at least
   one attention variant. Additionally, what are the steps involved in computing the
   attention specifically for a Transformer model?

2) What is the objective of text representation? What is meant by contextualized word
   embedding? Describe ELMo and BERT methods for text representation.

3) Explain the concept of Positive Pointwise Mutual Information (PPMI) and discuss its
   advantages over raw word frequency counts in measuring word association. Provide an
   example to illustrate how PPMI is computed (including its formula). What are the
   solutions for handling rare words with PPMI? Why do we need them?
""",

"photo_2026-08-01_14-51-16.jpg": """\
BRAIN MODELLING - EXAM - 18 June 2026

1. [5] Describe principles and models for transformation from dynamic stimuli
   (depending on space and time) to time-dependent firing rates
2. [6] Define the entropy rate for a neural response described as a spike train
   (spike times), with graphs
3. [6] Draw and describe the ionic current by a stochastic kinetic scheme of an
   individual voltage-dependent ion channel characterized by 2 closed states and 1 open
   state. Finally, describe the "equivalent" deterministic model (Hodgkin-Huxley
   approach) if many channels of that type are present.
4. [6] Define the synaptic weight modulation by Spike Timing-Dependent Plasticity, and
   draw a plausible graph with both long-term potentiation and depression
5. [5] Describe FitzHugh-Nagumo neuron model and its dynamics
6. [4] Describe the informatic workflow to develop a bottom-up model of a brain circuit,
   using Brain Scaffold Builder as an example of framework
""",

"photo_2026-08-01_14-51-20.jpg": """\
BRAIN MODELLING - EXAM - 12th February 2024

1. Draw a graph of an action potential, indicating the main phases and the relative
   roles of the main ion channels
2. Define a response tuning curve, and make an example using also graphs
3. Describe the discrimination between two different stimulus values as a case of
   single-cell decoding
4. Define the entropy in the domain of neural responses, and draw it as function of
   probability when a neuron responds in only two possible ways
5. Describe the Integrate-and-Fire Neuron model and write down its equation including
   the synaptic currents
6. Define the gating variables for a transient conductance, drawing them as function of
   Voltage
7. Define the mechanisms of long-term plasticity and the Hebbian learning principles
8. What's a mean field theory? Give an example of application in neuroscience
""",

"photo_2026-08-01_14-51-23.jpg": """\
BRAIN MODELLING - EXAM - 1st March 2024

1. Define the membrane capacitance and compute how a current of 2 nA changes the
   membrane potential of a neuron (electronically compact) with a surface area of
   0.03 mm^2 (specific capacitance = 0.9 uF/cm^2).
2. Describe the steps for the encoding process from dynamic stimuli to time-dependent
   firing rates.
3. Describe the population decoding, also giving an example of population vector.
4. Describe the enriched equation of the Leaky Integrate-and-Fire Model to include the
   Spike-Rate Adaptation and draw the relation between the injected current and the
   output frequency.
5. Draw and explain a state diagram for a 5-state channel (4 state closed, 1 open).
6. Define the Spike Timing-Dependent Plasticity (STDP) using also representative graphs.
7. In the context of connectivity, define information integration theory with also
   examples of altered balance.
8. Explain what the FitzHugh-Nagumo model is and outline its key characteristics.
   Describe the dynamic behaviours as the external current supplied to a neuron varies.

BRAIN MODELLING - EXAM - 20th June 2024

1. Describe how the propagation velocity in a neuron can be increased
2. Describe how one can model stochastic spike sequences
3. Describe the probability theory for neural activity (Bayes theorem), given s as
   stimulus and r = (r1, r2, ..., rN) for N neurons (population) as a list of
   spike-count firing rates
4. Define the mutual information in the domain of neural responses, and draw the mutual
   information as function of probability when there are two possible stimulus values
   (+ and -) but the encoding is not perfect (probability of an incorrect response Px)
5. Define what is "Refractoriness" and how it can be included in an integrate-and-fire
   neuron model
6. Define the Hodgkin-Huxley model and equation system
7. Define the equation of the postsynaptic conductance dynamics (P, open probability),
   and define possible functions to represent Ps(t) for fast and slow synapses
8. What are the advantages of atlas-based modelling?

BRAIN MODELLING - EXAM - 10th July 2024

1. Define the membrane resistance and compute how much current is needed to generate a
   membrane potential change of 20 mV in a neuron with R of 50 MOhm
2. Describe how one can measure the selectivity of neurons to dynamic stimuli
3. Define the entropy rate H considering the neural response as a spike train
4. Describe the Leaky Integrate-and-Fire Model and define the main equation and its
   variables
5. Define the equation of the synaptic Release Probability and the possible Short-term
   modifications
6. Describe the principles of the Stochastic models of individual ionic channels,
   defining g.
7. Define the main structural and functional properties of the cerebellum
8. Define the condition for which a spiking neural network is defined as balanced, how
   does a balanced (or imbalanced) state impact on the functionality of the network,
   and what measure could be taken to measure the balance.
""",

"photo_2026-08-01_14-51-24.jpg": """\
BRAIN MODELLING - EXAM - 11th Sept 2024

1. Define the Nernst equation and apply it to compute the reversal potential of Na+,
   knowing that RT/F = 27 mV and the outside concentration is 9 times the inside one
2. Describe how neurons encode information, and which quantities can be extracted
3. Define the mutual information in the domain of neural responses, and draw the mutual
   information as function of probability when there are two possible stimulus values
   (+ and -) but the encoding is not perfect (probability of an incorrect response Px)
4. Define what is "Refractoriness" and how it can be included in an integrate-and-fire
   neuron model
5. Define space-time receptive fields
6. Define the gating variable of a voltage-dependent ionic channel gate for a persistent
   Conductance (n as the probability of a gate being in the open state), defining the
   equation and its variables
7. Define the Synaptic Conductance and the synaptic current
8. Describe the principles of the Conductance-Based multi-compartment models
""",

"photo_2026-08-01_14-51-25.jpg": """\
University of Milano-Bicocca, University of Milan (La Statale), University of Pavia
Bachelor's Degree in Artificial Intelligence

Web and Social Networks Search and Analysis
Written Examination
Prof. Marco Viviani
June 16, 2025

1. [3 points] Illustrate the main characteristics underlying complex networks; also
   discuss the similarities and differences of these characteristics to those of regular
   networks and random networks; furthermore, how do these characteristics relate to one
   another?

2. [4 points] Given the undirected graph G illustrated in Figure 1:
   - Indicate maximal cliques;
   - Compute the local clustering coefficient of nodes c and e;
   - Compute the average degree of G by employing the Handshaking Lemma;
   - Compute the delta centrality of the node c when P(G) = ||G||.

3. [5 points] Illustrate the concepts of Web 1.0 and Web 2.0, detailing their main
   characteristics, the technologies used, and the main differences. Furthermore, given
   the undirected graph G illustrated in Figure 2:
   - Indicate if there are any bridges and/or articulation points;
   - Provide the incidence matrix of the graph;
   - Compute the betweenness centrality of nodes c and h;

4. [3 points] What is assortativity in network theory, and how does it influence the
   formation and dynamics of networks? Please provide a detailed explanation.
""",
}

QUANTUM_RECALL = """\
THEORETICAL AND QUANTUM PHYSICS FOR AI (509492) - MODULE 2, QUANTUM INFORMATION
Student recollection of the exam questions, with the expected answers.
Handwritten note, transcribed. Provenance: a classmate's recall, not an official paper.

1. Definition of information "according to this course".

2. Hamiltonian H = [[h*Omega, 0], [0, h*Omega]] in the basis {|0>, |1>}, initial state
   |psi(0)> = sqrt(3/5)|0> + i*sqrt(2/5)|1>.
   Compute <Z> on |psi(t)> for t > 0.        (answer should be 1/5)

3. Information capacity of a system made of a spin-1/2 particle and a 4-level atom.
                                              (answer should be log2 8)

4. (Full text not recalled, but it was like:) What does "[A,B] = 0" say about
   observables A and B?          (answer should be that they share an eigenbasis)

5. Reduced matrix of B in |psi> = sqrt(3/7)|00> + e^(i*pi/3)*sqrt(4/7)|11>.
                                  (answer should be 3/7|0><0| + 4/7|1><1|)

6. Purity of rho = 1/2|00><00| + 1/4|00><11| + 1/4|11><00| + 1/2|11><11|.
                                              (answer should be 5/8)

7. To which state does this Bloch vector correspond?  a = (0, 1, 0)
                                              (answer should be |y+>)

8. Which of the following functions is (normalized and) a valid wave function?
   Only two recalled: (1/2pi)cos x , e^(-|x|)/sqrt(pi)      (answer should be the second)

9. Uncertainty relation. A = [[0,1],[1,0]], B = [[0,-i],[i,0]], |psi> = |x+>.
   Delta_A * Delta_B >= ?                     (answer should be 0)

10. On which of these states does A get outcome 1 with 100% probability?
    A = [[0,0,0,0],[0,3/2,i/2,0],[0,-i/2,3/2,0],[0,0,0,-1]]
                                    (answer should be (1/sqrt2)(0,1,i,0)^T)

NOTE ON FORMAT - this contradicts the earlier assumption that 509492 is an
Ethics-style multiple-choice paper. Questions 2, 3, 5, 6, 9 require actual
computation (time evolution and expectation values, reduced density matrices,
purity, commutators); only 7, 8 and 10 are recognition items. Budgeting this as a
cheap MCQ exam understates it.
"""


def main() -> int:
    archive = RawArchive(RAW)
    added = 0

    def save(course: str, name: str, provenance: str, payload, kind: str, src: Path | None):
        nonlocal added
        slug = "".join(ch if ch.isalnum() else "-" for ch in name)[:70].strip("-")
        archive.save(
            source="whatsapp",
            label=f"file-{course}-extra-{slug}",
            url=f"whatsapp://{provenance}/{src.name if src else name}",
            payload=payload,
            kind=kind,
            status=200,
        )
        added += 1

    for filename, (course, name, provenance) in PDFS.items():
        path = SRC / filename
        if not path.exists():
            print(f"  MISSING {filename}")
            continue
        save(course, name, provenance, path.read_bytes(), "pdf", path)

    nested = SRC / "nested"
    for path in sorted(nested.rglob("*.pdf")):
        year = path.parent.name
        save(
            NESTED_COURSE,
            f"ML exam {path.stem} ({year})",
            "pdf-text",
            path.read_bytes(),
            "pdf",
            path,
        )

    for filename, (course, name, provenance) in PHOTOS.items():
        path = SRC / filename
        if not path.exists():
            print(f"  MISSING {filename}")
            continue
        if provenance == "transcribed" and filename in TRANSCRIPTIONS:
            text = TRANSCRIPTIONS[filename]
        else:
            ocr = path.with_suffix("").with_suffix(".ocr.txt")
            alt = SRC / (Path(filename).stem + ".ocr.txt")
            text = alt.read_text() if alt.exists() else (ocr.read_text() if ocr.exists() else "")
            text = f"[OCR from a photograph - expect transcription errors]\n\n{text}"
        if text.strip():
            save(course, name, provenance, text, "text", path)

    save("509492", "Quantum module 2 - recalled exam questions with answers",
         "transcribed", QUANTUM_RECALL, "text", None)

    print(f"ingested {added} documents from the course groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
