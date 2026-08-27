---
name: "Alpha"
vendorKey: "acme"
agentKey: "alpha"
version: "1.0.0"
slug: "acme/alpha"
description: "First half of a deliberate delegation cycle used to test cycle detection here"
author: "@acme"
license: "MIT"
tags: ["test"]
agents:
  - vendor: "acme"
    agent: "beta"
    version: "1.0.0"
    role: "partner"
    required: true
---

# Agent Purpose

## Core Responsibilities
- delegate to beta
