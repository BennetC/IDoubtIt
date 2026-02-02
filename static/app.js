const rankOrder = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"];
const suitOrder = ["♣", "♦", "♥", "♠"];

const elements = {
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
  errorBanner: document.getElementById("error-banner"),
  btnStart: document.getElementById("btn-start"),
  btnPrev: document.getElementById("btn-prev"),
  btnPlay: document.getElementById("btn-play"),
  btnNext: document.getElementById("btn-next"),
  btnEnd: document.getElementById("btn-end"),
  speedSelect: document.getElementById("speed-select"),
  publicToggle: document.getElementById("public-toggle"),
};

let replayData = null;
let states = [];
let currentStep = 0;
let playTimer = null;
let showPublic = false;

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

  if (showPublic) {
    elements.pileCards.innerHTML = `<em>${state.pile.length} cards hidden</em>`;
  } else {
    renderCards(elements.pileCards, state.pile);
  }

  elements.players.innerHTML = "";
  state.players.forEach((player, idx) => {
    const wrapper = document.createElement("div");
    wrapper.className = "player";
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
  historyItems.forEach((item, index) => {
    item.classList.toggle("active", index + 1 === step);
  });
}

function updateHistory() {
  elements.historyList.innerHTML = "";
  replayData.events.forEach((event, idx) => {
    const item = document.createElement("li");
    item.textContent = `${idx + 1}. ${describeEvent(event, idx + 1)}`;
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

function setupControls() {
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
  elements.replaySelect.addEventListener("change", (event) => {
    loadReplay(event.target.value);
  });
  elements.publicToggle.addEventListener("change", (event) => {
    showPublic = event.target.checked;
    renderState(currentStep);
  });
}

setupControls();
loadReplayList();
