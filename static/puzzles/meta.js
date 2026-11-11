import { addPrompt, element, textAnswer } from "./common.js?v=43";

export function render(root, puzzle, submit) {
  addPrompt(root, puzzle);
  const fragments = puzzle.collected_fragments || [];
  if (fragments.length) {
    const list = element("ul");
    for (const fragment of fragments) {
      list.append(element("li", `${fragment.title}: ${fragment.gives}`));
    }
    root.append(element("h4", "Clues your team has collected"), list);
  } else {
    root.append(element("p", "Your team has not collected any fragments yet."));
  }
  textAnswer(root, submit);
}
