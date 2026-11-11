export function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) {
    node.textContent = text;
  }
  if (className) {
    node.className = className;
  }
  return node;
}

export function addPrompt(root, puzzle) {
  if (puzzle.image_url) {
    const image = document.createElement("img");
    image.src = puzzle.image_url;
    image.alt = puzzle.overlay_text || puzzle.title;
    image.className = "puzzle-image";
    root.append(image);
  }
  if (puzzle.overlay_text) {
    root.append(element("p", puzzle.overlay_text, "puzzle-overlay"));
  }
  root.append(element("p", puzzle.prompt || ""));
}

export function textAnswer(root, submit, options = {}) {
  const form = document.createElement("form");
  const input = document.createElement("input");
  input.type = "text";
  input.autocomplete = "off";
  input.required = true;
  input.maxLength = options.maxLength || 512;
  input.setAttribute("aria-label", options.label || "Your answer");
  if (options.inputMode) {
    input.inputMode = options.inputMode;
  }
  if (options.pattern) {
    input.pattern = options.pattern;
  }
  const button = element("button", options.buttonLabel || "Submit answer");
  button.type = "submit";
  form.append(input, button);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submit(input.value);
    input.value = "";
  });
  root.append(form);
}
