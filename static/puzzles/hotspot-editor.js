import { isHotspotHit, validateHotspot, formatPercent } from "./hotspot.js?v=43";

const MIN_DRAW_SIZE = 0.5;
const editorStates = new WeakMap();

function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined) {
    result.textContent = text;
  }
  if (className) {
    result.className = className;
  }
  return result;
}

function cleanRegions(regions) {
  if (!Array.isArray(regions)) {
    return [];
  }
  return regions
    .filter((region) => region && typeof region === "object")
    .map((region) => ({
      x: Number.isFinite(region.x) ? clamp(region.x) : 0,
      y: Number.isFinite(region.y) ? clamp(region.y) : 0,
      w: Number.isFinite(region.w) ? clamp(region.w) : 0,
      h: Number.isFinite(region.h) ? clamp(region.h) : 0,
    }));
}

function clamp(value) {
  return Math.max(0, Math.min(100, value));
}

function pointOnImage(event, image) {
  const bounds = image.getBoundingClientRect();
  return {
    x: clamp(((event.clientX - bounds.left) / bounds.width) * 100),
    y: clamp(((event.clientY - bounds.top) / bounds.height) * 100),
  };
}

function renderPuzzle(puzzle) {
  const panel = node("article", undefined, "hotspot-editor-panel");
  panel.tabIndex = 0;
  panel.append(
    node("h4", `${puzzle.id} — ${puzzle.title}`, "hotspot-editor-title"),
  );
  if (puzzle.prompt) {
    panel.append(node("p", puzzle.prompt, "hotspot-editor-prompt"));
  }
  const regions = cleanRegions(puzzle.regions);
  const initialRegions = regions.map((region) => ({ ...region }));
  let tolerance = Number.isFinite(puzzle.tolerance) ? puzzle.tolerance : 0;
  const initialTolerance = tolerance;
  let selectedIndex = -1;
  let testMode = false;
  let edited = false;
  let interaction;

  const imageStatus = node("p", "", "hotspot-editor-status");
  const serverErrors = (puzzle.errors || []).filter(
    (message) => !/\.regions(?:\[| )|\.tolerance/.test(message),
  );
  const serverRegionErrors = (puzzle.errors || []).filter((message) =>
    /\.regions(?:\[| )|\.tolerance/.test(message),
  );
  const serverWarnings = (puzzle.warnings || []).filter(
    (message) => !/\.regions(?:\[| )| regions cover /.test(message),
  );
  const serverRegionWarnings = (puzzle.warnings || []).filter((message) =>
    /\.regions(?:\[| )| regions cover /.test(message),
  );
  const diagnostics = node("div", undefined, "hotspot-editor-diagnostics");
  const surface = node("div", undefined, "hotspot-editor-surface");
  const image = document.createElement("img");
  image.className = "hotspot-editor-image";
  image.alt = puzzle.title || `Image for ${puzzle.id}`;
  const overlay = node("div", undefined, "hotspot-editor-overlay");
  surface.append(image, overlay);

  const controls = node("div", undefined, "hotspot-editor-controls");
  const testToggle = node("button", "Test clicks", "button button-secondary");
  testToggle.type = "button";
  testToggle.setAttribute("aria-pressed", "false");
  const toleranceLabel = node("label", "Tolerance (%)", "hotspot-tolerance-label");
  const toleranceInput = document.createElement("input");
  toleranceInput.type = "number";
  toleranceInput.min = "0";
  toleranceInput.max = "10";
  toleranceInput.step = "0.1";
  toleranceInput.value = String(tolerance);
  toleranceInput.setAttribute("aria-label", `Tolerance for ${puzzle.id}`);
  const deleteButton = node("button", "Delete region", "button button-secondary");
  deleteButton.type = "button";
  deleteButton.disabled = selectedIndex < 0;
  const revertButton = node("button", "Revert", "button button-secondary");
  revertButton.type = "button";
  toleranceLabel.append(toleranceInput);
  controls.append(testToggle, toleranceLabel, deleteButton, revertButton);

  const instruction = node(
    "p",
    "Drag on the image to draw a region. Drag a region to move it or use its corner handles to resize it.",
    "hotspot-editor-instruction",
  );
  if (puzzle.image_data_url) {
    image.src = puzzle.image_data_url;
  } else {
    surface.hidden = true;
    imageStatus.textContent =
      "Image preview is unavailable. Check that the image path exists and is a supported image.";
  }

  function showDiagnostics() {
    const result = validateHotspot(regions, tolerance);
    diagnostics.replaceChildren();
    const errors = [
      ...serverErrors,
      ...(edited ? result.errors : serverRegionErrors),
    ];
    const warnings = [
      ...serverWarnings,
      ...(edited ? result.warnings : serverRegionWarnings),
    ];
    if (errors.length || warnings.length) {
      const list = node("ul", undefined, "hotspot-editor-message-list");
      for (const message of errors) {
        list.append(node("li", message, "hotspot-message-error"));
      }
      for (const message of warnings) {
        list.append(node("li", message, "hotspot-message-warning"));
      }
      diagnostics.append(list);
    } else {
      diagnostics.append(
        node("p", "Regions look good.", "hotspot-message-success"),
      );
    }
    renderRegions(errors, warnings);
  }

  function renderRegions(errors, warnings) {
    overlay.replaceChildren();
    regions.forEach((region, index) => {
      const box = node("div", String(index + 1), "hotspot-region");
      box.dataset.hotspotRegion = String(index);
      box.style.left = `${region.x}%`;
      box.style.top = `${region.y}%`;
      box.style.width = `${region.w}%`;
      box.style.height = `${region.h}%`;
      if (
        errors.some(
          (message) =>
            message.includes(`regions[${index}]`) ||
            message.includes(`Region ${index + 1}`),
        )
      ) {
        box.classList.add("has-error");
      } else if (
        warnings.some(
          (message) =>
            message.includes(`regions[${index}]`) ||
            message.includes(`Region ${index + 1}`),
        )
      ) {
        box.classList.add("has-warning");
      }
      if (index === selectedIndex) {
        box.classList.add("is-selected");
      }

      if (tolerance > 0) {
        const padded = node("span", undefined, "hotspot-region-padding");
        padded.style.left = `${Math.max(0, region.x - tolerance)}%`;
        padded.style.top = `${Math.max(0, region.y - tolerance)}%`;
        padded.style.width = `${
          Math.min(100, region.x + region.w + tolerance) -
          Math.max(0, region.x - tolerance)
        }%`;
        padded.style.height = `${
          Math.min(100, region.y + region.h + tolerance) -
          Math.max(0, region.y - tolerance)
        }%`;
        overlay.append(padded);
      }

      for (const corner of ["nw", "ne", "sw", "se"]) {
        const handle = node("span", undefined, `hotspot-region-handle is-${corner}`);
        handle.dataset.hotspotHandle = corner;
        handle.dataset.hotspotRegionIndex = String(index);
        box.append(handle);
      }
      overlay.append(box);
    });
    deleteButton.disabled = selectedIndex < 0 || selectedIndex >= regions.length;
  }

  function markTestResult(point) {
    const result = isHotspotHit(regions, tolerance, point.x, point.y);
    const formattedPoint = `(${formatPercent(point.x)}%, ${formatPercent(point.y)}%)`;
    imageStatus.textContent = result.hit
      ? `Correct: inside region ${result.regionIndex + 1} ${formattedPoint}`
      : `Miss at ${formattedPoint}`;
    const marker = node(
      "span",
      result.hit ? "✓" : "×",
      `hotspot-test-marker ${result.hit ? "is-correct" : "is-miss"}`,
    );
    marker.style.left = `${point.x}%`;
    marker.style.top = `${point.y}%`;
    overlay.append(marker);
    window.setTimeout(() => marker.remove(), 2000);
  }

  testToggle.addEventListener("click", () => {
    testMode = !testMode;
    testToggle.setAttribute("aria-pressed", String(testMode));
    testToggle.textContent = testMode ? "Exit test mode" : "Test clicks";
    surface.classList.toggle("is-testing", testMode);
    imageStatus.textContent = testMode
      ? "Test mode: click the image to check a coordinate."
      : "";
  });

  toleranceInput.addEventListener("input", () => {
    edited = true;
    tolerance = toleranceInput.value === "" ? Number.NaN : Number(toleranceInput.value);
    showDiagnostics();
  });

  deleteButton.addEventListener("click", () => {
    if (selectedIndex < 0 || selectedIndex >= regions.length) {
      return;
    }
    regions.splice(selectedIndex, 1);
    edited = true;
    selectedIndex = -1;
    showDiagnostics();
  });

  revertButton.addEventListener("click", () => {
    regions.splice(0, regions.length, ...initialRegions.map((region) => ({ ...region })));
    tolerance = initialTolerance;
    edited = false;
    toleranceInput.value = String(initialTolerance);
    selectedIndex = -1;
    imageStatus.textContent = "Unsaved edits reverted.";
    showDiagnostics();
  });

  panel.addEventListener("keydown", (event) => {
    if (
      selectedIndex < 0 ||
      selectedIndex >= regions.length ||
      event.target instanceof HTMLInputElement
    ) {
      return;
    }
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      regions.splice(selectedIndex, 1);
      edited = true;
      selectedIndex = -1;
      showDiagnostics();
      return;
    }
    const nudges = {
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
    };
    const nudge = nudges[event.key];
    if (!nudge) {
      return;
    }
    event.preventDefault();
    const amount = event.shiftKey ? 2 : 0.5;
    const region = regions[selectedIndex];
    edited = true;
    region.x = clamp(region.x + nudge[0] * amount);
    region.y = clamp(region.y + nudge[1] * amount);
    region.x = Math.min(region.x, 100 - region.w);
    region.y = Math.min(region.y, 100 - region.h);
    showDiagnostics();
  });

  surface.addEventListener("pointerdown", (event) => {
    if (!puzzle.image_data_url || image.naturalWidth === 0) {
      return;
    }
    const point = pointOnImage(event, image);
    if (testMode) {
      if (
        event.target === image ||
        event.target === overlay ||
        event.target.closest?.(".hotspot-region")
      ) {
        markTestResult(point);
      }
      return;
    }

    const regionBox = event.target.closest?.("[data-hotspot-region]");
    const handle = event.target.closest?.("[data-hotspot-handle]");
    if (regionBox) {
      selectedIndex = Number(regionBox.dataset.hotspotRegion);
    }
    const regionIndex = handle
      ? Number(handle.dataset.hotspotRegionIndex)
      : regionBox
        ? Number(regionBox.dataset.hotspotRegion)
        : -1;
    if (regionIndex >= 0 && regionIndex < regions.length) {
      const region = regions[regionIndex];
      interaction = {
        kind: handle ? "resize" : "move",
        corner: handle?.dataset.hotspotHandle,
        regionIndex,
        point,
        original: { ...region },
      };
      selectedIndex = regionIndex;
      panel.focus({ preventScroll: true });
    } else if (event.target === image || event.target === overlay) {
      const region = { x: point.x, y: point.y, w: 0, h: 0 };
      regions.push(region);
      selectedIndex = regions.length - 1;
      interaction = {
        kind: "draw",
        regionIndex: selectedIndex,
        point,
        original: { ...region },
      };
    } else {
      return;
    }
    event.preventDefault();
    surface.setPointerCapture(event.pointerId);
    showDiagnostics();
  });

  surface.addEventListener("pointermove", (event) => {
    if (!interaction) {
      return;
    }
    const point = pointOnImage(event, image);
    const { kind, point: start, original, regionIndex, corner } = interaction;
    const region = regions[regionIndex];
    if (!region) {
      return;
    }
    if (kind === "draw") {
      region.x = Math.min(start.x, point.x);
      region.y = Math.min(start.y, point.y);
      region.w = Math.abs(point.x - start.x);
      region.h = Math.abs(point.y - start.y);
    } else if (kind === "move") {
      region.x = clamp(original.x + point.x - start.x);
      region.y = clamp(original.y + point.y - start.y);
      region.x = Math.min(region.x, 100 - region.w);
      region.y = Math.min(region.y, 100 - region.h);
    } else {
      const left = corner.includes("w");
      const top = corner.includes("n");
      const fixedX = left ? original.x + original.w : original.x;
      const fixedY = top ? original.y + original.h : original.y;
      const movingX = clamp(point.x);
      const movingY = clamp(point.y);
      region.x = Math.min(fixedX, movingX);
      region.y = Math.min(fixedY, movingY);
      region.w = Math.abs(fixedX - movingX);
      region.h = Math.abs(fixedY - movingY);
    }
    edited = true;
    showDiagnostics();
  });

  function endInteraction(event) {
    if (!interaction) {
      return;
    }
    const { kind, regionIndex } = interaction;
    interaction = undefined;
    if (kind === "draw") {
      const region = regions[regionIndex];
      if (region.w < MIN_DRAW_SIZE || region.h < MIN_DRAW_SIZE) {
        regions.splice(regionIndex, 1);
        selectedIndex = -1;
        if (testMode) {
          markTestResult(pointOnImage(event, image));
        }
      } else {
        edited = true;
      }
    }
    showDiagnostics();
  }

  surface.addEventListener("pointerup", endInteraction);
  surface.addEventListener("pointercancel", endInteraction);

  panel.append(controls, instruction, surface, imageStatus, diagnostics);
  panel.dataset.hotspotId = puzzle.id;
  editorStates.set(panel, () => ({
    regions: regions.map((region) => ({ ...region })),
    tolerance,
  }));
  showDiagnostics();
  return panel;
}

export function renderHotspotEditors(root, puzzles) {
  root.replaceChildren();
  root.hidden = !Array.isArray(puzzles) || puzzles.length === 0;
  if (root.hidden) {
    return;
  }
  root.append(
    node("h3", "Image-region puzzles", "hotspot-editor-heading"),
    node(
      "p",
      "Draw or adjust the target regions, then submit the room to save them directly into its puzzle data.",
      "hotspot-editor-description",
    ),
  );
  for (const puzzle of puzzles) {
    root.append(renderPuzzle(puzzle));
  }
}

export function getHotspotEdits(root) {
  return Object.fromEntries(
    [...root.querySelectorAll(".hotspot-editor-panel")].flatMap((panel) => {
      const getState = editorStates.get(panel);
      return panel.dataset.hotspotId && getState
        ? [[panel.dataset.hotspotId, getState()]]
        : [];
    }),
  );
}
