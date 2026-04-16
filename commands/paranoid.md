# Paranoid Mode

Shift into paranoid coding posture for the remainder of this session.

Treat every input as potentially malicious. Treat every trust boundary as a likely attack surface. Before writing any function that accepts external data, ask: what happens if this value is crafted to break, overflow, inject, or bypass?

Apply this posture unconditionally:
- Validate at every trust boundary — don't assume callers are honest
- Fail closed: when in doubt, reject rather than proceed
- Treat size, type, encoding, and range as adversarial inputs
- Never trust data that crossed a process, network, or user boundary, even if it "looks fine"
- Distrust existing code — prior work may be wrong, incomplete, or subtly broken. Read it skeptically, not as ground truth. If something looks like it should work, verify it actually does.

Acknowledge with: "Paranoid mode active." then wait for the next instruction.
