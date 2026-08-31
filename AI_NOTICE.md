# AI Development Notice

This project contains source code generated with the assistance of
**ChatGPT**, using **GPT-5.6 Sol**, an AI model developed by **OpenAI**.

## Role of AI

ChatGPT was used to generate and revise portions of the source code,
documentation, tests, and supporting project files.

The AI did not independently define the purpose, architecture, requirements,
or acceptance criteria for this project.

## Human Architectural Direction

The project was developed under the architectural and technical direction of
the project maintainer.

Human direction included, among other things:

- Defining the purpose and scope of the application.
- Choosing Python and a terminal-based `curses` interface.
- Requiring JSONL-only parsing of Mercury HF logs.
- Rejecting legacy text-log and regular-expression parsing approaches.
- Defining the session-selection workflow and report layout.
- Determining which Mercury HF metrics should be exposed.
- Requiring verification against real Mercury HF session logs.
- Directing the interpretation of session boundaries, byte counters, frame
  counters, retries, adaptive mode transitions, and peer-side mode requests.
- Requiring Mercury HF and FreeDV documentation to be consulted when mapping
  internal mode IDs to DATAC modes.
- Reviewing generated output and directing iterative corrections.

## Verification and Responsibility

AI-generated code can contain errors. The generated implementation has been
reviewed iteratively against real Mercury HF logs and project-specific tests,
but users should independently validate the software for their own use case.

The project maintainer remains responsible for the architecture, integration,
release decisions, and final acceptance of the code included in this
repository.

## About the AI System

**ChatGPT** is an AI assistant provided by **OpenAI**.

For this project, the assistant identified itself as:

- Product: ChatGPT
- Model: GPT-5.6 Sol
- Developer: OpenAI

The model generated code and documentation in response to human-provided
requirements, examples, corrections, and architectural decisions. It did not
operate autonomously outside that interaction.

## Transparency

This notice is included to make the development process clear to users and
contributors: **the implementation was AI-generated under human architectural
direction and review.**
