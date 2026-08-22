"""Concrete adapters for the Protocols the soul layer declares and injects.

WHY THIS IS A SEPARATE PACKAGE FROM `daemon/`
---------------------------------------------
`daemon/` is the soul: thirteen modules, zero external dependencies, every
boundary an injected Protocol. That property is what makes the suite hermetic
and what keeps the module-boundary guarantees checkable. Concrete providers
(Ollama, an embedding backend, audio, video) live HERE so the dependency arrow
only ever points one way:

    adapters  ->  daemon        (adapters import Protocols from daemon)
    daemon    -/->  adapters    (never; nothing in daemon imports this package)

Nothing in this package is in the precedence chain, decides anything, or holds
soul state. An adapter translates a provider's shape into a Protocol's shape and
translates provider failures into the error the Protocol names. That is all.

v4's "Directory Structure (Updated Conv.6)" lists everything under `daemon/`
(`llm_manager.py`, `stt_engine.py`, `tts_manager.py`, ...). That layout is
already superseded by the shipped code — none of those files exist, their
responsibilities were consolidated differently, and the Protocol-injection
architecture the code actually uses postdates it. So this is a build-layout
choice, not a spec deviation. Flagged rather than assumed.
"""
