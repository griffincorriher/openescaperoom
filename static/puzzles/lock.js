import { addPrompt, element } from "./common.js?v=43";

export function render(root, puzzle, submit) {
  addPrompt(root, puzzle);

  const patterns = {
    digits: { inputMode: "numeric", pattern: "[0-9]", character: /^[0-9]$/ },
    letters: { pattern: "[A-Za-z]", character: /^[A-Za-z]$/ },
    directions: { pattern: "[NESWnesw]", character: /^[NESW]$/i },
  };
  const settings = patterns[puzzle.format];
  if (!settings) {
    throw new Error(`Unsupported lock code format: ${puzzle.format}`);
  }

  root.append(
    element("p", `Enter the ${puzzle.length}-character ${puzzle.format} code.`),
  );

  const form = element("form", undefined, "lock-code-form");
  const inputsRow = element("div", undefined, "flex mb-2 lock-code-inputs");
  inputsRow.setAttribute("role", "group");
  inputsRow.setAttribute("aria-label", `${puzzle.format} lock code`);

  const inputs = Array.from({ length: puzzle.length }, (_, index) => {
    const id = `lock-code-${index + 1}`;
    const wrapper = document.createElement("div");
    const label = element("label", `Code character ${index + 1}`, "sr-only");
    label.htmlFor = id;
    const input = document.createElement("input");
    input.id = id;
    input.type = "text";
    input.maxLength = 1;
    input.required = true;
    input.autocomplete = "off";
    input.inputMode = settings.inputMode || "text";
    input.pattern = settings.pattern;
    input.setAttribute("data-focus-input-init", "");
    input.setAttribute(
      "aria-label",
      `Code character ${index + 1} of ${puzzle.length}`,
    );
    input.className =
      "block bg-neutral-secondary-medium border border-default-medium text-heading text-sm rounded-base focus:ring-brand focus:border-brand h-10 w-10 shadow-xs placeholder:text-body lock-code-input";

    if (index > 0) {
      input.dataset.focusInputPrev = `lock-code-${index}`;
    }
    if (index < puzzle.length - 1) {
      input.dataset.focusInputNext = `lock-code-${index + 2}`;
    }

    wrapper.append(label, input);
    inputsRow.append(wrapper);
    return input;
  });

  const helper = element(
    "p",
    `Enter the ${puzzle.length}-character code, then submit it.`,
    "mt-2.5 text-sm text-body",
  );
  const button = element("button", "Submit answer", "button button-primary");
  button.type = "submit";
  form.append(inputsRow, helper, button);

  inputs.forEach((input, index) => {
    input.addEventListener("input", () => {
      const character = input.value.toUpperCase();
      input.value = settings.character.test(character) ? character : "";
      if (input.value) {
        inputs[index + 1]?.focus();
      }
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        inputs[index - 1]?.focus();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        inputs[index + 1]?.focus();
      } else if (event.key === "Backspace" && !input.value) {
        inputs[index - 1]?.focus();
      }
    });
  });

  inputsRow.addEventListener("paste", (event) => {
    const startIndex = inputs.indexOf(event.target);
    if (startIndex < 0) {
      return;
    }
    const pasted = event.clipboardData
      .getData("text")
      .toUpperCase()
      .split("")
      .filter((character) => settings.character.test(character));
    if (pasted.length <= 1) {
      return;
    }

    event.preventDefault();
    pasted.slice(0, inputs.length - startIndex).forEach((character, offset) => {
      inputs[startIndex + offset].value = character;
    });
    inputs[Math.min(startIndex + pasted.length, inputs.length - 1)].focus();
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const emptyInput = inputs.find((input) => !input.value);
    if (emptyInput) {
      emptyInput.focus();
      return;
    }

    submit(inputs.map((input) => input.value).join(""));
    inputs.forEach((input) => {
      input.value = "";
    });
    inputs[0].focus();
  });

  root.append(form);
}
