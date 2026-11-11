import { addPrompt, element, textAnswer } from "./common.js";

export function render(root, puzzle, submit) {
  addPrompt(root, puzzle);
  const settings = {
    digits: { inputMode: "numeric", pattern: "[0-9]*" },
    letters: { pattern: "[A-Za-z]*" },
    directions: { pattern: "[NESWnesw]*" },
  }[puzzle.format] || {};
  root.append(
    element("p", `Enter the ${puzzle.length}-character ${puzzle.format} code.`),
  );
  textAnswer(root, submit, {
    ...settings,
    maxLength: puzzle.length,
    label: `${puzzle.format} lock code`,
  });
}
