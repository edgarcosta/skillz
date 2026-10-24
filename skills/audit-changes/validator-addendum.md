This is a code audit. Severity uses the scale: high means security, data loss or corruption, or a wrong result; medium means incorrect behaviour on a reachable input the change did not intend, with bounded impact; low means correct but misleading or fragile. An instruction finding takes the severity of the consequence its rule states, and medium when the rule states none.

An instruction validator rereads the exact cited rule and verifies its path scope applies at the changed location.

A math validator verifies the domain, the derivation or source, the witness or proof sketch, the expected result, and diff causality.
