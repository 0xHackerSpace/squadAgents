---
name: "Beta"
vendorKey: "acme"
agentKey: "beta"
version: "1.0.0"
slug: "acme/beta"
description: "Second half of a deliberate delegation cycle used to test cycle detection here"
author: "@acme"
license: "MIT"
tags: ["test"]
agents:
  - vendor: "acme"
    agent: "alpha"
    version: "1.0.0"
    role: "partner"
    required: true
---

# Agent Purpose

## Core Responsibilities
- delegate back to alpha
