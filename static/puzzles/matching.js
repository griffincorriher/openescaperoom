import { addPrompt, element } from "./common.js?v=43";

export function render(root, puzzle, submit) {
  addPrompt(root, puzzle);
  const form = document.createElement("form");
  const rows = [];
  const choices = [...puzzle.right];
  const selections = new Set();
  const heading = element("h3", "Match each item");
  const list = element("ol", undefined, "matching-list");

  const updateChoices = () => {
    selections.clear();
    for (const select of rows) {
      if (select.value) {
        selections.add(select.value);
      }
    }
    for (const select of rows) {
      for (const option of select.options) {
        if (option.value) {
          option.disabled =
            option.value !== select.value && selections.has(option.value);
        }
      }
    }
  };

  for (const [index, item] of puzzle.left.entries()) {
    const row = element("li", undefined, "matching-row");
    const label = element("label", item);
    const select = document.createElement("select");
    select.required = true;
    select.setAttribute("aria-label", `Match for ${item}`);
    const placeholder = element("option", "Choose a match");
    placeholder.value = "";
    placeholder.disabled = true;
    placeholder.selected = true;
    select.append(placeholder);
    for (const choice of choices) {
      const option = element("option", choice);
      option.value = choice;
      select.append(option);
    }
    label.htmlFor = `matching-answer-${index}`;
    select.id = `matching-answer-${index}`;
    rows.push(select);
    select.addEventListener("change", updateChoices);
    row.append(label, select);
    list.append(row);
  }

  const button = element("button", "Check matches");
  button.type = "submit";
  form.append(heading, list, button);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (form.reportValidity()) {
      submit(rows.map((select) => select.value));
    }
  });
  root.append(form);
}
