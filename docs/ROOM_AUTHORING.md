# Room authoring kit

Copilot (or any chat AI) writes the room; the author makes the images and zips it. Image tools can't reliably bundle images into a zip with the right filenames, so the flow has two halves.

## How it works

1. **Pick a theme.** Fill in the four blanks at the top of the prompt below (theme, difficulty, minutes, team size).
2. **Paste the prompt into Copilot.** It returns `room.yaml`, an image list (exact filename + image prompt for each), and `HOST_GUIDE.md` with the full solution.
3. **Generate the images.** Ask for each image on the list, one at a time. Save each with the exact filename from the list.
4. **Assemble the folder.** `room.yaml` and `HOST_GUIDE.md` at the top level, images in `assets/`.
5. **Zip and upload** (if uploads are enabled), or commit the folder to `rooms/` in the repo.
6. **Playtest** solo with answers visible, then mark it ready.

## Room package spec

### Folder layout

```
haunted-mansion/
├── room.yaml        # the whole room: story, puzzles, answers, hints
├── HOST_GUIDE.md    # solution walkthrough for the game master
└── assets/
    ├── cover.png    # room picker thumbnail
    ├── intro.png
    ├── library.png
    └── ...
```

### room.yaml

```yaml
meta:
  id: haunted-mansion            # lowercase, hyphens, matches folder name
  title: "The Haunted Mansion"
  author: "Priya"
  difficulty: medium              # easy | medium | hard
  est_minutes: 30
  team_size: "3-6"
  tags: [spooky, halloween]
  cover: assets/cover.png

settings:
  time_limit_min: 30
  hint_penalty_sec: 60            # time added per hint used
  wrong_answer_cooldown_sec: 5    # stops brute-forcing locks

story:
  intro: "The door slams behind you. The candles flicker..."
  intro_image: assets/intro.png
  outro: "The front door creaks open. You're free."
  outro_image: assets/outro.png

puzzles:
  - id: library
    title: "The Dusty Library"
    prestory: "Dust swirls as you step into the library. The cellar key is hidden somewhere in this room, and you can hear footsteps upstairs."  # scene + goal, never a clue; shown over the puzzle image when it unlocks
    type: lock
    format: digits                # digits | letters | directions
    length: 4
    prompt: "Four books are pulled halfway out. Their spines read..."
    image: assets/library.png
    overlay_text: "VOL. VII   VOL. II   VOL. IX   VOL. IV"
    requires: []                  # empty = open at start
    answer: "7294"
    hints:
      - "The spines aren't decoration."
      - "Roman numerals, left to right."
      - "VII, II, IX, IV."
    solve_text: "A click. The bookcase swings open."
    gives: "G"                    # optional: fragment for the final meta puzzle
```

### Puzzle types

| Type | Players see | Extra fields |
| --- | --- | --- |
| `text` | A prompt and a free-text box | `answers` (list of accepted answers) |
| `multiple_choice` | 3–5 options | `options`, `answer` |
| `lock` | A combination dial | `format`, `length`, `answer` |
| `split_clue` | Each player sees a different fragment | `fragments` (list, dealt round-robin to teammates), `answer` |
| `cipher` | Scrambled text the engine encodes | `method` (caesar, atbash, reverse), `shift`, `plaintext`, `answer` |
| `ordering` | Items to drag into order | `items` (listed in the correct order; engine shuffles them) |
| `image_hotspot` | Click the right spot on an image | `regions` (x, y, w, h as % of image; set after the image exists) |
| `meta` | The final puzzle, built from earlier `gives` | `answer`; must require every puzzle that has `gives` |

### Rules the validator checks

- Every `id` is unique, lowercase, and uses hyphens only.
- Every `requires` entry points to a real puzzle id, and there are no loops.
- At least one puzzle has `requires: []`, and exactly one puzzle is `type: meta`.
- Every image path exists in `assets/`. Images are PNG, JPG, or WEBP, each under 5 MB; the zip is under 50 MB.
- Every puzzle has a prestory under 50 words that doesn't contain its own answer, and 2–3 hints ordered from vague to nearly the answer.
- Answers are matched case-insensitively, ignoring spaces and punctuation, so `"Ghost Story"` matches `ghoststory`.

## The Copilot prompt

Copy the block below into Copilot and fill in the four lines under ROOM REQUEST.

```text
You are an escape room designer. Design a complete online escape room for a team game engine. Follow the format and rules below exactly; the engine rejects rooms that break them.

ROOM REQUEST
- Theme: [e.g. heist on a luxury train, haunted mansion, space station oxygen leak]
- Difficulty: [easy | medium | hard]
- Time limit (minutes): [e.g. 30]
- Team size: [e.g. 3-6]

DESIGN RULES
1. 6 to 9 puzzles total, each solvable in 2 to 5 minutes.
2. Puzzles form a graph, not a single line. At least 2 puzzles are open at the start, and there are at least 2 branches teams can work on in parallel.
3. Use at least 4 different puzzle types. Include at least one split_clue puzzle so teammates must talk to each other.
4. The last puzzle is type meta. Every other puzzle with a "gives" field feeds it a fragment (a letter, number or word), and the fragments combine into the final answer.
5. Every answer must be solvable from the prompt, overlay_text, fragments or options alone. Never require outside knowledge beyond common facts (days of the week, Roman numerals, basic math).
6. NEVER put clue text, numbers or symbols inside an image. Image generators misspell text. Put any text players must read in overlay_text (the engine draws it on the image) or in the prompt.
7. Images set the mood and show objects; they are never the only source of a clue.
8. Each puzzle has exactly 3 hints: vague, specific, nearly the answer.
9. Write in a fun, vivid voice. Keep each prompt under 60 words.
10. Keep the story consistent: intro sets the stakes, each prestory sets the scene, each solve_text moves the story forward, outro pays it off.
11. Every puzzle has a prestory (under 50 words), shown as its own slide when the puzzle unlocks. It describes where the team is and what they are trying to do (open the safe, find the password). It NEVER contains clue content, answer fragments, numbers the puzzle uses, or hint wording.

PUZZLE TYPES (use only these)
- text: free-text answer. Fields: answers (list of accepted spellings)
- multiple_choice: Fields: options (3-5), answer
- lock: Fields: format (digits | letters | directions), length, answer
- split_clue: each teammate sees one fragment. Fields: fragments (3-4 items, each useless alone), answer
- cipher: engine encodes the text. Fields: method (caesar | atbash | reverse), shift (caesar only), plaintext, answer
- ordering: drag items into order. Fields: items (written in the CORRECT order), answer: "ordered"
- meta: final puzzle. Fields: answer. Its requires lists every puzzle with a gives field.
Do not use image_hotspot.

OUTPUT: produce exactly these 4 parts, in this order.

PART 1 - room.yaml in a single yaml code block, using this structure:
meta:
  id: <lowercase-hyphenated-title>
  title: "<room name>"
  author: "<leave as AUTHOR>"
  difficulty: <difficulty>
  est_minutes: <minutes>
  team_size: "<team size>"
  tags: [<2-3 tags>]
  cover: assets/cover.png
settings:
  time_limit_min: <minutes>
  hint_penalty_sec: 60
  wrong_answer_cooldown_sec: 5
story:
  intro: "<2-3 sentences>"
  intro_image: assets/intro.png
  outro: "<1-2 sentences>"
  outro_image: assets/outro.png
puzzles:
  - id: <lowercase-hyphenated>
    title: "<short title>"
    prestory: "<1-3 sentences: the scene and the goal, no clues>"
    type: <type>
    prompt: "<what players read>"
    image: assets/<id>.png
    overlay_text: "<optional: text drawn on the image>"
    requires: [<ids that must be solved first, or empty>]
    <type-specific fields>
    answer: "<answer>"
    hints: ["<vague>", "<specific>", "<nearly the answer>"]
    solve_text: "<one sentence story beat>"
    gives: "<optional fragment for the meta puzzle>"

PART 2 - Image list as a table with columns: Filename | Image prompt.
Include cover.png, intro.png, outro.png, and one image per puzzle named <puzzle id>.png.
Start every image prompt with the same style line, written once for this room (for example "Moody digital painting, warm candlelight, cinematic, no text, no letters, no numbers"), so all images match.

PART 3 - HOST_GUIDE.md in a markdown code block: a one-paragraph premise, a text diagram of which puzzles unlock which, then each puzzle in order with its answer and a one-line explanation of how to solve it.

PART 4 - Self-check. Confirm each item as a checklist: every requires id exists; no loops; 2+ puzzles open at start; exactly one meta puzzle; every gives fragment appears in the meta answer logic; no clue depends on text inside an image; every puzzle has 3 hints; every prestory states a goal and contains no clue.

If you can run Python, also create a zip named <room id>.zip containing room.yaml, HOST_GUIDE.md and an empty assets/ folder, and tell me which image files I still need to add.
```

Image follow-up, one per message:

```text
Generate the image for <filename> using its prompt from the image list. Landscape, 16:9. No text, letters or numbers anywhere in the image.
```

## Image tips

- **Use `overlay_text` for anything players must read.** The engine draws it on the image in a clean font.
- **Check counts and colors.** If a puzzle depends on something in an image, generate it, check it yourself, and fix the answer to match.
- **Keep one style line** at the start of every image prompt so the room looks consistent.
- **Name files exactly.** `library.png`, not `library (1).png` or `Library.PNG`.
- **16:9 landscape**, under 5 MB each.
- **Hotspot puzzles are manual.** Add `image_hotspot` puzzles yourself after the image exists.

## Pre-upload checklist

- [ ] Replaced `AUTHOR` with your name in `room.yaml`
- [ ] Every filename in the image list exists in `assets/`, spelled exactly
- [ ] Checked anything in an image that an answer depends on
- [ ] Solved every puzzle yourself using only what players will see
- [ ] Hints read in order; the third nearly gives the answer away
- [ ] `HOST_GUIDE.md` matches the final answers
- [ ] Zipped the folder itself, so `room.yaml` sits at the top of the zip
- [ ] Uploaded (or committed to `rooms/`), fixed validator warnings, playtested once
