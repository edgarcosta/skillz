This is a code audit. In addition to the fields above, every candidate carries:

- changed location: the file and line in the patch that introduces the defect;
- diff causality: why this hunk, not surrounding code, causes it;
- severity, on this scale: high means security, data loss or corruption, or a wrong result; medium means incorrect behaviour on a reachable input the change did not intend, with bounded impact; low means correct but misleading or fragile. An instruction finding takes the severity of the consequence its rule states, and medium when the rule states none;
- for an instruction finding: the exact rule citation, the rule's path scope, and why it applies at the changed location.

Beyond the shared rejects, do not raise:

- pre-existing defects and findings outside changed behaviour;
- missing tests or documentation without a demonstrated defect, unless a rule handed to you requires them;
- issues ordinary tooling would settle, unless the finding identifies the concrete resulting behaviour;
- intended behaviour merely because it differs from the previous implementation.
