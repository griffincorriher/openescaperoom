import { addPrompt, element, textAnswer } from "./common.js";

export function render(root, puzzle, submit) {
  addPrompt(root, puzzle);
  root.append(element("pre", puzzle.encoded_text, "cipher-text"));
  textAnswer(root, submit);
}
