window.mermaidConfig = {
  startOnLoad: false,
  securityLevel: "loose",
  theme: document.body.dataset.mdColorScheme === "slate" ? "dark" : "default",
};

mermaid.initialize(window.mermaidConfig);

function renderMermaid() {
  const theme = document.body.dataset.mdColorScheme === "slate" ? "dark" : "default";
  mermaid.initialize({ ...window.mermaidConfig, theme });
  mermaid.run({ querySelector: ".mermaid" });
}

document$.subscribe(renderMermaid);
