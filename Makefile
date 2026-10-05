# Cheevos developer commands. Run `make help` for the list.

UV ?= uv
RUN := $(UV) run
RES ?= 640x480
SCALE ?= 2
SCREEN_RESOLUTIONS ?= 640x480 752x560 1280x720
# Walk-through of the real app on recorded fixtures (desktop fixture mode).
SCREEN_SCRIPT ?= shot:home,a,shot:profile,b,down,a,shot:games,select,shot:games_details,select,down,a,shot:game,down,a,shot:achievement,a,shot:screenshot,b,b,y,shot:options,b,b,b,down,a,shot:recent,b,down,a,shot:awards,a,down,a,shot:settings
SHELL_SCRIPTS := $(shell find app scripts -name '*.sh' 2>/dev/null)

.DEFAULT_GOAL := help
.PHONY: help sync pyui fmt lint conventions shellcheck typecheck test check run screens doc-screens package \
	deploy launch stop logs shot clean

help: ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-12s %s\n", $$1, $$2}'

sync: ## Install/refresh the dev environment (Python 3.10 + tools)
	$(UV) sync

pyui: ## Fetch PyUI and the SPRUCE theme into .spruceos/ (REF=<ref> for another commit)
	scripts/fetch_pyui.sh $(REF)

fmt: ## Format and auto-fix lint issues
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

lint: conventions shellcheck ## Formatting, lint, conventions and shell checks
	$(RUN) ruff format --check .
	$(RUN) ruff check .

conventions: ## Module size caps, docstrings on everything, layering rules
	$(RUN) python scripts/check_conventions.py

shellcheck: ## Check POSIX shell scripts (busybox ash on devices)
ifneq ($(strip $(SHELL_SCRIPTS)),)
	$(RUN) shellcheck -s sh $(SHELL_SCRIPTS)
else
	@echo "shellcheck: no shell scripts yet"
endif

typecheck: ## Type-check with ty
	$(RUN) ty check

test: ## Run the test suite with coverage
	$(RUN) pytest --cov --cov-report=term

check: lint typecheck test ## Everything CI runs

run: ## Desktop window: make run [RES=752x560] [SCALE=1]
	$(RUN) python -m cheevos.platform.desktop --res $(RES) --scale $(SCALE)

screens: ## Headless PNGs of the walk-through into build/screens/<WxH>/
	@for res in $(SCREEN_RESOLUTIONS); do \
		$(RUN) python -m cheevos.platform.desktop --headless --res $$res \
			--script "$(SCREEN_SCRIPT)" || exit 1; \
	done
	@echo "Screens written to build/screens/"

doc-screens: ## Render the wiki screenshots into docs/images (showcase drill)
	$(RUN) python scripts/doc_screens.py

package: ## Build the device package into dist/App/Cheevos
	$(RUN) python scripts/build_package.py

deploy: package ## Copy the package to the device (DEVICE_HOST=<ip> or DEVICE_SSH=...)
	scripts/device.sh deploy

launch: ## Start Cheevos on the device remotely
	scripts/device.sh launch

stop: ## Ask Cheevos on the device to exit
	scripts/device.sh stop

logs: ## Show the device log
	scripts/device.sh logs

shot: ## Save the device screen: make shot [OUT=build/device.png]
	scripts/device.sh shot $(or $(OUT),build/device.png)

clean: ## Remove build outputs and caches (keeps dev/sdcard)
	rm -rf build dist .pytest_cache .ruff_cache .coverage coverage.xml htmlcov
	find . -name __pycache__ -type d -not -path './.spruceos/*' -not -path './.venv/*' \
		-exec rm -rf {} +
