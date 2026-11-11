import { addPrompt, textAnswer } from "./common.js";

export function render(root, puzzle, submit) {
  addPrompt(root, puzzle);
  textAnswer(root, submit);
}
