(function () {
  const GRID = 20;
  const CELL = 16;
  const TICK_MS = 130;
  const DALE_GREEN = '#9bbc0f';
  const DALE_DARK = '#0a0a0a';
  const DALE_RED = '#c41e3a';

  let modalEl = null;
  let canvas = null;
  let ctx = null;
  let loopId = null;
  let snake = [];
  let direction = { x: 1, y: 0 };
  let nextDirection = { x: 1, y: 0 };
  let food = { x: 10, y: 10 };
  let score = 0;
  let running = false;
  let keyHandler = null;

  function randCell() {
    return {
      x: Math.floor(Math.random() * GRID),
      y: Math.floor(Math.random() * GRID),
    };
  }

  function foodOnSnake() {
    return snake.some((part) => part.x === food.x && part.y === food.y);
  }

  function placeFood() {
    do {
      food = randCell();
    } while (foodOnSnake());
  }

  function resetGame() {
    snake = [
      { x: 8, y: 10 },
      { x: 7, y: 10 },
      { x: 6, y: 10 },
    ];
    direction = { x: 1, y: 0 };
    nextDirection = { x: 1, y: 0 };
    score = 0;
    placeFood();
    updateScore();
    draw();
  }

  function updateScore() {
    const el = document.getElementById('snake-score');
    if (el) el.textContent = String(score);
  }

  function drawCell(x, y, color) {
    ctx.fillStyle = color;
    ctx.fillRect(x * CELL, y * CELL, CELL - 1, CELL - 1);
  }

  function draw() {
    if (!ctx) return;
    ctx.fillStyle = DALE_DARK;
    ctx.fillRect(0, 0, GRID * CELL, GRID * CELL);
    drawCell(food.x, food.y, DALE_RED);
    snake.forEach((part, index) => {
      drawCell(part.x, part.y, index === 0 ? DALE_GREEN : '#8bac0f');
    });
  }

  function step() {
    direction = nextDirection;
    const head = {
      x: snake[0].x + direction.x,
      y: snake[0].y + direction.y,
    };

    if (head.x < 0 || head.y < 0 || head.x >= GRID || head.y >= GRID) {
      gameOver();
      return;
    }
    if (snake.some((part) => part.x === head.x && part.y === head.y)) {
      gameOver();
      return;
    }

    snake.unshift(head);
    if (head.x === food.x && head.y === food.y) {
      score += 10;
      updateScore();
      placeFood();
    } else {
      snake.pop();
    }
    draw();
  }

  function gameOver() {
    running = false;
    if (loopId) {
      clearInterval(loopId);
      loopId = null;
    }
    const status = document.getElementById('snake-status');
    if (status) status.textContent = `Crashed! Score ${score}. Press Restart or arrow keys.`;
  }

  function startLoop() {
    if (loopId) clearInterval(loopId);
    running = true;
    const status = document.getElementById('snake-status');
    if (status) status.textContent = 'Arrow keys or tap the pad. Eat the red squares.';
    loopId = setInterval(() => {
      if (running) step();
    }, TICK_MS);
  }

  function setDirection(x, y) {
    if (!running) {
      resetGame();
      startLoop();
    }
    if (x === -direction.x && y === -direction.y) return;
    nextDirection = { x, y };
  }

  function onKeyDown(event) {
    if (!modalEl || modalEl.classList.contains('hidden')) return;
    const map = {
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
    };
    if (map[event.key]) {
      event.preventDefault();
      setDirection(map[event.key][0], map[event.key][1]);
    }
    if (event.key === 'Escape') close();
  }

  function buildModal() {
    if (modalEl) return;
    document.body.insertAdjacentHTML('beforeend', `
      <div class="modal hidden snake-easter-egg" id="snake-easter-egg" aria-hidden="true">
        <div class="modal-panel card snake-panel">
          <div class="modal-header">
            <div>
              <span class="eyebrow">#3 Intimidator</span>
              <h2>Nokia Snake</h2>
            </div>
            <button class="btn ghost" type="button" id="snake-close-btn" aria-label="Close">Close</button>
          </div>
          <p class="hero-sub snake-tagline">Found the Dale Earnhardt theme secret. Go get 'em.</p>
          <div class="snake-hud">
            <span>Score: <strong id="snake-score">0</strong></span>
            <button type="button" class="btn secondary" id="snake-restart-btn">Restart</button>
          </div>
          <canvas id="snake-canvas" width="${GRID * CELL}" height="${GRID * CELL}" aria-label="Snake game"></canvas>
          <div class="snake-dpad" aria-hidden="true">
            <button type="button" class="btn ghost snake-dpad-btn" data-dir="up">▲</button>
            <button type="button" class="btn ghost snake-dpad-btn" data-dir="left">◀</button>
            <button type="button" class="btn ghost snake-dpad-btn" data-dir="down">▼</button>
            <button type="button" class="btn ghost snake-dpad-btn" data-dir="right">▶</button>
          </div>
          <p class="hero-sub" id="snake-status"></p>
        </div>
      </div>
    `);

    modalEl = document.getElementById('snake-easter-egg');
    canvas = document.getElementById('snake-canvas');
    ctx = canvas.getContext('2d');

    document.getElementById('snake-close-btn')?.addEventListener('click', close);
    document.getElementById('snake-restart-btn')?.addEventListener('click', () => {
      resetGame();
      startLoop();
    });
    modalEl.addEventListener('click', (event) => {
      if (event.target === modalEl) close();
    });

    const dirs = {
      up: [0, -1],
      down: [0, 1],
      left: [-1, 0],
      right: [1, 0],
    };
    modalEl.querySelectorAll('.snake-dpad-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const move = dirs[btn.dataset.dir];
        if (move) setDirection(move[0], move[1]);
      });
    });
  }

  function open() {
    buildModal();
    if (!keyHandler) {
      keyHandler = onKeyDown;
      window.addEventListener('keydown', keyHandler);
    }
    modalEl.classList.remove('hidden');
    modalEl.setAttribute('aria-hidden', 'false');
    resetGame();
    startLoop();
  }

  function close() {
    if (!modalEl) return;
    running = false;
    if (loopId) {
      clearInterval(loopId);
      loopId = null;
    }
    modalEl.classList.add('hidden');
    modalEl.setAttribute('aria-hidden', 'true');
  }

  window.MaintainSMIPSnake = { open, close };
})();