#!/usr/bin/env python3
"""Run from a source checkout without installing the package."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
# Child interpreters need the same source path.
import os
os.environ['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
from relay_timing_lab.messaging.demo import demo

demo()
