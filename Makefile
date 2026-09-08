.PHONY: setup test validate cases app report clean

VENV := .venv
ifeq ($(OS),Windows_NT)
  PY := $(VENV)/Scripts/python.exe
else
  PY := $(VENV)/bin/python
endif

setup:
	python -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"

test:
	$(PY) -m pytest tests/unit -q

validate:
	$(PY) scripts/validate.py

cases:
	$(PY) scripts/reproduce_cases.py

app:
	$(PY) -m streamlit run app/main.py

report:
	$(PY) scripts/build_report.py

clean:
	rm -rf $(VENV) evidence/*.json cases/*/results
