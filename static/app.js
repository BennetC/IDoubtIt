const rankOrder = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"];
const suitOrder = ["♣", "♦", "♥", "♠"];

const elements = {
  tabs: document.querySelectorAll(".tab"),
  replayControls: document.getElementById("replay-controls"),
  playControls: document.getElementById("play-controls"),
  replayView: document.getElementById("replay-view"),
  playView: document.getElementById("play-view"),
  replaySelect: document.getElementById("replay-select"),
  stepCounter: document.getElementById("step-counter"),
  stepSlider: document.getElementById("step-slider"),
  eventText: document.getElementById("event-text"),
  activeRank: document.getElementById("active-rank"),
  currentPlayer: document.getElementById("current-player"),
  pileSize: document.getElementById("pile-size"),
  pileCards: document.getElementById("pile-cards"),
  players: document.getElementById("players"),
  historyList: document.getElementById("history-list"),
  historyOrder: document.getElementById("history-order"),
  errorBanner: document.getElementById("error-banner"),
  btnStart: document.getElementById("btn-start"),
  btnPrev: document.getElementById("btn-prev"),
  btnPlay: document.getElementById("btn-play"),
  btnNext: document.getElementById("btn-next"),
  btnEnd: document.getElementById("btn-end"),
  speedSelect: document.getElementById("speed-select"),
  publicToggle: document.getElementById("public-toggle"),
  playStatus: document.getElementById("play-status"),
  playActiveRank: document.getElementById("play-active-rank"),
  playCurrentPlayer: document.getElementById("play-current-player"),
  playPileSize: document.getElementById("play-pile-size"),
  playPileCards: document.getElementById("play-pile-cards"),
  playPlayers: document.getElementById("play-players"),
  playHistoryList: document.getElementById("play-history-list"),
  playHistoryOrder: document.getElementById("play-history-order"),
  playDecision: document.getElementById("play-decision"),
  playRankButtons: document.getElementById("play-rank-buttons"),
  playHand: document.getElementById("play-hand"),
  playSubmit: document.getElementById("play-submit"),
  playChallengeButtons: document.getElementById("play-challenge-buttons"),
  playErrorBanner: document.getElementById("play-error-banner"),
  playPlayerCount: document.getElementById("play-player-count"),
  playHumanSeat: document.getElementById("play-human-seat"),
  playBotType: document.getElementById("play-bot-type"),
  playSeed: document.getElementById("play-seed"),
  playStart: document.getElementById("play-start"),
  playPause: document.getElementById("play-pause"),
  playResume: document.getElementById("play-resume"),
  playStop: document.getElementById("play-stop"),
  playSaveName: document.getElementById("play-save-name"),
  playSave: document.getElementById("play-save"),
  playSaveSelect: document.getElementById("play-save-select"),
  playLoad: document.getElementById("play-load"),
  playDebugToggle: document.getElementById("play-debug-toggle"),
  playBotEvalToggle: document.getElementById("play-bot-eval-toggle"),
  playBotEvalList: document.getElementById("play-bot-eval-list"),
  playBotEvalPlayerFilter: document.getElementById("play-bot-eval-player-filter"),
  playBotEvalTypeFilter: document.getElementById("play-bot-eval-type-filter"),
  playBotEvalAnalysis: document.getElementById("play-bot-eval-analysis"),
  replayBotEval: document.getElementById("replay-bot-eval"),
};

let replayData = null;
let states = [];
let currentStep = 0;
let playTimer = null;
let showPublic = false;
let playSession = null;
let playEvents = [];
let playSelectedCards = new Set();
let playDebug = false;
let playBotEval = false;
let playBotEvalEntries = [];
let historyOrder = "desc";
let playHistoryOrder = "desc";
let lastDecisionKey = null;

function playerColorClass(playerId) {
  if (playerId == null) {
    return "";
  }
  return `player-color-${playerId % 6}`;
}

function cardColor(card) {
  const suit = card.slice(-1);
  return suit === "♥" || suit === "♦" ? "red" : "black";
}

function parseCard(card) {
  return { rank: card.slice(0, -1), suit: card.slice(-1) };
}

function sortCards(cards) {
  return [...cards].sort((a, b) => {
    const cardA = parseCard(a);
    const cardB = parseCard(b);
    const rankDiff = rankOrder.indexOf(cardA.rank) - rankOrder.indexOf(cardB.rank);
    if (rankDiff !== 0) {
      return rankDiff;
    }
    return suitOrder.indexOf(cardA.suit) - suitOrder.indexOf(cardB.suit);
  });
}

function renderCards(container, cards) {
  container.innerHTML = "";
  if (cards.length === 0) {
    container.innerHTML = "<em>No cards</em>";
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const card of sortCards(cards)) {
    const span = document.createElement("span");
    span.className = `card ${cardColor(card) === "red" ? "red" : ""}`;
    span.textContent = card;
    fragment.appendChild(span);
  }
  container.appendChild(fragment);
}

function renderSelectableCards(container, cards) {
  container.innerHTML = "";
  if (cards.length === 0) {
    container.innerHTML = "<em>No cards</em>";
    updatePlaySubmitState();
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const card of sortCards(cards)) {
    const span = document.createElement("button");
    span.type = "button";
    span.className = `card ${cardColor(card) === "red" ? "red" : ""}`;
    if (playSelectedCards.has(card)) {
      span.classList.add("selected");
    }
    span.textContent = card;
    span.addEventListener("click", () => {
      if (playSelectedCards.has(card)) {
        playSelectedCards.delete(card);
      } else {
        if (playSelectedCards.size >= 3) {
          showPlayError("You can only select up to 3 cards.");
          return;
        }
        playSelectedCards.add(card);
      }
      renderSelectableCards(container, cards);
    });
    fragment.appendChild(span);
  }
  container.appendChild(fragment);
  updatePlaySubmitState();
}

function updatePlaySubmitState() {
  if (!elements.playSubmit) {
    return;
  }
  elements.playSubmit.disabled = playSelectedCards.size === 0;
}

function describeEvent(event, index) {
  if (!event) {
    return "Game start";
  }
  const type = event.type;
  switch (type) {
    case "GAME_START":
      return "Game started.";
    case "SELECT_RANK":
      return `P${event.player} selects active rank ${event.rank}.`;
    case "PLAY":
      return `P${event.player} plays ${event.cards.length} card(s) claiming ${event.claim_rank}.`;
    case "CHALLENGE_DECISION":
      return event.challenge
        ? `P${event.challenger} challenges.`
        : `P${event.challenger} does not challenge.`;
    case "CHALLENGE_EVAL":
      return `P${event.challenger} eval: ${event.message}`;
    case "CHALLENGE_RESOLUTION":
      return event.truthful
        ? `Challenge resolved: truthful. Revealed ${event.revealed.join(", ")}.`
        : `Challenge resolved: lie caught. Revealed ${event.revealed.join(", ")}.`;
    case "PICKUP_PILE":
      return `P${event.player} picks up ${event.cards.length} card(s).`;
    case "DISCARD_QUAD":
      return `P${event.player} discards four ${event.rank}s.`;
    case "PLACEMENT":
      return `P${event.player} finishes in place ${event.place}.`;
    case "GAME_END":
      return "Game over.";
    default:
      return `Event ${index}: ${type}`;
  }
}

function formatEval(evalData) {
  if (!evalData) {
    return "";
  }
  return `p_truthful=${evalData.p_truthful.toFixed(2)}, U_challenge=${evalData.u_challenge.toFixed(
    2,
  )}, U_pass=${evalData.u_pass.toFixed(2)}, pile=${evalData.pile}, k=${evalData.k}, my_active=${
    evalData.my_active
  }, opp_hand=${evalData.opp_hand}`;
}

function primaryEventPlayer(event) {
  if (!event) {
    return null;
  }
  if (event.player != null) {
    return event.player;
  }
  if (event.challenger != null) {
    return event.challenger;
  }
  return null;
}

function decisionKey(decision) {
  if (!decision) {
    return null;
  }
  return `${decision.type}-${decision.player}`;
}

function buildInitialState(replay) {
  return {
    players: replay.initial_state.players.map((player) => ({
      hand: [...player.hand],
      bot: player.bot,
      placement: player.placement,
      discarded: [...(player.discarded || [])],
    })),
    active_rank: replay.initial_state.active_rank,
    pile: [...replay.initial_state.pile],
    current_player: replay.initial_state.current_player ?? 0,
    placements: [...replay.initial_state.placements],
  };
}

function nextActivePlayer(state, afterPlayer) {
  const active = state.players
    .map((player, idx) => ({ player, idx }))
    .filter(({ player }) => player.placement == null)
    .map(({ idx }) => idx);
  if (active.length === 0) {
    return null;
  }
  if (!active.includes(afterPlayer)) {
    return active[0];
  }
  const index = active.indexOf(afterPlayer);
  return active[(index + 1) % active.length];
}

function removeCards(hand, cards, errors) {
  for (const card of cards) {
    const idx = hand.indexOf(card);
    if (idx === -1) {
      errors.push(`Card ${card} missing from hand during replay.`);
      return false;
    }
    hand.splice(idx, 1);
  }
  return true;
}

function applyEvent(state, event, errors) {
  switch (event.type) {
    case "GAME_START":
      break;
    case "SELECT_RANK":
      state.active_rank = event.rank;
      break;
    case "PLAY":
      removeCards(state.players[event.player].hand, event.cards, errors);
      state.pile.push(...event.cards);
      break;
    case "CHALLENGE_DECISION":
      if (!event.challenge) {
        state.current_player = event.challenger;
      }
      break;
    case "CHALLENGE_RESOLUTION":
      break;
    case "PICKUP_PILE":
      state.players[event.player].hand.push(...event.cards);
      state.pile = [];
      state.active_rank = null;
      state.current_player = nextActivePlayer(state, event.player);
      break;
    case "DISCARD_QUAD":
      removeCards(state.players[event.player].hand, event.cards, errors);
      state.players[event.player].discarded.push(...event.cards);
      break;
    case "PLACEMENT":
      state.players[event.player].placement = event.place;
      state.placements.push(event.player);
      if (state.current_player === event.player) {
        state.current_player = nextActivePlayer(state, event.player);
      }
      break;
    case "GAME_END":
      state.current_player = null;
      break;
    default:
      errors.push(`Unknown event type: ${event.type}`);
  }
}

function collectCards(state) {
  const cards = [];
  for (const player of state.players) {
    cards.push(...player.hand);
    cards.push(...player.discarded);
  }
  cards.push(...state.pile);
  return cards;
}

function validateReplay(replay) {
  const errors = [];
  if (!replay.initial_state || !replay.initial_state.players) {
    return ["Replay missing initial state."];
  }
  const initialCards = replay.initial_state.players.flatMap((player) => player.hand);
  if (initialCards.length !== 52) {
    errors.push(`Initial hands contain ${initialCards.length} cards (expected 52).`);
  }
  const initialCounts = new Map();
  for (const card of initialCards) {
    initialCounts.set(card, (initialCounts.get(card) || 0) + 1);
  }
  const state = buildInitialState(replay);
  const events = replay.events || [];
  events.forEach((event, index) => {
    applyEvent(state, event, errors);
    const currentCards = collectCards(state);
    if (currentCards.length !== initialCards.length) {
      errors.push(
        `Event ${index + 1}: card count mismatch (${currentCards.length} vs ${initialCards.length}).`
      );
    }
    const currentCounts = new Map();
    for (const card of currentCards) {
      currentCounts.set(card, (currentCounts.get(card) || 0) + 1);
    }
    if (currentCounts.size !== initialCounts.size) {
      errors.push(`Event ${index + 1}: card conservation violation detected.`);
    } else {
      for (const [card, count] of initialCounts.entries()) {
        if (currentCounts.get(card) !== count) {
          errors.push(`Event ${index + 1}: card conservation violation detected.`);
          break;
        }
      }
    }
  });
  return errors;
}

function buildStates(replay) {
  const errors = [];
  const state = buildInitialState(replay);
  const statesList = [JSON.parse(JSON.stringify(state))];
  for (const event of replay.events) {
    applyEvent(state, event, errors);
    statesList.push(JSON.parse(JSON.stringify(state)));
  }
  return { states: statesList, errors };
}

function renderState(step) {
  const state = states[step];
  const event = step === 0 ? null : replayData.events[step - 1];
  elements.stepCounter.textContent = `Step ${step} / ${replayData.events.length}`;
  elements.activeRank.textContent = state.active_rank ?? "-";
  elements.currentPlayer.textContent =
    state.current_player == null ? "-" : `P${state.current_player}`;
  elements.pileSize.textContent = state.pile.length;

  elements.eventText.textContent = describeEvent(event, step);
  if (elements.replayBotEval) {
    if (event && event.eval) {
      elements.replayBotEval.textContent = formatEval(event.eval);
    } else {
      elements.replayBotEval.innerHTML = "<em>No eval data for this event.</em>";
    }
  }

  if (showPublic) {
    elements.pileCards.innerHTML = `<em>${state.pile.length} cards hidden</em>`;
  } else {
    renderCards(elements.pileCards, state.pile);
  }

  elements.players.innerHTML = "";
  state.players.forEach((player, idx) => {
    const wrapper = document.createElement("div");
    wrapper.className = "player";
    wrapper.classList.add(playerColorClass(idx));
    if (state.current_player === idx) {
      wrapper.classList.add("current");
    }
    const placement = player.placement ? `Place ${player.placement}` : "In play";
    const header = document.createElement("div");
    header.className = "player-header";
    header.innerHTML = `
      <div class="player-title">P${idx} (${player.bot})</div>
      <div class="player-meta">${placement} · ${player.hand.length} cards</div>
    `;
    const handList = document.createElement("div");
    handList.className = "card-list";
    if (showPublic) {
      handList.innerHTML = `<em>${player.hand.length} cards hidden</em>`;
    } else {
      renderCards(handList, player.hand);
    }
    const discarded = document.createElement("div");
    discarded.className = "player-meta";
    discarded.textContent = player.discarded.length
      ? `Discarded quads: ${player.discarded.length} cards`
      : "Discarded quads: none";
    wrapper.appendChild(header);
    wrapper.appendChild(handList);
    wrapper.appendChild(discarded);
    elements.players.appendChild(wrapper);
  });

  const historyItems = elements.historyList.querySelectorAll("li");
  historyItems.forEach((item) => {
    item.classList.toggle("active", Number(item.dataset.step) === step);
  });
}

function updateHistory() {
  elements.historyList.innerHTML = "";
  const indices = replayData.events.map((_, idx) => idx);
  if (historyOrder === "desc") {
    indices.reverse();
  }
  indices.forEach((idx) => {
    const event = replayData.events[idx];
    const item = document.createElement("li");
    item.textContent = `${idx + 1}. ${describeEvent(event, idx + 1)}`;
    item.dataset.step = String(idx + 1);
    const primaryPlayer = primaryEventPlayer(event);
    if (primaryPlayer != null) {
      item.classList.add(playerColorClass(primaryPlayer));
    }
    item.addEventListener("click", () => {
      stopPlayback();
      setStep(idx + 1);
    });
    elements.historyList.appendChild(item);
  });
}

function setStep(step) {
  currentStep = Math.max(0, Math.min(step, states.length - 1));
  elements.stepSlider.value = currentStep;
  renderState(currentStep);
}

function playStep() {
  if (currentStep >= states.length - 1) {
    stopPlayback();
    return;
  }
  setStep(currentStep + 1);
}

function startPlayback() {
  if (playTimer) {
    return;
  }
  elements.btnPlay.textContent = "Pause";
  const speed = Number(elements.speedSelect.value);
  playTimer = setInterval(playStep, 1000 / speed);
}

function stopPlayback() {
  if (playTimer) {
    clearInterval(playTimer);
    playTimer = null;
    elements.btnPlay.textContent = "Play";
  }
}

function togglePlayback() {
  if (playTimer) {
    stopPlayback();
  } else {
    startPlayback();
  }
}

async function loadReplayList() {
  const response = await fetch("/api/replays");
  const data = await response.json();
  elements.replaySelect.innerHTML = "";
  data.replays.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    elements.replaySelect.appendChild(option);
  });
  if (data.replays.length > 0) {
    elements.replaySelect.value = data.replays[0];
    await loadReplay(data.replays[0]);
  }
}

async function loadReplay(name) {
  stopPlayback();
  const response = await fetch(`/api/replay/${name}`);
  replayData = await response.json();
  elements.errorBanner.classList.add("hidden");
  if (replayData.validation_errors && replayData.validation_errors.length) {
    elements.errorBanner.textContent = `Validation errors: ${replayData.validation_errors.join(" ")}`;
    elements.errorBanner.classList.remove("hidden");
  }
  const validationErrors = validateReplay(replayData);
  if (validationErrors.length) {
    elements.errorBanner.textContent = `Validation errors: ${validationErrors.join(" ")}`;
    elements.errorBanner.classList.remove("hidden");
  }
  const build = buildStates(replayData);
  states = build.states;
  elements.stepSlider.max = states.length - 1;
  elements.stepSlider.value = 0;
  updateHistory();
  setStep(0);
}

function showPlayError(message) {
  elements.playErrorBanner.textContent = message;
  elements.playErrorBanner.classList.remove("hidden");
}

function clearPlayError() {
  elements.playErrorBanner.classList.add("hidden");
  elements.playErrorBanner.textContent = "";
}

function updatePlaySeatOptions() {
  const count = Number(elements.playPlayerCount.value);
  elements.playHumanSeat.innerHTML = "";
  for (let idx = 0; idx < count; idx += 1) {
    const option = document.createElement("option");
    option.value = String(idx);
    option.textContent = `Seat ${idx}`;
    elements.playHumanSeat.appendChild(option);
  }
  if (Number(elements.playHumanSeat.value) >= count) {
    elements.playHumanSeat.value = "0";
  }
}

function setTab(tab) {
  if (tab === "play") {
    stopPlayback();
  }
  elements.tabs.forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tab);
  });
  const replayActive = tab === "replay";
  elements.replayControls.classList.toggle("hidden", !replayActive);
  elements.playControls.classList.toggle("hidden", replayActive);
  elements.replayView.classList.toggle("hidden", !replayActive);
  elements.playView.classList.toggle("hidden", replayActive);
  elements.stepSlider.classList.toggle("hidden", !replayActive);
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  const data = await response.json();
  if (!response.ok) {
    const message = data.error || "Request failed.";
    throw new Error(message);
  }
  return data;
}

function appendPlayHistory(events) {
  if (!events || events.length === 0) {
    return;
  }
  for (const event of events) {
    playEvents.push(event);
  }
}

function appendPlayBotEval(entries) {
  if (!entries || entries.length === 0) {
    return;
  }
  for (const entry of entries) {
    playBotEvalEntries.push(entry);
  }
}

function renderPlayBotEvalList() {
  if (!elements.playBotEvalList) {
    return;
  }
  elements.playBotEvalList.innerHTML = "";
  if (!playBotEval || playBotEvalEntries.length === 0) {
    elements.playBotEvalList.innerHTML = "<li><em>No bot eval data.</em></li>";
    return;
  }
  for (const [idx, entry] of playBotEvalEntries.entries()) {
    const item = document.createElement("li");
    item.textContent = `${idx + 1}. P${entry.challenger} ${entry.type}: ${formatEval(
      entry.eval,
    )}`;
    item.classList.add(playerColorClass(entry.challenger));
    elements.playBotEvalList.appendChild(item);
  }
}

function updateBotEvalFilters() {
  if (!elements.playBotEvalPlayerFilter || !playSession) {
    return;
  }
  elements.playBotEvalPlayerFilter.innerHTML = "";
  const allOption = document.createElement("option");
  allOption.value = "all";
  allOption.textContent = "All";
  elements.playBotEvalPlayerFilter.appendChild(allOption);
  playSession.public_state.players.forEach((player) => {
    const option = document.createElement("option");
    option.value = String(player.id);
    option.textContent = `P${player.id}`;
    elements.playBotEvalPlayerFilter.appendChild(option);
  });
}

function renderBotEvalAnalysis() {
  if (!elements.playBotEvalAnalysis) {
    return;
  }
  elements.playBotEvalAnalysis.innerHTML = "";
  if (!playSession || !playSession.finished || playBotEvalEntries.length === 0) {
    elements.playBotEvalAnalysis.innerHTML = "<li><em>No analysis data.</em></li>";
    return;
  }
  const playerFilter = elements.playBotEvalPlayerFilter?.value ?? "all";
  const typeFilter = elements.playBotEvalTypeFilter?.value ?? "all";
  const filtered = playBotEvalEntries.filter((entry) => {
    if (playerFilter !== "all" && String(entry.challenger) !== playerFilter) {
      return false;
    }
    if (typeFilter !== "all" && entry.type !== typeFilter) {
      return false;
    }
    return true;
  });
  if (filtered.length === 0) {
    elements.playBotEvalAnalysis.innerHTML = "<li><em>No matching eval data.</em></li>";
    return;
  }
  filtered.forEach((entry, idx) => {
    const item = document.createElement("li");
    item.textContent = `${idx + 1}. P${entry.challenger} ${entry.type}: ${formatEval(
      entry.eval,
    )}`;
    item.classList.add(playerColorClass(entry.challenger));
    elements.playBotEvalAnalysis.appendChild(item);
  });
}

function renderPlayHistory() {
  elements.playHistoryList.innerHTML = "";
  const indices = playEvents.map((_, idx) => idx);
  if (playHistoryOrder === "desc") {
    indices.reverse();
  }
  const humanIndex = playSession?.human_index ?? null;
  const lastHumanPlayIndex = playEvents.reduce((acc, event, idx) => {
    if (event.type === "PLAY" && event.player === humanIndex) {
      return idx;
    }
    return acc;
  }, -1);
  indices.forEach((idx) => {
    const event = playEvents[idx];
    const item = document.createElement("li");
    item.textContent = `${idx + 1}. ${describeEvent(event, idx + 1)}`;
    const primaryPlayer = primaryEventPlayer(event);
    if (primaryPlayer != null) {
      item.classList.add(playerColorClass(primaryPlayer));
    }
    if (lastHumanPlayIndex !== -1 && idx > lastHumanPlayIndex) {
      item.classList.add("recent-since-human");
    }
    elements.playHistoryList.appendChild(item);
  });
}

function renderPlayState() {
  if (!playSession) {
    elements.playStatus.textContent = "Start a new game to begin.";
    elements.playActiveRank.textContent = "-";
    elements.playCurrentPlayer.textContent = "-";
    elements.playPileSize.textContent = "0";
    elements.playPileCards.innerHTML = "";
    elements.playPlayers.innerHTML = "";
    elements.playHistoryList.innerHTML = "";
    elements.playDecision.textContent = "Waiting for game start.";
    elements.playRankButtons.innerHTML = "";
    elements.playHand.innerHTML = "";
    elements.playChallengeButtons.innerHTML = "";
    elements.playSubmit.classList.add("hidden");
    if (elements.playBotEvalList) {
      elements.playBotEvalList.innerHTML = "";
    }
    if (elements.playBotEvalAnalysis) {
      elements.playBotEvalAnalysis.innerHTML = "";
    }
    playSelectedCards = new Set();
    lastDecisionKey = null;
    return;
  }
  const botEvalDetails = elements.playBotEvalList?.closest("details");
  const botEvalAnalysisDetails = elements.playBotEvalAnalysis?.closest("details");
  if (botEvalDetails) {
    botEvalDetails.classList.toggle("hidden", !playBotEval);
  }
  if (botEvalAnalysisDetails) {
    botEvalAnalysisDetails.classList.toggle("hidden", !playBotEval);
  }
  const state = playDebug ? playSession.debug_state : playSession.public_state;
  elements.playActiveRank.textContent = state.active_rank ?? "-";
  elements.playCurrentPlayer.textContent =
    state.current_player == null ? "-" : `P${state.current_player}`;
  elements.playPileSize.textContent = state.pile_size;
  if (playDebug) {
    renderCards(elements.playPileCards, state.pile);
  } else {
    elements.playPileCards.innerHTML =
      state.pile_size > 0 ? `<em>${state.pile_size} cards hidden</em>` : "<em>Empty</em>";
  }
  elements.playPlayers.innerHTML = "";
  state.players.forEach((player) => {
    const wrapper = document.createElement("div");
    wrapper.className = "player";
    wrapper.classList.add(playerColorClass(player.id));
    if (state.current_player === player.id) {
      wrapper.classList.add("current");
    }
    const placement = player.placement ? `Place ${player.placement}` : "In play";
    const header = document.createElement("div");
    header.className = "player-header";
    const humanTag = player.id === playSession.human_index ? " (Human)" : "";
    header.innerHTML = `
      <div class="player-title">P${player.id}${humanTag} (${player.bot})</div>
      <div class="player-meta">${placement} · ${player.hand_size} cards</div>
    `;
    const handList = document.createElement("div");
    handList.className = "card-list";
    if (player.hand.length > 0) {
      renderCards(handList, player.hand);
    } else if (player.hand_size === 0) {
      handList.innerHTML = "<em>No cards</em>";
    } else {
      handList.innerHTML = "<em>Hidden</em>";
    }
    wrapper.appendChild(header);
    wrapper.appendChild(handList);
    elements.playPlayers.appendChild(wrapper);
  });

  const decision = playSession.pending_decision;
  const currentDecisionKey = decisionKey(decision);
  if (currentDecisionKey !== lastDecisionKey) {
    playSelectedCards = new Set();
    lastDecisionKey = currentDecisionKey;
  }
  elements.playRankButtons.innerHTML = "";
  elements.playHand.innerHTML = "";
  elements.playChallengeButtons.innerHTML = "";
  elements.playSubmit.classList.add("hidden");
  updatePlaySubmitState();
  if (playSession.finished) {
    elements.playDecision.textContent = "Game over.";
    elements.playStatus.textContent = "Game over.";
    updateBotEvalFilters();
    renderPlayBotEvalList();
    renderBotEvalAnalysis();
    return;
  }
  if (playSession.paused) {
    elements.playStatus.textContent = "Paused.";
  } else if (decision) {
    elements.playStatus.textContent = `Waiting for you: ${decision.type.replace("_", " ")}`;
  } else {
    elements.playStatus.textContent = "Waiting for bots...";
  }
  if (!decision) {
    elements.playDecision.textContent = "Waiting for the next decision.";
    renderPlayBotEvalList();
    return;
  }
  if (decision.type === "SELECT_RANK") {
    elements.playDecision.textContent = "Choose a new active rank.";
    rankOrder.forEach((rank) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = rank;
      button.addEventListener("click", async () => {
        try {
          clearPlayError();
          const data = await postJson("/api/game/action", {
            session_id: playSession.session_id,
            action: { type: "SELECT_RANK", rank },
          });
          applyPlayResponse(data);
        } catch (error) {
          showPlayError(error.message);
        }
      });
      elements.playRankButtons.appendChild(button);
    });
  } else if (decision.type === "PLAY") {
    elements.playDecision.textContent = "Select 1-3 cards to play.";
    const human = state.players.find((player) => player.id === playSession.human_index);
    renderSelectableCards(elements.playHand, human?.hand || []);
    elements.playSubmit.classList.remove("hidden");
  } else if (decision.type === "CHALLENGE") {
    elements.playDecision.textContent = "Challenge the last play?";
    const challenge = document.createElement("button");
    challenge.type = "button";
    challenge.textContent = "Challenge";
    const pass = document.createElement("button");
    pass.type = "button";
    pass.textContent = "Pass";
    const handler = async (value) => {
      try {
        clearPlayError();
        const data = await postJson("/api/game/action", {
          session_id: playSession.session_id,
          action: { type: "CHALLENGE", value },
        });
        applyPlayResponse(data);
      } catch (error) {
        showPlayError(error.message);
      }
    };
    challenge.addEventListener("click", () => handler(true));
    pass.addEventListener("click", () => handler(false));
    elements.playChallengeButtons.appendChild(challenge);
    elements.playChallengeButtons.appendChild(pass);
  }
  renderPlayBotEvalList();
}

function applyPlayResponse(data) {
  playSession = data;
  appendPlayHistory(data.events);
  appendPlayBotEval(data.bot_eval);
  renderPlayHistory();
  updateBotEvalFilters();
  renderPlayBotEvalList();
  renderBotEvalAnalysis();
  if (data.replay_saved) {
    loadReplayList();
  }
  renderPlayState();
}

async function refreshSaveList() {
  const response = await fetch("/api/saves");
  const data = await response.json();
  elements.playSaveSelect.innerHTML = "";
  data.saves.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    elements.playSaveSelect.appendChild(option);
  });
}

function setupControls() {
  elements.tabs.forEach((button) => {
    button.addEventListener("click", () => {
      setTab(button.dataset.tab);
    });
  });
  elements.stepSlider.addEventListener("input", (event) => {
    stopPlayback();
    setStep(Number(event.target.value));
  });
  elements.btnStart.addEventListener("click", () => {
    stopPlayback();
    setStep(0);
  });
  elements.btnEnd.addEventListener("click", () => {
    stopPlayback();
    setStep(states.length - 1);
  });
  elements.btnPrev.addEventListener("click", () => {
    stopPlayback();
    setStep(currentStep - 1);
  });
  elements.btnNext.addEventListener("click", () => {
    stopPlayback();
    setStep(currentStep + 1);
  });
  elements.btnPlay.addEventListener("click", togglePlayback);
  elements.speedSelect.addEventListener("change", () => {
    if (playTimer) {
      stopPlayback();
      startPlayback();
    }
  });
  elements.historyOrder.addEventListener("change", (event) => {
    historyOrder = event.target.value;
    if (replayData) {
      updateHistory();
      renderState(currentStep);
    }
  });
  elements.playHistoryOrder.addEventListener("change", (event) => {
    playHistoryOrder = event.target.value;
    if (playSession) {
      renderPlayHistory();
    }
  });
  elements.playBotEvalPlayerFilter.addEventListener("change", () => {
    renderBotEvalAnalysis();
  });
  elements.playBotEvalTypeFilter.addEventListener("change", () => {
    renderBotEvalAnalysis();
  });
  elements.replaySelect.addEventListener("change", (event) => {
    loadReplay(event.target.value);
  });
  elements.publicToggle.addEventListener("change", (event) => {
    showPublic = event.target.checked;
    renderState(currentStep);
  });
  elements.playPlayerCount.addEventListener("change", updatePlaySeatOptions);
  elements.playDebugToggle.addEventListener("change", (event) => {
    playDebug = event.target.checked;
    renderPlayState();
  });
  elements.playBotEvalToggle.addEventListener("change", (event) => {
    playBotEval = event.target.checked;
    renderPlayBotEvalList();
    renderBotEvalAnalysis();
  });
  elements.playStart.addEventListener("click", async () => {
    try {
      clearPlayError();
      playEvents = [];
      playBotEvalEntries = [];
      const playerCount = Number(elements.playPlayerCount.value);
      const humanIndex = Number(elements.playHumanSeat.value);
      const botType = elements.playBotType.value;
      const botTypes = Array.from({ length: playerCount }, () => botType);
      const seedValue = elements.playSeed.value ? Number(elements.playSeed.value) : null;
      const data = await postJson("/api/game/new", {
        players: playerCount,
        human_index: humanIndex,
        bot_types: botTypes,
        seed: seedValue,
      });
      applyPlayResponse(data);
    } catch (error) {
      showPlayError(error.message);
    }
  });
  elements.playPause.addEventListener("click", async () => {
    if (!playSession) {
      showPlayError("No active game.");
      return;
    }
    try {
      clearPlayError();
      const data = await postJson("/api/game/pause", { session_id: playSession.session_id });
      applyPlayResponse(data);
    } catch (error) {
      showPlayError(error.message);
    }
  });
  elements.playResume.addEventListener("click", async () => {
    if (!playSession) {
      showPlayError("No active game.");
      return;
    }
    try {
      clearPlayError();
      const data = await postJson("/api/game/resume", { session_id: playSession.session_id });
      applyPlayResponse(data);
    } catch (error) {
      showPlayError(error.message);
    }
  });
  elements.playStop.addEventListener("click", async () => {
    if (!playSession) {
      showPlayError("No active game.");
      return;
    }
    if (!confirm("Stop the current game without saving?")) {
      return;
    }
    try {
      clearPlayError();
      await postJson("/api/game/stop", { session_id: playSession.session_id });
      playSession = null;
      playEvents = [];
      playBotEvalEntries = [];
      renderPlayState();
    } catch (error) {
      showPlayError(error.message);
    }
  });
  elements.playSave.addEventListener("click", async () => {
    if (!playSession) {
      showPlayError("No active game.");
      return;
    }
    const saveName = elements.playSaveName.value.trim();
    if (!saveName) {
      showPlayError("Enter a save name.");
      return;
    }
    try {
      clearPlayError();
      await postJson("/api/game/save", {
        session_id: playSession.session_id,
        save_name: saveName,
      });
      await refreshSaveList();
    } catch (error) {
      showPlayError(error.message);
    }
  });
  elements.playLoad.addEventListener("click", async () => {
    const saveName = elements.playSaveSelect.value;
    if (!saveName) {
      showPlayError("Select a save to load.");
      return;
    }
    try {
      clearPlayError();
      playEvents = [];
      const data = await postJson("/api/game/load", { save_name: saveName });
      applyPlayResponse(data);
    } catch (error) {
      showPlayError(error.message);
    }
  });
  elements.playSubmit.addEventListener("click", async () => {
    if (!playSession) {
      showPlayError("No active game.");
      return;
    }
    if (playSelectedCards.size < 1 || playSelectedCards.size > 3) {
      showPlayError("Select 1-3 cards to play.");
      return;
    }
    try {
      clearPlayError();
      const data = await postJson("/api/game/action", {
        session_id: playSession.session_id,
        action: { type: "PLAY", cards: Array.from(playSelectedCards) },
      });
      applyPlayResponse(data);
    } catch (error) {
      showPlayError(error.message);
    }
  });
}

setupControls();
loadReplayList();
updatePlaySeatOptions();
refreshSaveList();
setTab("replay");
