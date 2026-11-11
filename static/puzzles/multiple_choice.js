import { addPrompt, element } from "./common.js";

export function render(root, puzzle, submit) {
  addPrompt(root, puzzle);
  const form = document.createElement("form");
  const select = document.createElement("select");
  select.required = true;
  select.setAttribute("aria-label", "Choose an answer");
  const placeholder = element("option", "Choose an answer");
  placeholder.value = "";
  placeholder.disabled = true;
  placeholder.selected = true;
  select.append(placeholder);
  for (const choice of puzzle.options) {
    const option = element("option", choice);
    option.value = choice;
    select.append(option);
  }
  const button = element("button", "Submit answer");
  button.type = "submit";
  form.append(select, button);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (select.value) {
      submit(select.value);
    }
  });
  root.append(form);
}
