import { addPrompt, element } from "./common.js?v=43";

export function render(root, puzzle, submit) {
  addPrompt(root, puzzle);
  const form = document.createElement("form");
  const fieldset = document.createElement("fieldset");
  const legend = element("legend", "Select every correct answer");

  fieldset.append(legend);
  for (const [index, optionText] of puzzle.options.entries()) {
    const label = element("label", undefined, "pick-all-option");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = optionText;
    checkbox.id = `pick-all-option-${index}`;
    label.htmlFor = checkbox.id;
    label.append(checkbox, element("span", optionText));
    fieldset.append(label);
  }

  const button = element("button", "Check answers");
  button.type = "submit";
  form.append(fieldset, button);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const selected = [...fieldset.querySelectorAll('input[type="checkbox"]:checked')]
      .map((checkbox) => checkbox.value);
    if (selected.length) {
      submit(selected);
    }
  });
  root.append(form);
}
