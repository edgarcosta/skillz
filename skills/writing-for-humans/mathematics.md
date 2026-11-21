# Mathematical writing

Adapted, with permission, from Samuel Grushevsky's WriteBetter skill.

Read this when the text states or explains mathematics, in a paper, an email, a pull request body, a docstring or a comment. These rules add to SKILL.md.

## Orient the reader

- Near the start, say three things: the question the text answers, what made it hard, and the idea that makes the answer possible. For code, the question is what it computes and the idea is the mathematical fact the algorithm relies on. Skip the difficulty when there was none.
- Before a non-obvious construction, such as a correction term, a parameter choice or a precomputed table, state its job: the property it must have or the obstacle it removes. For a parameter that balances two error terms, name both terms first.
- At a change of stage, such as a new section or the next phase of an algorithm, say what result is carried forward and what remains to prove. A short proof whose route is visible needs no such sentence.

## Make the reasoning legible

- Explain why each step works, not only which steps were taken. At the decisive step, name the hypothesis that makes it available and say how its result is used.
- For a formula-based algorithm, include one equality or implication connecting the formula to the promised result, and name the hypothesis that licenses it. Naming a theorem alone does not supply this connection. Keep this bridge when shortening a docstring or explanation. Use only supplied or verified facts.
- After a computation or a technical conclusion, the next sentence says what it means for the claim. For a numerical criterion, say which property of the objects it detects.
- Shorten a deduction only when the reader can redo it from inputs the text names, with no hidden choice or extra hypothesis. Write out the inference for steps a standard tool does not make automatic: generic to all fibers, a finite search to all cases, local to global, floating-point agreement to exact equality.
- When a step uses more than the sentence before it, name its input by what it says: "the dimension bound in Lemma 3", "since $N$ is squarefree". When the justification comes later, say where: "proved in Section 4".

Weak: "Hence $a_p$ is even for every odd prime $p$ of good reduction."
Better: "Since $E$ has a rational point of order 2, and reduction modulo an odd prime $p$ of good reduction is injective on 2-torsion, $2$ divides $\#E(\mathbb{F}_p) = p + 1 - a_p$. As $p + 1$ is even, so is $a_p$."

## Keep informal explanations accountable

Informal explanations make mathematical claims too, so the claim-strength rule in SKILL.md applies to them. Check each against the formal statement for these distinctions:

- a choice that suffices, versus an optimal or unique one;
- a hypothesis this proof uses, versus one the theorem needs;
- an analogy, versus an equivalence ("behaves like" versus "is");
- a separate choice for each parameter, versus one uniform choice.

"Canonical" and "natural" are claims too; use them only where the source establishes them.

Every summary of a theorem states all of its hypotheses and its status: conditional on GRH, for $p$ large enough, or for a generic member of a family.

A name does not close a gap: calling an isomorphism "descent data" does not prove the compatibility it suggests. Report a gap in the source to the author and keep it visible.

## Notation and mathematical prose

Rule 3 of SKILL.md governs new names; these rules govern the symbols you keep.

- Introduce a symbol where the reader first needs it, with its role in the same phrase: "the quotient map $q\colon X \to X/G$". A symbol used only in a proof is defined in the proof, not in the statement or the introduction.
- When a symbol returns in a later section, restate its role: "the conductor $N$", "the exceptional curves $E$".
- Keep existence, choice and uniqueness apart: "there is an isomorphism", "fix an isomorphism $\phi$", "the canonical isomorphism". When an identification uses a specific map, name the map.
- State quantifiers in the order the statement means them. For every constant in a bound, say what it depends on, or call it absolute; write "uniformly in $N$" when that is meant. When the source leaves the order or the dependence unclear, flag it to the author instead of choosing a reading.

Weak: "$d(n) \le C n^{\epsilon}$ for all $n$."
Better: "For every $\epsilon > 0$ there is $C_\epsilon$, depending only on $\epsilon$, such that $d(n) \le C_\epsilon n^{\epsilon}$ for all $n \ge 1$."

- "Since", "hence", "so", "equivalently", "respectively", "only", the articles and restrictive clauses carry logic. Change one only to change the logic. Each "respectively" pairs two lists of the same length, in the same order.
- Each formula and its prose must parse as one sentence read aloud. Put a word between adjacent formulas: "if $n > 1$, $n$ has a prime factor" becomes "if $n > 1$, then $n$ has a prime factor".

## Revising

When you revise mathematical text, yours or someone else's, compare the revision with the original for quantifiers, hypotheses, characteristic, genericity, signs, constants, normalizations, conditional status and exceptions. Each must match. When a hypothesis looks missing, report it to the author instead of inserting it. Restating an assumption the text already makes explicit elsewhere is fine.

Then run

    python3 <this directory>/scripts/preservation_check.py ORIGINAL REVISED

It lists changes between the two texts in formulas, citation keys, labels and references, and qualifier words. Each item is a question to check, not an order.

The checker treats each `%` not written `\%` as starting a LaTeX comment; in other formats, compare the rest of such lines by hand. For commands with several citation arguments, such as `\cites{a}{b}` or `\parencites[p. 3]{a}[p. 5]{b}`, it reads only the first argument; compare the other keys by hand.

Exit 0 means the comparison ran, including when differences were found; exit 2 means unreadable input or bad arguments.
