import { addPrompt, element, textAnswer } from "./common.js";

export function render(root, puzzle, submit) {
  addPrompt(root, puzzle);
  root.append(element("p", `Your private clue: ${puzzle.fragment}`, "private-clue"));
  textAnswer(root, submit);
}
