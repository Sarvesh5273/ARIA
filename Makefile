# ARIA — project tasks.
#
# `make check` is the one to run before committing: it proves the suite is green
# AND that handoff_bundle/specs/ still matches .kiro/specs/.

# Prefer the project venv when it exists; fall back to the system interpreter.
PYTHON ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

.DEFAULT_GOAL := help
.PHONY: help bundle check-bundle test check selftest preflight

help:
	@echo "make test          run the pytest suite"
	@echo "make bundle        regenerate handoff_bundle/specs/ from .kiro/specs/"
	@echo "make check-bundle  verify the bundle is in sync (writes nothing)"
	@echo "make check         test + check-bundle — run this before committing"
	@echo "make selftest      state_manager smoke check (module form, not by path)"
	@echo "make preflight     what audio + visual would need on this machine"
	@echo ""
	@echo "Diagnostics — need a live backend, take minutes, NOT part of 'check':"
	@echo "  $(PYTHON) tools/observe_dmn_pass.py         watch a real 8-minute idle pass"
	@echo "  $(PYTHON) tools/compare_local_models.py     A/B local voices on gate metrics"
	@echo ""
	@echo "PYTHON=$(PYTHON)"

# Answers "can she speak / can she see yet" without constructing anything or
# needing a model backend. Cheap enough to be part of help rather than a doc.
preflight:
	$(PYTHON) main.py --audio-preflight
	$(PYTHON) main.py --visual-preflight

test:
	$(PYTHON) -m pytest tests/ -q

# handoff_bundle/specs/spec_*.md is GENERATED. Edit .kiro/specs/<module>/ or
# handoff_bundle/spec_headers/<module>.md, then run this. Never hand-edit output.
bundle:
	$(PYTHON) tools/build_handoff_bundle.py

check-bundle:
	$(PYTHON) tools/build_handoff_bundle.py --check

# Deliberately not a dependency of `test`: the suite stays fast and hermetic.
check: test check-bundle

# Must be the module form. By-path invocation puts daemon/ on sys.path, where
# daemon/types.py shadows the stdlib `types` module and the import fails.
selftest:
	$(PYTHON) -m daemon.state_manager
