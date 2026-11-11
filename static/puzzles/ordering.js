import { addPrompt, element } from "./common.js?v=43";

export function render(root, puzzle, submit) {
  addPrompt(root, puzzle);
  const items = [...puzzle.items];
  const list = element("ol");
  const drawItems = () => {
    list.replaceChildren();
    items.forEach((item, index) => {
      const row = element("li", undefined, "ordering-row");
      row.append(element("span", item));
      for (const [label, offset] of [["Move up", -1], ["Move down", 1]]) {
        const button = element("button", label);
        button.type = "button";
        button.disabled = index + offset < 0 || index + offset >= items.length;
        button.addEventListener("click", () => {
          const [moved] = items.splice(index, 1);
          items.splice(index + offset, 0, moved);
          drawItems();
        });
        row.append(button);
      }
      list.append(row);
    });
  };
  drawItems();
  const button = element("button", "Check order");
  button.type = "button";
  button.addEventListener("click", () => submit([...items]));
  root.append(list, button);
}
