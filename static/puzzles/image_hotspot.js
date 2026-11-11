import { element } from "./common.js?v=43";

export function render(root, puzzle, submit) {
  root.append(element("p", puzzle.prompt || ""));
  if (puzzle.overlay_text) {
    root.append(element("p", puzzle.overlay_text, "puzzle-overlay"));
  }
  root.append(element("p", "Click the hidden target in the image."));
  const button = document.createElement("button");
  button.type = "button";
  button.className = "hotspot-image-button";
  button.setAttribute("aria-label", "Select a location in the puzzle image");
  const image = document.createElement("img");
  image.src = puzzle.image_url;
  image.alt = puzzle.overlay_text || puzzle.title;
  image.className = "puzzle-image";
  button.append(image);
  button.addEventListener("click", (event) => {
    const bounds = image.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width) * 100;
    const y = ((event.clientY - bounds.top) / bounds.height) * 100;
    submit({ x, y });
  });
  root.append(button);
}
