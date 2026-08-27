---
name: "csv-report"
description: "Builds a tidy CSV summary from a dataframe, with one row per column of the source"
license: "Apache-2.0"
metadata:
  author: "acme"
  version: "1.0.0"
allowed-tools: ["python", "read"]
---

# CSV Report Skill

## When to Use

When the user asks for a summary of a tabular dataset.

## Usage

Call `scripts/summarize.py` with the dataset path.
