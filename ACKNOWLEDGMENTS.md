# Acknowledgments

stdraw's interaction layer and quality-gate philosophy draw on several open-source
diagramming projects. We studied how they implement and verify direct-manipulation
interactions, and calibrated our own decisions against their production evidence.
Thank you — this project stands on your shoulders.

| Project | What we learned from it |
|---|---|
| **[bpmn-io/diagram-js](https://github.com/bpmn-io/diagram-js)** & **[bpmn-js](https://github.com/bpmn-io/bpmn-js)** | Hit-layer design: interaction paths with **painted stroke** (`stroke:'white'`, `strokeWidth:15`) + CSS `pointer-events:stroke` — a decade of production proof that shaped our fix for transparent-stroke hit-testing; bendpoint / segment-dragger interaction patterns; drag-preview-then-commit UX. |
| **[jgraph/drawio](https://github.com/jgraph/drawio)** (mxGraph) | Drag-a-segment-inserts-two-bendpoints interaction (candidate for our 0.7.9+ line dragging); container-level event routing with engine-owned geometric hit testing — our reference for the "own your hit-testing" upgrade path. |
| **[xyflow/xyflow](https://github.com/xyflow/xyflow)** (React Flow) | Constrained endpoint reconnection (handles, `onReconnect`) and commit-on-drop previews — anchors-over-freedom for edge editing. |
| **[cytoscape/cytoscape.js](https://github.com/cytoscape/cytoscape.js)** | Canvas-rendered hit-testing as pure geometry, testable without browser hit-layer quirks; real-browser (Cypress) e2e for interactions. |
| **[W3C aria-practices](https://github.com/w3c/aria-practices)** & **[AFixt/apg-gherkin](https://github.com/AFixt/apg-gherkin)** | Keyboard/focus/state acceptance criteria for interactive widgets, in scenario form — the bar our interactive layer is held to. |

Our internal comparison and the lessons distilled from these projects live in
`docs/` and our agent skills; where we adopted a pattern, the credit is theirs
and the mistakes are ours. All referenced projects are MIT or W3C-documented
standards — thank you for licensing generosity.
