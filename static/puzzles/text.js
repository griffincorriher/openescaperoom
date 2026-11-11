import { addPrompt, textAnswer } from "./common.js?v=43";

export function render(root, puzzle, submit) {
  addPrompt(root, puzzle);
  textAnswer(root, submit);
}
