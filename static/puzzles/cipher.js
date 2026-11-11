import { addPrompt, element, textAnswer } from "./common.js?v=43";

export function render(root, puzzle, submit) {
  addPrompt(root, puzzle);
  root.append(element("pre", puzzle.encoded_text, "cipher-text"));
  textAnswer(root, submit);
}
