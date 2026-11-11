import {
  getHotspotEdits,
  renderHotspotEditors,
} from "./puzzles/hotspot-editor.js?v=43";

const statusElement = document.querySelector("#connection-status");
const gameStatusElement = document.querySelector("#game-status");
const createForm = document.querySelector("#create-game-form");
const joinForm = document.querySelector("#join-game-form");
const joinCodeInput = document.querySelector("#join-code");
const joinCodeDigits = [...document.querySelectorAll("[data-join-code-digit]")];
const adminKeyInput = document.querySelector("#admin-key");
const roomSelect = document.querySelector("#room-select");
const playtestButton = document.querySelector("#playtest-button");
const roomUploadTools = document.querySelector("#room-upload-tools");
const uploadRoomForm = document.querySelector("#upload-room-form");
const roomArchiveInput = document.querySelector("#room-archive");
const roomUploadDropzone = document.querySelector("#room-upload-dropzone");
const roomUploadFileName = document.querySelector("#room-upload-file-name");
const browseRoomFileButton = document.querySelector("#browse-room-file");
const roomPublishTools = document.querySelector("#room-publish-tools");
const publishRoomButton = document.querySelector("#publish-room-button");
const hostGuidePreview = document.querySelector("#host-guide-preview");
const hostGuideText = document.querySelector("#host-guide-text");
const hotspotValidationPanel = document.querySelector("#hotspot-validation");
const lobbyView = document.querySelector("#lobby-view");
const gameView = document.querySelector("#game-view");
const gameMain = document.querySelector(".game-main");
const lobbyCodeElement = document.querySelector("#lobby-code");
const lobbyPhaseElement = document.querySelector("#lobby-phase");
const appToastElement = document.querySelector("#app-toast");
const teamListElement = document.querySelector("#team-list");
const playerListElement = document.querySelector("#player-list");
const hostDragHelp = document.querySelector("#host-drag-help");
const hostControls = document.querySelector("#host-controls");
const nameForm = document.querySelector("#player-name-form");
const nameInput = document.querySelector("#player-name");
const createTeamForm = document.querySelector("#create-team-form");
const teamNameInput = document.querySelector("#team-name");
const createTeamButton = document.querySelector("#create-team-button");
const teamNameHelp = document.querySelector("#team-name-help");
const lockTeamsButton = document.querySelector("#lock-teams-button");
const autoBalanceButton = document.querySelector("#auto-balance-button");
const startGameButton = document.querySelector("#start-game-button");
const roomTitleElement = document.querySelector("#room-title");
const gameCodeElement = document.querySelector("#game-code");
const resultsView = document.querySelector("#results-view");
const resultsRoomTitleElement = document.querySelector("#results-room-title");
const resultsGameCodeElement = document.querySelector("#results-game-code");
const resultsHomeButton = document.querySelector("#results-home-button");
const lobbyCodeCopyButton = document.querySelector("#copy-lobby-code");
const gameCodeCopyButton = document.querySelector("#copy-game-code");
const resultsCodeCopyButton = document.querySelector("#copy-results-game-code");
const roomIntroElement = document.querySelector("#room-intro");
const roomIntroImageElement = document.querySelector("#room-intro-image");
const teamProgressElement = document.querySelector("#team-progress");
const gameClockElement = document.querySelector("#game-clock");
const gameToastElement = document.querySelector("#game-toast");
const pausedOverlay = document.querySelector("#paused-overlay");
const gameHostControls = document.querySelector("#game-host-controls");
const openHostControlsButton = document.querySelector("#open-host-controls");
const hostControlsModal = document.querySelector("#host-controls-modal");
const closeHostControlsButton = document.querySelector("#close-host-controls");
const pauseGameButton = document.querySelector("#pause-game-button");
const addTimeForm = document.querySelector("#add-time-form");
const addTimeMinutes = document.querySelector("#add-time-minutes");
const skipPuzzleForm = document.querySelector("#skip-puzzle-form");
const skipTeamSelect = document.querySelector("#skip-team");
const skipPuzzleSelect = document.querySelector("#skip-puzzle");
const hostMessageForm = document.querySelector("#host-message-form");
const hostMessageTeamSelect = document.querySelector("#host-message-team");
const hostMessageInput = document.querySelector("#host-message-text");
const kickPlayerList = document.querySelector("#kick-player-list");
const teamActivityList = document.querySelector("#team-activity");
const leaderboardResults = document.querySelector("#leaderboard-results");
const raceChartCanvas = document.querySelector("#race-chart-canvas");
const hostTeamProgress = document.querySelector("#host-team-progress");
const themeToggle = document.querySelector("#theme-toggle");
const soundToggle = document.querySelector("#sound-toggle");
const confettiLayer = document.querySelector("#confetti-layer");
const homeHero = document.querySelector("#home-hero");
const connectionStrip = document.querySelector("#connection-strip");
const homeGrid = document.querySelector("#home-grid");
const puzzleMapElement = document.querySelector("#puzzle-map");
const puzzlePanel = document.querySelector("#puzzle-panel");
const puzzleTitleElement = document.querySelector("#puzzle-title");
const puzzlePrestoryElement = document.querySelector("#puzzle-prestory");
const puzzleModuleRoot = document.querySelector("#puzzle-module-root");
const puzzleChallenge = document.querySelector("#puzzle-challenge");
const beginPuzzleButton = document.querySelector("#begin-puzzle-button");
const puzzleHintElement = document.querySelector("#puzzle-hint");
const hintButton = document.querySelector("#hint-button");
const resultsPanel = document.querySelector("#results-panel");
const roomOutroElement = document.querySelector("#room-outro");
const roomOutroImageElement = document.querySelector("#room-outro-image");
const standingsListElement = document.querySelector("#standings-list");
const awardsListElement = document.querySelector("#awards-list");
const playerStatsListElement = document.querySelector("#player-stats-list");
const playerIdKey = "party-games-player-id";
const activeGameKey = "party-games-active-game";
const themeKey = "party-games-theme";
const mutedKey = "party-games-muted";
const roomTokensKey = "party-games-room-tokens";
let reconnectDelay = 1000;
let heartbeat;
let socket;
let reconnectPending = false;
let lobbySnapshot;
let gameSnapshot;
let currentPuzzle;
let availableRoomCount = 0;
let roomCatalog = [];
let canPublishRooms = false;
let confirmStart = false;
let muted = localStorage.getItem(mutedKey) === "true";
let audioContext;
let pausedControlStates;
let raceChart;
let pendingLobbyAction;
let renderedResultsGameId;
let appToastTimer;
const codeCopyResetTimers = new WeakMap();
const puzzleModules = {
  text: () => import("./puzzles/text.js?v=43"),
  multiple_choice: () => import("./puzzles/multiple_choice.js?v=43"),
  lock: () => import("./puzzles/lock.js?v=43"),
  split_clue: () => import("./puzzles/split_clue.js?v=43"),
  cipher: () => import("./puzzles/cipher.js?v=43"),
  ordering: () => import("./puzzles/ordering.js?v=43"),
  matching: () => import("./puzzles/matching.js?v=43"),
  pick_all: () => import("./puzzles/pick_all.js?v=43"),
  meta: () => import("./puzzles/meta.js?v=43"),
  image_hotspot: () => import("./puzzles/image_hotspot.js?v=43"),
};
const pageUrl = new URL(window.location.href);
let joinOnConnect = pageUrl.searchParams.get("join");

if (pageUrl.searchParams.has("admin-key")) {
  pageUrl.searchParams.delete("admin-key");
  window.history.replaceState(null, "", pageUrl);
}

function createPlayerId() {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function getPlayerId() {
  let playerId = localStorage.getItem(playerIdKey);
  if (!playerId) {
    playerId = createPlayerId();
    localStorage.setItem(playerIdKey, playerId);
  }
  return playerId;
}

function getRoomTokens() {
  const saved = localStorage.getItem(roomTokensKey);
  if (!saved) {
    return {};
  }
  const tokens = JSON.parse(saved);
  if (
    !tokens
    || typeof tokens !== "object"
    || Array.isArray(tokens)
    || Object.entries(tokens).some(
      ([roomId, token]) =>
        !roomId || typeof token !== "string" || token.length < 16,
    )
  ) {
    throw new Error("Stored room access tokens are invalid.");
  }
  return tokens;
}

function saveRoomToken(roomId, token) {
  const tokens = getRoomTokens();
  tokens[roomId] = token;
  localStorage.setItem(roomTokensKey, JSON.stringify(tokens));
}

function getActiveGame() {
  const saved = localStorage.getItem(activeGameKey);
  if (!saved) {
    return null;
  }
  try {
    const activeGame = JSON.parse(saved);
    if (
      typeof activeGame.gameId === "string" &&
      typeof activeGame.code === "string"
    ) {
      return activeGame;
    }
    throw new Error("Stored game session is invalid.");
  } catch {
    localStorage.removeItem(activeGameKey);
    return null;
  }
}

function send(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    gameStatusElement.textContent = "Not connected. Please wait and try again.";
    return;
  }
  socket.send(JSON.stringify(payload));
}

function saveGameSession(message, isHost) {
  const activeGame = {
    gameId: message.game_id,
    code: message.code,
    isHost,
    isPlaytest: message.is_playtest === true,
  };
  if (isHost) {
    activeGame.hostToken = message.host_token;
  }
  localStorage.setItem(activeGameKey, JSON.stringify(activeGame));
  setJoinCode(message.code || "");
  if (isHost) {
    adminKeyInput.value = "";
    gameStatusElement.textContent = message.is_playtest
      ? "Private playtest created. Host access is saved in this browser."
      : `Game created. Share code ${message.code} with players. ` +
        "Host access is saved in this browser.";
  } else {
    gameStatusElement.textContent = `Joined game ${message.code}.`;
  }
  setFormsDisabled(true);
}

function setFormsDisabled(disabled) {
  createForm.querySelector("button").disabled = disabled || availableRoomCount === 0;
  playtestButton.disabled = disabled || availableRoomCount === 0;
  roomSelect.disabled = disabled;
  joinForm.querySelector("button").disabled = disabled;
  for (const digit of joinCodeDigits) {
    digit.disabled = disabled;
  }
  adminKeyInput.disabled = disabled;
}

function makeElement(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) {
    element.textContent = text;
  }
  if (className) {
    element.className = className;
  }
  return element;
}

function normalizeJoinCode(value) {
  return value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 5);
}

function setJoinCode(value) {
  const code = normalizeJoinCode(value);
  joinCodeDigits.forEach((digit, index) => {
    digit.value = code[index] || "";
  });
  joinCodeInput.value = code;
}

function updateJoinCodeValue() {
  joinCodeInput.value = joinCodeDigits.map((digit) => digit.value).join("");
}

function fillJoinCode(value) {
  setJoinCode(value);
  const nextEmpty = joinCodeDigits.find((digit) => !digit.value);
  (nextEmpty || joinCodeDigits.at(-1)).focus();
}

joinCodeDigits.forEach((digit, index) => {
  digit.addEventListener("input", () => {
    const code = normalizeJoinCode(digit.value);
    if (code.length > 1) {
      fillJoinCode(code);
      return;
    }
    digit.value = code;
    updateJoinCodeValue();
    if (code && index < joinCodeDigits.length - 1) {
      joinCodeDigits[index + 1].focus();
    }
  });
  digit.addEventListener("paste", (event) => {
    event.preventDefault();
    fillJoinCode(normalizeJoinCode(event.clipboardData.getData("text")));
  });
  digit.addEventListener("keydown", (event) => {
    if (event.key === "Backspace" && !digit.value && index > 0) {
      joinCodeDigits[index - 1].focus();
    } else if (event.key === "ArrowLeft" && index > 0) {
      event.preventDefault();
      joinCodeDigits[index - 1].focus();
    } else if (event.key === "ArrowRight" && index < joinCodeDigits.length - 1) {
      event.preventDefault();
      joinCodeDigits[index + 1].focus();
    }
  });
});

function updateCodeCopyButton(button, code) {
  const canCopy = Boolean(code);
  window.clearTimeout(codeCopyResetTimers.get(button));
  button.removeAttribute("data-copy-state");
  button.disabled = !canCopy;
  button.querySelector(".code-copy-label").textContent = canCopy
    ? "Copy"
    : "No code";
  button.setAttribute(
    "aria-label",
    canCopy ? `Copy join code ${code}` : "No join code available",
  );
}

async function writeClipboardText(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Fall through to the selection-based copy for non-secure or restricted contexts.
    }
  }

  const input = document.createElement("textarea");
  input.value = text;
  input.setAttribute("readonly", "");
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.append(input);
  input.select();
  const copied = document.execCommand("copy");
  input.remove();
  if (!copied) {
    throw new Error("The browser denied clipboard access.");
  }
}

async function copyJoinCode(button, codeElement) {
  const code = codeElement.textContent.trim();
  if (!code) {
    return;
  }
  try {
    await writeClipboardText(code);
    button.setAttribute("aria-label", `Join code ${code} copied`);
    showToast("Join code copied to clipboard.", "success");
  } catch (error) {
    console.error("Could not copy join code.", error);
    button.setAttribute("aria-label", "Could not copy join code");
    showToast("Could not copy join code.", "error");
  }
  window.clearTimeout(codeCopyResetTimers.get(button));
  codeCopyResetTimers.set(button, window.setTimeout(() => {
    button.setAttribute("aria-label", `Copy join code ${code}`);
  }, 2200));
}

function showToast(message, type = "warning") {
  window.clearTimeout(appToastTimer);
  appToastElement.textContent = message;
  appToastElement.dataset.type = type;
  appToastElement.setAttribute("role", type === "error" ? "alert" : "status");
  appToastElement.setAttribute(
    "aria-live",
    type === "error" ? "assertive" : "polite",
  );
  appToastElement.hidden = false;
  appToastTimer = window.setTimeout(() => {
    appToastElement.hidden = true;
    appToastElement.textContent = "";
    delete appToastElement.dataset.type;
  }, 4500);
}

function sendLobbyAction(type, values = {}) {
  send({ type, ...values });
}

function updateLobbyVisibility() {
  const active = Boolean(lobbySnapshot);
  lobbyView.hidden = !active || lobbySnapshot.phase !== "lobby";
  homeHero.hidden = active;
  connectionStrip.hidden = !active || !lobbySnapshot?.is_host;
  homeGrid.hidden = active;
  gameStatusElement.hidden = active;
  document.querySelector('[aria-labelledby="create-game-heading"]').hidden = active;
  document.querySelector('[aria-labelledby="join-game-heading"]').hidden = active;
  if (active) {
    setFormsDisabled(true);
  }
}

function renderTeamControls(team, currentPlayer, canHostControl) {
  const teamCard = makeElement(
    "article",
    undefined,
    "team-card",
  );
  if (canHostControl && lobbySnapshot.phase === "lobby") {
    teamCard.addEventListener("dragover", (event) => {
      event.preventDefault();
    });
    teamCard.addEventListener("drop", (event) => {
      event.preventDefault();
      const playerId = event.dataTransfer.getData("text/plain");
      if (playerId) {
        sendLobbyAction("lobby.move_player", {
          player_id: playerId,
          team_id: team.team_id,
        });
      }
    });
  }
  const header = makeElement("div", undefined, "team-header");
  const teamSize = lobbySnapshot.phase === "playing"
    ? `${team.player_count} players · ${team.solved} solved`
    : `${team.player_count} / ${team.max_team_size} players`;
  header.append(
    makeElement("h4", team.name),
    makeElement("span", teamSize),
  );
  teamCard.append(header);

  const members = makeElement("ul");
  for (const playerId of team.player_ids) {
    const player = lobbySnapshot.players.find(
      (candidate) => candidate.player_id === playerId,
    );
    if (player) {
      members.append(makeElement("li", player.name));
    }
  }
  teamCard.append(members);

  const canJoin = currentPlayer.team_id !== team.team_id &&
    (lobbySnapshot.phase === "playing" || !lobbySnapshot.teams_locked) &&
    (lobbySnapshot.phase === "playing" ||
      team.player_count < team.max_team_size);
  if (canJoin) {
    const joinButton = makeElement(
      "button",
      currentPlayer.team_id ? "Change to this team" : "Join this team",
      "button button-secondary",
    );
    joinButton.type = "button";
    joinButton.addEventListener("click", () => {
      sendLobbyAction("lobby.join_team", { team_id: team.team_id });
    });
    teamCard.append(joinButton);
  }

  if (
    currentPlayer.team_id === team.team_id &&
    lobbySnapshot.phase === "lobby" &&
    !lobbySnapshot.teams_locked &&
    !lobbySnapshot.is_playtest
  ) {
    const leaveButton = makeElement("button", "Leave team", "button button-quiet");
    leaveButton.type = "button";
    leaveButton.addEventListener("click", () => {
      sendLobbyAction("lobby.leave_team");
    });
    teamCard.append(leaveButton);
  }

  if (canHostControl) {
    const renameForm = document.createElement("form");
    renameForm.className = "inline-form";
    const renameInput = document.createElement("input");
    renameInput.type = "text";
    renameInput.maxLength = 30;
    renameInput.value = team.name;
    renameInput.setAttribute("aria-label", `Rename ${team.name}`);
    renameInput.dataset.focusKey = `team-rename-${team.team_id}`;
    renameInput.required = true;
    const renameButton = makeElement("button", "Rename", "button button-secondary");
    renameButton.type = "submit";
    renameForm.append(renameInput, renameButton);
    renameForm.addEventListener("submit", (event) => {
      event.preventDefault();
      sendLobbyAction("lobby.rename_team", {
        team_id: team.team_id,
        name: renameInput.value,
      });
    });
    teamCard.append(renameForm);

    if (team.player_count === 0 && lobbySnapshot.phase === "lobby") {
      const deleteButton = makeElement(
        "button",
        "Delete empty team",
        "button button-quiet",
      );
      deleteButton.type = "button";
      deleteButton.addEventListener("click", () => {
        sendLobbyAction("lobby.delete_team", { team_id: team.team_id });
      });
      teamCard.append(deleteButton);
    }
  }
  return teamCard;
}

function captureFocusedControl() {
  const control = document.activeElement;
  if (
    !control ||
    !["INPUT", "SELECT", "TEXTAREA"].includes(control.tagName)
  ) {
    return undefined;
  }

  return {
    control,
    focusKey: control.dataset.focusKey,
    id: control.id,
    ariaLabel: control.getAttribute("aria-label"),
    value: control.value,
    selectionStart: control instanceof HTMLInputElement ||
        control instanceof HTMLTextAreaElement
      ? control.selectionStart
      : null,
    selectionEnd: control instanceof HTMLInputElement ||
        control instanceof HTMLTextAreaElement
      ? control.selectionEnd
      : null,
  };
}

function restoreFocusedControl(state) {
  if (!state) {
    return;
  }

  let control = state.control;
  if (!control.isConnected) {
    control = [...document.querySelectorAll("input, select, textarea")].find(
      (candidate) =>
        candidate.tagName === state.control.tagName &&
        (state.focusKey
          ? candidate.dataset.focusKey === state.focusKey
          : state.id
          ? candidate.id === state.id
          : candidate.getAttribute("aria-label") === state.ariaLabel),
    );
    if (!control) {
      return;
    }

    if (control instanceof HTMLSelectElement) {
      if ([...control.options].some((option) => option.value === state.value)) {
        control.value = state.value;
      }
    } else {
      control.value = state.value;
    }
  }

  control.focus({ preventScroll: true });
  if (
    state.selectionStart !== null &&
    state.selectionEnd !== null &&
    (control instanceof HTMLInputElement ||
      control instanceof HTMLTextAreaElement)
  ) {
    control.setSelectionRange(state.selectionStart, state.selectionEnd);
  }
}

function renderLobby(snapshot) {
  const focusedControl = captureFocusedControl();
  const pendingAction = pendingLobbyAction;
  lobbySnapshot = snapshot;
  updateLobbyVisibility();
  lobbyCodeElement.textContent = snapshot.is_playtest
    ? "Private playtest · no join code"
    : snapshot.code;
  updateCodeCopyButton(
    lobbyCodeCopyButton,
    snapshot.is_playtest ? "" : snapshot.code,
  );
  lobbyPhaseElement.textContent = snapshot.phase === "playing"
    ? "Game started"
    : "Waiting for players";
  hostControls.hidden = !snapshot.is_host;
  hostDragHelp.hidden = !snapshot.is_host || snapshot.phase !== "lobby";

  const currentPlayer = snapshot.players.find(
    (player) => player.player_id === snapshot.player_id,
  );
  const hasPlayerName = Boolean(
    currentPlayer?.name && currentPlayer.name !== "Choosing a name",
  );
  if (focusedControl?.control !== nameInput) {
    nameInput.value = currentPlayer?.name === "Choosing a name"
      ? ""
      : currentPlayer?.name || "";
  }
  nameForm.hidden = false;
  createTeamForm.hidden =
    snapshot.phase !== "lobby" || snapshot.teams_locked || snapshot.is_playtest;
  lockTeamsButton.hidden = snapshot.phase !== "lobby" || snapshot.is_playtest;
  autoBalanceButton.hidden = snapshot.phase !== "lobby" || snapshot.is_playtest;
  startGameButton.hidden = snapshot.phase !== "lobby";
  createTeamButton.disabled =
    snapshot.phase !== "lobby" || snapshot.teams_locked;
  teamNameHelp.hidden = hasPlayerName;
  lockTeamsButton.textContent = snapshot.teams_locked
    ? "Unlock teams"
    : "Lock teams";
  startGameButton.textContent = confirmStart
    ? "Confirm start anyway"
    : "Start game";
  if (
    pendingAction?.type === "set_name" &&
    currentPlayer?.name === pendingAction.value
  ) {
    pendingLobbyAction = undefined;
  } else if (
    pendingAction?.type === "create_team" &&
    snapshot.teams.some(
      (team) => team.team_id === currentPlayer?.team_id &&
        team.name === pendingAction.value,
    )
  ) {
    pendingLobbyAction = undefined;
    teamNameInput.value = "";
  }

  teamListElement.replaceChildren();
  for (const team of snapshot.teams) {
    teamListElement.append(
      renderTeamControls(
        team,
        currentPlayer,
        snapshot.is_host && !snapshot.is_playtest,
      ),
    );
  }

  playerListElement.replaceChildren();
  for (const player of snapshot.players) {
    const row = makeElement(
      "li",
      undefined,
      "player-row",
    );
    if (snapshot.is_host) {
      row.draggable = snapshot.phase === "lobby";
      row.addEventListener("dragstart", (event) => {
        event.dataTransfer.setData("text/plain", player.player_id);
      });
    }
    const team = snapshot.teams.find(
      (candidate) => candidate.team_id === player.team_id,
    );
    const hostTag = player.is_host ? " · Host" : "";
    const connectionTag = player.connected ? "" : " · disconnected";
    row.append(
      makeElement(
        "span",
        `${player.name}${hostTag}${connectionTag} · ${team?.name || "Unassigned"}`,
      ),
    );
    if (snapshot.is_host) {
      const teamSelect = document.createElement("select");
      teamSelect.setAttribute("aria-label", `Move ${player.name} to a team`);
      teamSelect.dataset.focusKey = `player-team-${player.player_id}`;
      teamSelect.className = "team-player-select";
      const unassignedOption = makeElement("option", "Unassigned");
      unassignedOption.value = "";
      teamSelect.append(unassignedOption);
      for (const optionTeam of snapshot.teams) {
        const option = makeElement("option", optionTeam.name);
        option.value = optionTeam.team_id;
        teamSelect.append(option);
      }
      teamSelect.value = player.team_id || "";
      teamSelect.addEventListener("change", () => {
        sendLobbyAction("lobby.move_player", {
          player_id: player.player_id,
          team_id: teamSelect.value || null,
        });
      });
      row.append(teamSelect);
    }
    playerListElement.append(row);
  }

  if (snapshot.phase === "playing") {
    createTeamForm.hidden = true;
  }
  restoreFocusedControl(focusedControl);
}

function renderRoomList(rooms, canUpload, canPublish, preferredRoomId = "") {
  const previousRoomId = preferredRoomId || roomSelect.value;
  const placeholder = makeElement("option", "Choose a room");
  placeholder.value = "";
  placeholder.disabled = true;
  placeholder.selected = true;
  roomSelect.replaceChildren(placeholder);
  roomCatalog = rooms;
  canPublishRooms = canPublish;
  availableRoomCount = rooms.length;
  for (const room of rooms) {
    const option = makeElement(
      "option",
      `${room.title}${room.uploaded ? " · Uploaded" : ""}${room.uploaded && canPublish && !room.published ? " · Not published" : ""} · ${room.difficulty} · about ${room.est_minutes} min`,
    );
    option.value = room.id;
    roomSelect.append(option);
  }
  if (rooms.some((room) => room.id === previousRoomId)) {
    roomSelect.value = previousRoomId;
  }
  roomUploadTools.hidden = !canUpload;
  updateRoomPublishTools();
  createForm.querySelector("button").disabled = rooms.length === 0;
  playtestButton.disabled = rooms.length === 0;
  if (rooms.length === 0) {
    roomSelect.firstElementChild.textContent = "No valid rooms are available";
  }
}

function updateRoomPublishTools() {
  const selectedRoom = roomCatalog.find((room) => room.id === roomSelect.value);
  roomPublishTools.hidden = !(
    canPublishRooms
    && selectedRoom?.uploaded
    && !selectedRoom.published
    && getRoomTokens()[selectedRoom.id]
  );
}

async function loadRoomList(preferredRoomId = "") {
  try {
    const response = await fetch(
      new URL("api/rooms", window.location.href),
      {
        headers: {
          Accept: "application/json",
          "X-Room-Tokens": JSON.stringify(getRoomTokens()),
        },
      },
    );
    if (!response.ok) {
      throw new Error(`Room catalog request failed with status ${response.status}.`);
    }
    const catalog = await response.json();
    if (!Array.isArray(catalog.rooms)) {
      throw new Error("Room catalog response was invalid.");
    }
    if (typeof catalog.can_upload !== "boolean") {
      throw new Error("Room catalog upload permissions were invalid.");
    }
    if (typeof catalog.can_publish !== "boolean") {
      throw new Error("Room catalog publication permissions were invalid.");
    }
    renderRoomList(
      catalog.rooms,
      catalog.can_upload,
      catalog.can_publish,
      preferredRoomId,
    );
  } catch (error) {
    availableRoomCount = 0;
    createForm.querySelector("button").disabled = true;
    roomSelect.replaceChildren(
      makeElement("option", "Could not load rooms; reload to retry"),
    );
    roomSelect.firstElementChild.value = "";
    roomSelect.firstElementChild.disabled = true;
    gameStatusElement.textContent =
      error instanceof Error ? error.message : "Could not load the room catalog.";
  }
}

function formatClock(seconds) {
  seconds = Math.floor(seconds);
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainingSeconds).padStart(2, "0")}`;
}

function renderPuzzleMap(snapshot) {
  if (puzzlePanel.parentElement !== gameMain) {
    gameMain.insertBefore(puzzlePanel, confettiLayer);
  }
  puzzleMapElement.replaceChildren();
  for (const puzzle of snapshot.puzzles) {
    const card = makeElement(
      "article",
      undefined,
      "puzzle-entry",
    );
    card.dataset.state = puzzle.state;
    card.dataset.puzzleId = puzzle.id;
    card.append(
      makeElement("strong", puzzle.title, "text-base font-semibold"),
      makeElement("span", puzzle.state === "open" ? "Available" :
        puzzle.state === "solved" ? "Solved" :
          puzzle.state === "skipped" ? "Skipped" : "Locked"),
    );
    if (puzzle.state === "open") {
      const openButton = makeElement(
        "button",
        "Open puzzle",
        "button button-primary mt-auto",
      );
      openButton.type = "button";
      openButton.addEventListener("click", () => {
        send({ type: "puzzle.open", puzzle_id: puzzle.id });
      });
      card.append(openButton);
    } else if (puzzle.solve_text && puzzle.state === "solved") {
      card.append(makeElement("p", puzzle.solve_text, "puzzle-solve-text"));
    }
    if (snapshot.is_playtest && Object.hasOwn(puzzle, "answer")) {
      const answer = Array.isArray(puzzle.answer)
        ? puzzle.answer.map((item) =>
          Array.isArray(item) ? item.join(" → ") : item
        ).join(" / ")
        : puzzle.answer && typeof puzzle.answer === "object"
          ? JSON.stringify(puzzle.answer)
          : String(puzzle.answer);
      card.append(makeElement("p", `Answer: ${answer}`, "puzzle-answer"));
    }
    puzzleMapElement.append(card);
  }
  if (currentPuzzle && !puzzlePanel.hidden) {
    placePuzzlePanel(currentPuzzle.id);
  }
}

function placePuzzlePanel(puzzleId) {
  puzzleMapElement.querySelector(".puzzle-entry--active")?.classList.remove(
    "puzzle-entry--active",
  );
  const card = puzzleMapElement.querySelector(
    `[data-puzzle-id="${CSS.escape(puzzleId)}"]`,
  );
  if (window.matchMedia("(max-width: 56rem)").matches && card) {
    card.classList.add("puzzle-entry--active");
    card.append(puzzlePanel);
  } else {
    gameMain.insertBefore(puzzlePanel, confettiLayer);
  }
}

function roomAssetUrl(roomId, path) {
  const safePath = path.split("/").map(encodeURIComponent).join("/");
  const assetUrl = new URL(
    `rooms/${encodeURIComponent(roomId)}/assets/${safePath}`,
    window.location.href,
  );
  const activeGame = getActiveGame();
  const gameId = gameSnapshot?.game_id || activeGame?.gameId;
  if (gameId) {
    assetUrl.searchParams.set("game_id", gameId);
    assetUrl.searchParams.set("player_id", getPlayerId());
  }
  return assetUrl.href;
}

function submitPuzzleAnswer(answer) {
  if (currentPuzzle) {
    send({
      type: "puzzle.submit",
      puzzle_id: currentPuzzle.id,
      answer,
    });
  }
}

async function renderPuzzle(puzzle) {
  setPuzzlePaused(false);
  currentPuzzle = puzzle;
  puzzlePanel.hidden = false;
  placePuzzlePanel(puzzle.id);
  puzzleTitleElement.textContent = puzzle.title;
  puzzlePrestoryElement.textContent = puzzle.prestory;
  if (puzzle.image) {
    puzzle.image_url = roomAssetUrl(gameSnapshot.room_id, puzzle.image);
  }
  puzzleModuleRoot.replaceChildren();
  puzzleChallenge.hidden = true;
  beginPuzzleButton.hidden = false;
  puzzleHintElement.textContent = (puzzle.revealed_hints || []).join(" ");
  hintButton.disabled = puzzle.hints_used >= 3;
  const loadModule = puzzleModules[puzzle.type];
  if (!loadModule) {
    gameStatusElement.textContent = "This puzzle type is not supported.";
    return;
  }
  let module;
  try {
    module = await loadModule();
  } catch (error) {
    console.error("Failed to load puzzle module.", error);
    gameStatusElement.textContent =
      "Puzzle controls could not be loaded. Reload the page to try again.";
    return;
  }
  if (currentPuzzle?.id !== puzzle.id) {
    return;
  }
  module.render(puzzleModuleRoot, puzzle, submitPuzzleAnswer);
  setPuzzlePaused(gameSnapshot?.paused === true);
  if (window.matchMedia("(max-width: 56rem)").matches) {
    puzzlePanel.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

window.matchMedia("(max-width: 56rem)").addEventListener("change", () => {
  if (currentPuzzle && !puzzlePanel.hidden) {
    placePuzzlePanel(currentPuzzle.id);
  }
});

function renderResults(snapshot) {
  const results = snapshot.results;
  resultsPanel.hidden = !results;
  if (!results) {
    renderedResultsGameId = undefined;
    return;
  }
  if (snapshot.game_id === renderedResultsGameId) {
    return;
  }
  renderedResultsGameId = snapshot.game_id;
  leaderboardResults.hidden = snapshot.is_playtest;
  roomOutroElement.textContent = snapshot.outro;
  roomOutroImageElement.hidden = !snapshot.outro_image;
  if (snapshot.outro_image) {
    roomOutroImageElement.src = roomAssetUrl(
      snapshot.room_id,
      snapshot.outro_image,
    );
  } else {
    roomOutroImageElement.removeAttribute("src");
  }
  standingsListElement.replaceChildren();
  for (const team of results.standings || []) {
    standingsListElement.append(
      makeElement(
        "li",
        `${team.name}: ${team.solved} solved${team.skipped ? ` · ${team.skipped} skipped` : ""} · ${formatClock(team.adjusted_sec)} adjusted${team.finished ? " · finished" : ""}`,
      ),
    );
  }
  raceChart?.destroy();
  const darkTheme = document.documentElement.dataset.theme === "dark";
  Chart.defaults.color = darkTheme ? "#c2c7b6" : "#626b5d";
  const teamNames = new Map(snapshot.teams.map((team) => [team.team_id, team.name]));
  const teamIds = [...new Set([
    ...snapshot.teams.map((team) => team.team_id),
    ...(results.race || []).map((event) => event.team_id),
  ])];
  const maxElapsedMinutes = Math.max(
    0,
    ...(results.race || []).map((event) => event.elapsed_sec / 60),
  );
  const xAxisBuffer = Math.max(0.03, maxElapsedMinutes * 0.015);
  const xAxisMax = Math.ceil((maxElapsedMinutes + xAxisBuffer) * 10) / 10;
  const colors = ["#39704d", "#cf7442", "#427d91", "#a9502a", "#8a9b48", "#735d46"];
  const puzzleNames = new Map(
    snapshot.puzzles.map((puzzle) => [puzzle.id, puzzle.title]),
  );
  const datasets = teamIds.map((teamId, index) => {
    const events = (results.race || [])
      .filter((event) => event.team_id === teamId)
      .sort((left, right) => left.elapsed_sec - right.elapsed_sec);
    const color = colors[index % colors.length];
    return {
      label: teamNames.get(teamId) || events[0]?.team_name || "Team",
      data: [
        { x: 0, y: 0 },
        ...events.map((event, eventIndex) => ({
          x: event.elapsed_sec / 60,
          y: eventIndex + 1,
          puzzle_title: puzzleNames.get(event.puzzle_id) || event.puzzle_id,
          player_name: event.player_name || "Player",
        })),
      ],
      borderColor: color,
      backgroundColor: color,
      pointBackgroundColor: color,
      pointRadius: 4,
      pointHoverRadius: 6,
      borderWidth: 2,
      stepped: "after",
      fill: false,
    };
  });
  raceChart = new Chart(raceChartCanvas, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 250 },
      interaction: { intersect: false, mode: "nearest" },
      plugins: {
        legend: { position: "bottom", labels: { usePointStyle: true, padding: 18 } },
        tooltip: {
          callbacks: {
            title: (items) =>
              `${items[0]?.dataset.label || "Team"} · ${formatClock(Math.round(items[0]?.parsed.x * 60 || 0))}`,
            label: (context) => {
              const point = context.raw;
              return point.puzzle_title
                ? `${point.puzzle_title} solved by ${point.player_name}`
                : `${point.y} puzzles solved`;
            },
          },
        },
      },
      scales: {
        x: {
          type: "linear",
          title: { display: true, text: "Minutes elapsed" },
          min: -xAxisBuffer,
          max: xAxisMax,
          ticks: {
            precision: 1,
            callback: (value) =>
              value < 0 ? "" : Number(value).toFixed(1).replace(/\.0$/, ""),
          },
          grid: {
            color: darkTheme
              ? "rgba(194, 199, 182, 0.16)"
              : "rgba(98, 107, 93, 0.14)",
          },
        },
        y: {
          title: { display: true, text: "Puzzles solved" },
          min: -0.2,
          max: snapshot.puzzles.length + 0.2,
          afterBuildTicks: (scale) => {
            scale.ticks = Array.from(
              { length: snapshot.puzzles.length + 1 },
              (_, value) => ({ value }),
            );
          },
          ticks: {
            autoSkip: false,
            stepSize: 1,
            callback: (value) => String(value),
          },
          grid: {
            color: darkTheme
              ? "rgba(194, 199, 182, 0.16)"
              : "rgba(98, 107, 93, 0.14)",
          },
        },
      },
    },
  });
  awardsListElement.replaceChildren();
  for (const award of results.awards || []) {
    awardsListElement.append(makeElement("li", award.label));
  }
  playerStatsListElement.replaceChildren();
  for (const player of results.player_stats || []) {
    playerStatsListElement.append(
      makeElement(
        "li",
        `${player.name}: ${player.solves} solved · ${player.wrong_answers} wrong answers · ${player.average_solve_speed_sec ?? "—"} sec average`,
      ),
    );
  }
}

function renderHostDashboard(snapshot) {
  const canControl = snapshot.is_host && snapshot.phase === "playing";
  if (!canControl && hostControlsModal.classList.contains("flex")) {
    closeHostControlsButton.click();
  }
  gameHostControls.hidden = !canControl;
  openHostControlsButton.hidden = !canControl;
  if (!canControl) {
    return;
  }
  pauseGameButton.textContent = snapshot.paused ? "Resume game" : "Pause game";
  pauseGameButton.dataset.action = snapshot.paused ? "host.resume" : "host.pause";

  const teams = snapshot.teams || [];
  for (const select of [skipTeamSelect, hostMessageTeamSelect]) {
    const previousValue = select.value;
    const allOptions = [];
    if (select === hostMessageTeamSelect) {
      const option = makeElement("option", "All teams");
      option.value = "all";
      allOptions.push(option);
    }
    const options = teams.map((team) => {
      const option = makeElement("option", team.name);
      option.value = team.team_id;
      return option;
    });
    select.replaceChildren(...allOptions, ...options);
    if ([...select.options].some((option) => option.value === previousValue)) {
      select.value = previousValue;
    }
  }

  const previousPuzzle = skipPuzzleSelect.value;
  skipPuzzleSelect.replaceChildren(
    ...snapshot.puzzles.map((puzzle) => {
      const option = makeElement("option", puzzle.title);
      option.value = puzzle.id;
      return option;
    }),
  );
  if ([...skipPuzzleSelect.options].some((option) => option.value === previousPuzzle)) {
    skipPuzzleSelect.value = previousPuzzle;
  }
  kickPlayerList.replaceChildren();
  for (const player of lobbySnapshot?.players || []) {
    if (player.is_host) {
      continue;
    }
    const row = makeElement("li", undefined, "player-row");
    row.append(makeElement("span", player.name));
    const kickButton = makeElement("button", "Remove", "button button-quiet");
    kickButton.type = "button";
    kickButton.addEventListener("click", () => {
      send({ type: "host.kick", player_id: player.player_id });
    });
    row.append(kickButton);
    kickPlayerList.append(row);
  }

  hostTeamProgress.replaceChildren();
  const rankedTeams = [...teams].sort(
    (left, right) =>
      right.solved_count - left.solved_count ||
      left.adjusted_sec - right.adjusted_sec,
  );
  for (const team of rankedTeams) {
    hostTeamProgress.append(
      makeElement(
        "li",
        `${team.name}: ${team.solved_count} solved${team.skipped_count ? ` · ${team.skipped_count} skipped` : ""} · ${formatClock(team.adjusted_sec)} adjusted`,
      ),
    );
  }
}

function renderTeamActivity(snapshot) {
  const players = new Map(
    (lobbySnapshot?.players || []).map((player) => [
      player.player_id,
      player.name,
    ]),
  );
  const puzzleNames = new Map(
    snapshot.puzzles.map((puzzle) => [puzzle.id, puzzle.title]),
  );
  const labels = {
    open: "opened",
    wrong: "tried an answer for",
    solve: "solved",
    hint: "requested a hint for",
    skip: "had this puzzle skipped:",
  };
  teamActivityList.replaceChildren();
  for (const event of snapshot.activity || []) {
    const playerName = players.get(event.player_id) || "Team";
    const puzzleName = puzzleNames.get(event.puzzle_id) || "a puzzle";
    teamActivityList.append(
      makeElement(
        "li",
        `${formatClock(event.elapsed_sec)} · ${playerName} ${labels[event.type] || "updated"} ${puzzleName}`,
      ),
    );
  }
}

function setPuzzlePaused(paused) {
  pausedOverlay.hidden = !paused;
  const controls = [...puzzlePanel.querySelectorAll("button, input, select")];
  if (paused) {
    pausedControlStates ||= new Map();
    for (const control of controls) {
      if (!pausedControlStates.has(control)) {
        pausedControlStates.set(control, control.disabled);
      }
      control.disabled = true;
    }
  } else if (pausedControlStates) {
    for (const [control, wasDisabled] of pausedControlStates) {
      control.disabled = wasDisabled;
    }
    pausedControlStates = undefined;
  }
}

function renderGame(snapshot) {
  const focusedControl = captureFocusedControl();
  const previousPhase = gameSnapshot?.phase;
  gameSnapshot = snapshot;
  const hasResults = snapshot.phase === "results" && Boolean(snapshot.results);
  gameView.hidden = hasResults;
  resultsView.hidden = !hasResults;
  lobbyView.hidden = true;
  roomTitleElement.textContent = snapshot.room_title;
  resultsRoomTitleElement.textContent = snapshot.room_title;
  const activeGame = getActiveGame();
  const displayedCode = snapshot.is_playtest
    ? "Private playtest · no join code"
    : snapshot.code || activeGame?.code || "Code unavailable";
  gameCodeElement.textContent = displayedCode;
  resultsGameCodeElement.textContent = displayedCode;
  const copyableCode = snapshot.is_playtest
    ? ""
    : snapshot.code || activeGame?.code || "";
  updateCodeCopyButton(gameCodeCopyButton, copyableCode);
  updateCodeCopyButton(resultsCodeCopyButton, copyableCode);
  resultsHomeButton.textContent = snapshot.is_host
    ? "Start another game"
    : "Return home";
  roomIntroElement.textContent = snapshot.intro;
  roomIntroImageElement.hidden = !snapshot.intro_image;
  if (snapshot.intro_image) {
    roomIntroImageElement.src = roomAssetUrl(
      snapshot.room_id,
      snapshot.intro_image,
    );
  } else {
    roomIntroImageElement.removeAttribute("src");
  }
  const statusText = snapshot.phase === "results"
    ? snapshot.end_reason === "time_up" ? "Time is up" : "Game ended"
    : snapshot.paused ? "Paused" : "In progress";
  teamProgressElement.textContent =
    `${snapshot.team_name}: ${snapshot.team_solved} solved` +
    `${snapshot.team_skipped ? ` · ${snapshot.team_skipped} skipped` : ""} · ${statusText}`;
  gameClockElement.textContent = formatClock(snapshot.remaining_sec);
  setPuzzlePaused(snapshot.paused);
  renderPuzzleMap(snapshot);
  renderHostDashboard(snapshot);
  renderTeamActivity(snapshot);
  renderResults(snapshot);
  if (snapshot.phase === "results") {
    hintButton.disabled = true;
  }
  if (
    previousPhase === "playing" &&
    snapshot.phase === "results" &&
    snapshot.end_reason === "finished"
  ) {
    celebrate(true);
  }
  restoreFocusedControl(focusedControl);
}

function returnHomeFromResults() {
  send({ type: "game.leave" });
  localStorage.removeItem(activeGameKey);
  lobbySnapshot = undefined;
  gameSnapshot = undefined;
  currentPuzzle = undefined;
  confirmStart = false;
  gameView.hidden = true;
  lobbyView.hidden = true;
  resultsView.hidden = true;
  resultsPanel.hidden = true;
  puzzlePanel.hidden = true;
  setPuzzlePaused(false);
  setFormsDisabled(false);
  updateLobbyVisibility();
  gameToastElement.textContent = "";
  gameStatusElement.textContent =
    "Game ended. Start another game or join one.";
  raceChart?.destroy();
  raceChart = undefined;
  renderedResultsGameId = undefined;
  window.scrollTo(0, 0);
}

function celebrate(isFinish) {
  if (!muted && typeof AudioContext !== "undefined") {
    audioContext ||= new AudioContext();
    void audioContext.resume();
    const frequencies = isFinish ? [523.25, 659.25, 783.99] : [659.25, 783.99];
    frequencies.forEach((frequency, index) => {
      const oscillator = audioContext.createOscillator();
      const gain = audioContext.createGain();
      const start = audioContext.currentTime + index * 0.12;
      oscillator.frequency.value = frequency;
      gain.gain.setValueAtTime(0.08, start);
      gain.gain.exponentialRampToValueAtTime(0.001, start + 0.18);
      oscillator.connect(gain);
      gain.connect(audioContext.destination);
      oscillator.start(start);
      oscillator.stop(start + 0.18);
    });
  }
  const count = isFinish ? 28 : 14;
  for (let index = 0; index < count; index += 1) {
    const piece = makeElement("span", undefined, "confetti-piece");
    piece.style.setProperty("--confetti-x", `${Math.random() * 100}%`);
    piece.style.setProperty("--confetti-hue", `${Math.floor(Math.random() * 360)}`);
    piece.addEventListener("animationend", () => piece.remove(), { once: true });
    confettiLayer.append(piece);
  }
}

function applyPreferences() {
  const savedTheme = localStorage.getItem(themeKey);
  const dark = savedTheme
    ? savedTheme === "dark"
    : window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  themeToggle.querySelector("span").textContent = dark
    ? "Use light mode"
    : "Use dark mode";
  themeToggle.setAttribute("aria-pressed", String(dark));
  soundToggle.querySelector("span").textContent = muted
    ? "Unmute sounds"
    : "Mute sounds";
  soundToggle.setAttribute("aria-pressed", String(muted));
  if (raceChart) {
    const textColor = dark ? "#c2c7b6" : "#626b5d";
    const gridColor = dark
      ? "rgba(194, 199, 182, 0.16)"
      : "rgba(98, 107, 93, 0.14)";
    raceChart.options.color = textColor;
    raceChart.options.scales.x.grid.color = gridColor;
    raceChart.options.scales.y.grid.color = gridColor;
    raceChart.update("none");
  }
}

const errorMessages = {
  invalid_admin_key: "That admin key is not valid.",
  game_limit_reached: "The server is at its game limit. Try again later.",
  game_full: "That game is full.",
  game_not_found: "No active game has that code.",
  invalid_join_code: "Enter a valid 5-character game code.",
  invalid_host_token: "Could not restore host access in this browser.",
  player_not_found: "This player is not part of that game.",
  player_kicked: "This player was removed from the game.",
  invalid_time_amount: "Choose an amount of time from 1 to 120 minutes.",
  invalid_host_action: "The host action was invalid.",
  invalid_host_message: "Enter a message of up to 200 characters.",
  invalid_player_id: "That player cannot be removed.",
  already_in_game: "This browser is already connected to a game.",
  game_in_progress: "The game is still in progress.",
  invalid_room_id: "The selected room identifier is invalid.",
  room_not_found: "That room is not available on this server.",
  no_rooms_available: "There are no valid rooms available.",
  room_required: "Choose an escape room before creating a game.",
  not_in_game: "Join or create a game before using lobby actions.",
  host_only: "Only the host can use that control.",
  player_not_found: "That player could not be found.",
  name_required: "Choose your name before joining a team.",
  invalid_player_name: "Names must be 1–24 characters with no control characters.",
  invalid_team_name: "Team names must be 1–30 characters with no control characters.",
  duplicate_team_name: "That team name is already in use.",
  max_teams_reached: "This game has reached its team limit.",
  team_full: "That team is full.",
  team_not_found: "That team could not be found.",
  team_not_empty: "Only empty teams can be deleted.",
  playtest_solo_only: "Team and player changes are disabled in a solo playtest.",
  teams_locked: "Teams are locked; ask the host to move you.",
  game_already_started: "The game has already started.",
  no_teams: "Create a team before starting the game.",
  team_capacity: "There is not enough team capacity for unassigned players.",
  names_required: "Every player must choose a name before the game starts.",
  invalid_lock_state: "Invalid team lock setting.",
  game_ended: "This game has ended and cannot accept new players.",
  game_not_started: "The game has not started yet.",
  game_over: "The game has ended.",
  game_paused: "The game is paused.",
  player_not_on_team: "Join a team to take part in the game.",
  puzzle_not_found: "That puzzle could not be found.",
  puzzle_locked: "That puzzle is still locked.",
  puzzle_already_solved: "Your team has already solved that puzzle.",
  answer_cooldown: "Wait for the answer cooldown before trying again.",
  invalid_answer: "Enter a valid answer.",
  no_hints_left: "There are no hints remaining for this puzzle.",
  team_finished: "Your team has already finished.",
};

function handleMessage(event) {
  let message;
  try {
    message = JSON.parse(event.data);
  } catch {
    gameStatusElement.textContent = "Received an invalid server response.";
    return;
  }

  if (message.type === "lobby.snapshot") {
    renderLobby(message);
  } else if (message.type === "game.snapshot") {
    renderGame(message);
  } else if (message.type === "game.clock") {
    gameClockElement.textContent = formatClock(message.remaining_sec);
    if (gameSnapshot) {
      gameSnapshot.paused = message.paused;
      pauseGameButton.dataset.action = message.paused ? "host.resume" : "host.pause";
      pauseGameButton.textContent = message.paused ? "Resume game" : "Pause game";
      setPuzzlePaused(message.paused);
    }
  } else if (message.type === "game.created") {
    saveGameSession(message, true);
  } else if (message.type === "game.joined") {
    saveGameSession(message, false);
  } else if (message.type === "game.reconnected") {
    reconnectPending = false;
    const activeGame = getActiveGame();
    gameStatusElement.textContent = message.is_host
      ? activeGame?.isPlaytest
        ? "Reconnected to your private playtest as host."
        : `Reconnected to game ${message.code} as host.`
      : `Reconnected to game ${message.code}.`;
    setFormsDisabled(true);
  } else if (message.type === "lobby.start_warning") {
    confirmStart = true;
    startGameButton.textContent = "Confirm start anyway";
    const teamNames = message.undersized_teams
      .map((team) => team.name)
      .join(", ");
    showToast(
      `Some teams are below the minimum size: ${teamNames}. ` +
      "Start anyway or add players.",
      "warning",
    );
  } else if (message.type === "lobby.started") {
    confirmStart = false;
  } else if (message.type === "game.puzzle") {
    if (gameSnapshot) {
      gameSnapshot.activity.push({
        type: "open",
        puzzle_id: message.puzzle.id,
        elapsed_sec: gameSnapshot.elapsed_sec,
        player_id: gameSnapshot.player_id,
      });
      gameSnapshot.activity = gameSnapshot.activity.slice(-30);
      renderTeamActivity(gameSnapshot);
    }
    renderPuzzle(message.puzzle);
  } else if (message.type === "game.hint") {
    if (currentPuzzle?.id === message.puzzle_id) {
      puzzleHintElement.textContent +=
        `${puzzleHintElement.textContent ? " " : ""}${message.hint}`;
      currentPuzzle.hints_used = message.hint_index + 1;
      hintButton.disabled = message.hints_remaining === 0;
    }
  } else if (message.type === "game.answer_result") {
    if (message.correct) {
      celebrate(false);
      puzzlePanel.hidden = true;
      currentPuzzle = undefined;
      puzzleMapElement.querySelector(".puzzle-entry--active")?.classList.remove(
        "puzzle-entry--active",
      );
      gameMain.insertBefore(puzzlePanel, confettiLayer);
      gameStatusElement.textContent = "Correct! Your team has solved the puzzle.";
    } else {
      gameStatusElement.textContent =
        `Not quite. Wait ${message.cooldown_sec} seconds before trying again.`;
    }
  } else if (message.type === "game.host_message") {
    gameToastElement.textContent = `Host: ${message.text}`;
  } else if (message.type === "game.activity") {
    if (gameSnapshot) {
      gameSnapshot.activity.push(message.activity);
      gameSnapshot.activity = gameSnapshot.activity.slice(-30);
      renderTeamActivity(gameSnapshot);
    }
  } else if (message.type === "game.kicked") {
    localStorage.removeItem(activeGameKey);
    gameView.hidden = true;
    lobbyView.hidden = true;
    setFormsDisabled(false);
    gameStatusElement.textContent = "The host removed you from this game.";
  } else if (message.type === "error") {
    pendingLobbyAction = undefined;
    showToast(
      errorMessages[message.error] || "The request could not be completed.",
      "error",
    );
    if (
      reconnectPending &&
      ["game_not_found", "invalid_host_token", "player_not_found", "player_kicked"].includes(
        message.error,
      )
    ) {
      localStorage.removeItem(activeGameKey);
      setFormsDisabled(false);
    }
    reconnectPending = false;
  } else if (message.type === "pong") {
    return;
  }
}

function connect() {
  let playerId;
  try {
    playerId = getPlayerId();
  } catch {
    statusElement.textContent = "Browser storage is unavailable.";
    return;
  }

  const socketUrl = new URL("ws", window.location.href);
  socketUrl.protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  socketUrl.searchParams.set("player_id", playerId);
  socket = new WebSocket(socketUrl);

  socket.addEventListener("open", () => {
    reconnectDelay = 1000;
    statusElement.textContent = "Connected";
    statusElement.parentElement.dataset.status = "connected";
    const activeGame = getActiveGame();
    if (activeGame) {
      reconnectPending = true;
      send({
        type: "game.reconnect",
        game_id: activeGame.gameId,
        host_token: activeGame.hostToken,
      });
    } else if (joinOnConnect) {
      const code = normalizeJoinCode(joinOnConnect);
      setJoinCode(code);
      send({ type: "game.join", code });
      joinOnConnect = null;
    }
    heartbeat = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);
  });

  socket.addEventListener("close", (event) => {
    window.clearInterval(heartbeat);
    statusElement.parentElement.dataset.status = "disconnected";
    if (event.code === 4001) {
      // Another tab or window in this browser took over this player session.
      // Reconnecting here would kick that tab off and loop forever.
      statusElement.textContent = "Disconnected: open in another tab";
      gameStatusElement.textContent =
        "This game is now open in another tab or window. Close that tab and reload this page to continue here.";
      setFormsDisabled(true);
      return;
    }
    statusElement.textContent = "Disconnected; reconnecting…";
    window.setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 10000);
  });

  socket.addEventListener("message", handleMessage);
  socket.addEventListener("error", () => socket.close());
}

createForm.addEventListener("submit", (event) => {
  event.preventDefault();
  gameStatusElement.textContent = "Creating game…";
  send({
    type: "game.create",
    admin_key: adminKeyInput.value,
    room_id: roomSelect.value,
    room_token: getRoomTokens()[roomSelect.value] || "",
  });
});

function showSelectedRoomFile(file) {
  if (file && !file.name.toLowerCase().endsWith(".zip")) {
    roomArchiveInput.value = "";
    roomUploadFileName.textContent = "ZIP only · maximum 50 MB";
    showToast("Choose a room ZIP file.", "warning");
    return false;
  }
  roomUploadFileName.textContent =
    file?.name || "ZIP only · maximum 50 MB";
  return true;
}

browseRoomFileButton.addEventListener("click", () => {
  roomArchiveInput.click();
});

roomArchiveInput.addEventListener("change", () => {
  renderHotspotEditors(hotspotValidationPanel, []);
  uploadRoomForm.querySelector('button[type="submit"]').textContent =
    "Validate and add room";
  showSelectedRoomFile(roomArchiveInput.files?.[0]);
});

roomUploadDropzone.addEventListener("dragenter", (event) => {
  event.preventDefault();
  roomUploadDropzone.classList.add("is-dragging");
});

roomUploadDropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  event.dataTransfer.dropEffect = "copy";
  roomUploadDropzone.classList.add("is-dragging");
});

roomUploadDropzone.addEventListener("dragleave", (event) => {
  if (!roomUploadDropzone.contains(event.relatedTarget)) {
    roomUploadDropzone.classList.remove("is-dragging");
  }
});

roomUploadDropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  roomUploadDropzone.classList.remove("is-dragging");
  const file = event.dataTransfer.files?.[0];
  if (!file || !showSelectedRoomFile(file)) {
    return;
  }
  renderHotspotEditors(hotspotValidationPanel, []);
  uploadRoomForm.querySelector('button[type="submit"]').textContent =
    "Validate and add room";
  const files = new DataTransfer();
  files.items.add(file);
  roomArchiveInput.files = files.files;
});

uploadRoomForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const archive = roomArchiveInput.files?.[0];
  if (!archive) {
    showToast("Choose a room ZIP file first.", "warning");
    return;
  }
  const submitButton = uploadRoomForm.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  try {
    const formData = new FormData(uploadRoomForm);
    formData.set("admin_key", adminKeyInput.value);
    if (!hotspotValidationPanel.hidden) {
      formData.set("hotspot_regions", JSON.stringify(getHotspotEdits(hotspotValidationPanel)));
    }
    const response = await fetch(new URL("api/uploads", window.location.href), {
      method: "POST",
      headers: {
        "X-Room-Tokens": JSON.stringify(getRoomTokens()),
      },
      body: formData,
    });
    const result = await response.json();
    if (!response.ok) {
      const detail = result.detail;
      renderHotspotEditors(hotspotValidationPanel, detail?.hotspots || []);
      if (!hotspotValidationPanel.hidden) {
        submitButton.textContent = "Submit regions and add room";
      }
      const message = Array.isArray(detail?.errors)
        ? detail.errors.join(" ")
        : typeof detail === "string"
          ? {
            invalid_admin_key: "The admin key is incorrect.",
            room_id_conflicts_with_bundled: "That room ID is already in use.",
            room_id_already_uploaded: "That room ID belongs to another uploader.",
            room_in_use: "That room cannot be replaced while a game is using it.",
            upload_rate_limited: "Upload limit reached. Try again later.",
          }[detail] || detail
          : `Room upload failed (${response.status}).`;
      throw new Error(message);
    }
    if (
      typeof result.room?.id !== "string"
      || typeof result.room_token !== "string"
      || result.room_token.length < 16
    ) {
      throw new Error("The server returned an invalid upload response.");
    }
    saveRoomToken(result.room.id, result.room_token);
    renderHotspotEditors(hotspotValidationPanel, []);
    hostGuidePreview.hidden = typeof result.host_guide !== "string";
    hostGuideText.textContent = result.host_guide || "";
    roomArchiveInput.value = "";
    submitButton.textContent = "Validate and add room";
    showSelectedRoomFile(null);
    await loadRoomList(result.room.id);
    showToast(
      result.room.published === false
        ? "Room validated. It is private until you publish it."
        : result.warnings?.length
        ? `Room added with warnings: ${result.warnings.join(" ")}`
        : "Room validated and added.",
      result.room.published === false || result.warnings?.length
        ? "warning"
        : "success",
    );
  } catch (error) {
    showToast(
      error instanceof Error ? error.message : "Room upload failed.",
      "error",
    );
  } finally {
    submitButton.disabled = false;
  }
});

roomSelect.addEventListener("change", updateRoomPublishTools);

publishRoomButton.addEventListener("click", async () => {
  const roomId = roomSelect.value;
  const tokens = getRoomTokens();
  const roomToken = tokens[roomId];
  if (!roomId || !roomToken) {
    showToast("Select one of your unpublished rooms first.", "warning");
    return;
  }
  publishRoomButton.disabled = true;
  try {
    const response = await fetch(
      new URL(
        `api/uploads/${encodeURIComponent(roomId)}/publish`,
        window.location.href,
      ),
      {
        method: "POST",
        headers: {
          "X-Room-Tokens": JSON.stringify({ [roomId]: roomToken }),
        },
      },
    );
    const result = await response.json();
    if (!response.ok || result.room_id !== roomId || result.published !== true) {
      throw new Error(
        typeof result.detail === "string"
          ? result.detail
          : `Room publication failed (${response.status}).`,
      );
    }
    await loadRoomList(roomId);
    showToast("Room published and available to everyone.", "success");
  } catch (error) {
    showToast(
      error instanceof Error ? error.message : "Room publication failed.",
      "error",
    );
  } finally {
    publishRoomButton.disabled = false;
  }
});

themeToggle.addEventListener("click", () => {
  const currentlyDark = document.documentElement.dataset.theme === "dark";
  const theme = currentlyDark ? "light" : "dark";
  localStorage.setItem(themeKey, theme);
  applyPreferences();
});

soundToggle.addEventListener("click", () => {
  muted = !muted;
  localStorage.setItem(mutedKey, String(muted));
  applyPreferences();
});

playtestButton.addEventListener("click", () => {
  gameStatusElement.textContent = "Creating private playtest…";
  send({
    type: "game.playtest",
    admin_key: adminKeyInput.value,
    room_id: roomSelect.value,
    room_token: getRoomTokens()[roomSelect.value] || "",
  });
});

pauseGameButton.addEventListener("click", () => {
  send({ type: pauseGameButton.dataset.action });
});

addTimeForm.addEventListener("submit", (event) => {
  event.preventDefault();
  send({
    type: "host.add_time",
    minutes: Number.parseInt(addTimeMinutes.value, 10),
  });
});

document.querySelector("#confirm-end-game-button").addEventListener("click", () => {
  send({ type: "host.end_early" });
});

resultsHomeButton.addEventListener("click", returnHomeFromResults);
lobbyCodeCopyButton.addEventListener("click", () => {
  void copyJoinCode(lobbyCodeCopyButton, lobbyCodeElement);
});
gameCodeCopyButton.addEventListener("click", () => {
  void copyJoinCode(gameCodeCopyButton, gameCodeElement);
});
resultsCodeCopyButton.addEventListener("click", () => {
  void copyJoinCode(resultsCodeCopyButton, resultsGameCodeElement);
});

skipPuzzleForm.addEventListener("submit", (event) => {
  event.preventDefault();
  send({
    type: "host.skip",
    team_id: skipTeamSelect.value,
    puzzle_id: skipPuzzleSelect.value,
  });
});

hostMessageForm.addEventListener("submit", (event) => {
  event.preventDefault();
  send({
    type: "host.message",
    team_id: hostMessageTeamSelect.value,
    text: hostMessageInput.value,
  });
  hostMessageInput.value = "";
});

beginPuzzleButton.addEventListener("click", () => {
  beginPuzzleButton.hidden = true;
  puzzleChallenge.hidden = false;
});

hintButton.addEventListener("click", () => {
  if (currentPuzzle) {
    send({ type: "puzzle.hint", puzzle_id: currentPuzzle.id });
  }
});

document.querySelector("#close-puzzle-button").addEventListener("click", () => {
  puzzlePanel.hidden = true;
  currentPuzzle = undefined;
  puzzleMapElement.querySelector(".puzzle-entry--active")?.classList.remove(
    "puzzle-entry--active",
  );
  gameMain.insertBefore(puzzlePanel, confettiLayer);
});

nameForm.addEventListener("submit", (event) => {
  event.preventDefault();
  pendingLobbyAction = { type: "set_name", value: nameInput.value.trim() };
  sendLobbyAction("lobby.set_name", { name: nameInput.value });
});

createTeamForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const currentPlayer = lobbySnapshot?.players.find(
    (player) => player.player_id === lobbySnapshot.player_id,
  );
  if (!currentPlayer?.name || currentPlayer.name === "Choosing a name") {
    showToast("Save your player name before creating a team.", "warning");
    nameInput.focus();
    return;
  }
  pendingLobbyAction = { type: "create_team", value: teamNameInput.value.trim() };
  sendLobbyAction("lobby.create_team", { name: teamNameInput.value });
});

lockTeamsButton.addEventListener("click", () => {
  sendLobbyAction("lobby.lock_teams", {
    locked: !lobbySnapshot.teams_locked,
  });
});

autoBalanceButton.addEventListener("click", () => {
  sendLobbyAction("lobby.auto_balance");
});

startGameButton.addEventListener("click", () => {
  sendLobbyAction("lobby.start", { override_minimum: confirmStart });
});

joinForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const code = normalizeJoinCode(joinCodeInput.value);
  if (code.length !== joinCodeDigits.length) {
    showToast("Enter all 5 characters of the game code.", "warning");
    joinCodeDigits.find((digit) => !digit.value)?.focus();
    return;
  }
  send({ type: "game.join", code });
});

const currentGame = getActiveGame();
if (currentGame) {
  setJoinCode(currentGame.code);
  setFormsDisabled(true);
  gameStatusElement.textContent = `Reconnecting to game ${currentGame.code}…`;
}

connect();
loadRoomList();
applyPreferences();
